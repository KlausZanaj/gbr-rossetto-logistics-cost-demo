"""Same-population comparison and deterministic greedy pair consolidation."""
import hashlib
import json
from collections import Counter, defaultdict
from itertools import combinations

from .domain import AnalysisResult, Choice, Evaluation, Exclusion, Group, Issue, ModelConfig, ValidatedData
from .pricing import alternatives, cheapest


def config_payload(config: ModelConfig) -> dict:
    return {"timezone_name": config.timezone_name, "nonworking_dates": sorted(d.isoformat() for d in config.nonworking_dates),
            "money_rounding": config.money_rounding, "model_version": "0.1.0"}


def content_signature(hashes: tuple[tuple[str, str], ...], config: ModelConfig) -> str:
    encoded = json.dumps({"domain": "kz-input-v1", "inputs": sorted(hashes), "config": config_payload(config)}, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def proposal_id(members: tuple[str, ...]) -> str:
    payload = b"kz-proposal-v1\0" + json.dumps(sorted(members), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "kz-proposal-v1-" + hashlib.sha256(payload).hexdigest()


def consolidation_key(shipment):
    return shipment.customer_id, shipment.destination_id, shipment.zone, shipment.dispatch_at


def group_for(members, selected):
    ids = tuple(sorted(members))
    return Group(ids, proposal_id(ids), selected)


def assess_union(result: AnalysisResult, left: Group, right: Group) -> dict:
    """On-demand pair explanation; no quadratic report materialization."""
    lookup = {c.shipment.shipment_id: c.shipment for c in result.choices}
    members = tuple(sorted(left.members + right.members))
    if len(set(members)) != len(members) or any(sid not in lookup for sid in members):
        return {"status": "NOT_FEASIBLE", "reasons": ("Membri duplicati o non confrontabili.",), "evaluations": (), "saving_cents": None}
    shipments = tuple(lookup[sid] for sid in members)
    if any(not s.consolidation_allowed or s.handling_class != "standard" for s in shipments) or len({consolidation_key(s) for s in shipments}) != 1:
        return {"status": "NOT_FEASIBLE", "reasons": ("Cliente, sede, zona, istante o permesso di consolidamento incompatibili.",), "evaluations": (), "saving_cents": None}
    packages = tuple(p for p in result.data.packages if p.shipment_id in members)
    evaluations = alternatives(shipments, packages, result.data.tariffs, result.config)
    chosen = cheapest(evaluations)
    if chosen is None:
        reasons = tuple(reason for evaluation in evaluations for reason in evaluation.reasons) or ("Nessuna tariffa valida.",)
        return {"status": "NOT_FEASIBLE", "reasons": reasons, "evaluations": evaluations, "saving_cents": None}
    gain = left.selected.trace.total_cents + right.selected.trace.total_cents - chosen.trace.total_cents
    return {"status": "SAVING" if gain >= 1 else "NO_SAVING", "reasons": () if gain >= 1 else ("L'unione non riduce il costo almeno di un centesimo.",),
            "evaluations": evaluations, "saving_cents": gain}


def analyze(data: ValidatedData, config: ModelConfig) -> AnalysisResult:
    signature = content_signature(data.inputs.hashes, config)
    if data.blocked:
        return AnalysisResult(data, config, signature, (), (), (), data.issues)
    issues = list(data.issues)
    exclusions, choices = [], []
    lookup = {s.shipment_id: s for s in data.shipments}
    by_shipment = defaultdict(list)
    for package in data.packages:
        by_shipment[package.shipment_id].append(package)
    reason_lookup = defaultdict(list)
    for issue in issues:
        if issue.shipment_id and issue.severity == "EXCLUDE":
            reason_lookup[issue.shipment_id].append(issue.code + ": " + (issue.field + ": " if issue.field else "") + issue.message)
    for record in sorted(data.inputs.table("shipments.csv").records(), key=lambda r: r["shipment_id"]):
        sid = record["shipment_id"]
        if sid in data.invalid_shipments:
            exclusions.append(Exclusion(sid, "INVALID_DATA", tuple(reason_lookup[sid])))
            continue
        shipment = lookup[sid]
        if shipment.handling_class != "standard":
            exclusions.append(Exclusion(sid, "OUT_OF_SCOPE", tuple(reason_lookup[sid])))
            continue
        evaluations = alternatives((shipment,), tuple(by_shipment[sid]), data.tariffs, config)
        baseline = next((e for e in evaluations if e.service_id == shipment.current_service_id), None)
        if baseline is None or not baseline.feasible:
            reasons = baseline.reasons if baseline else ("NO_VALID_TARIFF: nessuna tariffa originale valida per zona e giorno locale",)
            exclusions.append(Exclusion(sid, "BASELINE_NOT_COMPARABLE", reasons))
            issues.append(Issue("EXCLUDE", "BASELINE_NOT_COMPARABLE", " | ".join(reasons), "shipments.csv", shipment_id=sid, field="current_service_id"))
            continue
        choices.append(Choice(shipment, baseline, cheapest(evaluations, shipment.current_service_id), evaluations))

    groups = []
    partitions = defaultdict(list)
    for choice in choices:
        group = group_for((choice.shipment.shipment_id,), choice.selected)
        if choice.shipment.consolidation_allowed:
            partitions[consolidation_key(choice.shipment)].append(group)
        else:
            groups.append(group)
    for key in sorted(partitions):
        current = sorted(partitions[key], key=lambda g: g.members)
        while True:
            candidates = []
            for left, right in combinations(current, 2):
                members = tuple(sorted(left.members + right.members))
                shipments = tuple(lookup[sid] for sid in members)
                packages = tuple(p for sid in members for p in by_shipment[sid])
                chosen = cheapest(alternatives(shipments, packages, data.tariffs, config))
                if chosen is None:
                    continue
                gain = left.selected.trace.total_cents + right.selected.trace.total_cents - chosen.trace.total_cents
                if gain >= 1:
                    pair_key = tuple(sorted((left.members, right.members)))
                    candidates.append((-gain, pair_key, chosen.service_id, chosen.tariff_id, left, right, chosen))
            if not candidates:
                break
            winner = min(candidates, key=lambda c: c[:4])
            left, right, chosen = winner[4:]
            current = [g for g in current if g is not left and g is not right]
            current.append(group_for(left.members + right.members, chosen))
            current.sort(key=lambda g: g.members)
        groups.extend(current)
    result = AnalysisResult(data, config, signature, tuple(choices), tuple(sorted(groups, key=lambda g: g.members)), tuple(exclusions), tuple(issues))
    verify_invariants(result)
    return result


def verify_invariants(result: AnalysisResult) -> None:
    ids = [c.shipment.shipment_id for c in result.choices]
    flattened = [sid for g in result.groups for sid in g.members]
    if Counter(ids) != Counter(flattened) or len(ids) != len(set(ids)):
        raise AssertionError("Popolazione non conservata esattamente una volta.")
    expected = Counter(p.package_id for p in result.data.packages if p.shipment_id in set(ids))
    actual = Counter(p.package_id for group in result.groups for p in group.selected.trace.packages)
    if actual != expected:
        raise AssertionError("Colli persi o duplicati.")
    c0 = sum(c.baseline.trace.total_cents for c in result.choices)
    c1 = sum(c.selected.trace.total_cents for c in result.choices)
    c2 = sum(g.selected.trace.total_cents for g in result.groups)
    if not c2 <= c1 <= c0:
        raise AssertionError("Costi non monotoni.")
    if any(not g.selected.feasible or g.proposal_id != proposal_id(g.members) for g in result.groups):
        raise AssertionError("Gruppo finale non ammissibile o ID incoerente.")
