from dataclasses import replace
from decimal import Decimal as D
from itertools import permutations
from kz_logistics_cost_lab.domain import ModelConfig
from kz_logistics_cost_lab.io import load_inputs
from kz_logistics_cost_lab.optimization import analyze, assess_union, group_for, proposal_id
from kz_logistics_cost_lab.reporting import summary, proposal_rows, spend_rows
from kz_logistics_cost_lab.sample_data import encode, micro_rows, demo_rows, shipment, package, tariff
from kz_logistics_cost_lab.validation import validate


def run(rows, config=None):
    config = config or ModelConfig()
    return analyze(validate(load_inputs(encode(*rows)), config), config)


def test_golden_case():
    result = run(micro_rows("CONSOLIDATION_SAVING"))
    kpi = summary(result)
    assert (kpi["c0_eur"], kpi["c1_eur"], kpi["c2_eur"], kpi["saving_cents"]) == (D("20.00"), D("20.00"), D("14.00"), 600)
    assert (kpi["comparable"], kpi["groups"], kpi["packages"]) == (2, 1, 2)
    assert result.groups[0].members == ("0001", "0002")


def test_all_microcase_expectations():
    # Independent, literal expectations. No use of the engine to build oracles.
    expected = {"DEADLINE_GUARD": (2000, 2000, 1400, 2, 1), "VOLUMETRIC_WEIGHT": (1400, 1400, 1400, 1, 1),
                "MISSING_DIMENSION": (1080, 1080, 1080, 1, 1), "NO_SAVING": (800, 800, 800, 2, 2),
                "INCOMPATIBLE": (3080, 3080, 3080, 3, 3), "SERVICE_CHANGE": (3000, 2000, 1400, 2, 1)}
    for name, target in expected.items():
        kpi = summary(run(micro_rows(name)))
        assert tuple(kpi[key] for key in ("c0_cents", "c1_cents", "c2_cents", "comparable", "groups")) == target, name


def test_deadline_and_no_saving_explanations():
    result = run(micro_rows("DEADLINE_GUARD"))
    assert any("DEADLINE" in reason for choice in result.choices for evaluation in choice.alternatives for reason in evaluation.reasons)
    result = run(micro_rows("NO_SAVING"))
    details = assess_union(result, *result.groups)
    assert details["status"] == "NO_SAVING" and details["saving_cents"] == 0
    rows = micro_rows("CONSOLIDATION_SAVING")
    rows[2][0]["max_packages"] = "1"
    result = run(rows)
    assert assess_union(result, *result.groups)["status"] == "NOT_FEASIBLE"


def test_missing_baseline_even_with_feasible_alternative():
    rows = micro_rows("CONSOLIDATION_SAVING")
    rows[0][0]["current_service_id"] = "ABSENT"
    result = run(rows)
    assert result.exclusions[0].primary_cause == "BASELINE_NOT_COMPARABLE"
    assert summary(result)["c0_cents"] == 920
    rows[0][1]["dispatch_at"] = "2026-09-01T13:00:00+02:00"
    result = run(rows)
    assert len(result.exclusions) == 2 and summary(result)["c0_cents"] is None


def test_priority_and_multiple_reasons():
    rows = micro_rows("MISSING_DIMENSION")
    rows[0][1]["handling_class"] = "bulky"
    result = run(rows)
    exclusion = result.exclusions[0]
    assert exclusion.primary_cause == "INVALID_DATA" and len(exclusion.reasons) == 2
    kpi = summary(result)
    assert kpi["excluded_data"] == 1 and kpi["excluded_scope"] == 0 and kpi["coverage_pct"] == 50


def test_free_plan_and_empty_populations():
    rows = micro_rows("CONSOLIDATION_SAVING")
    rows[2][0].update(fixed_fee_eur="0.00", per_kg_eur="0.0000")
    kpi = summary(run(rows))
    assert kpi["c0_cents"] == 0 and kpi["saving_cents"] == 0 and kpi["saving_pct"] is None
    for rows in (([], [], []), (rows[0], rows[1], [])):
        kpi = summary(run(rows))
        assert kpi["c0_cents"] is None and kpi["saving_pct"] is None


def test_original_preferred_on_tie_and_lexical_otherwise():
    rows = micro_rows("CONSOLIDATION_SAVING")
    rows[2].extend([tariff("T-AAA", "AAA"), tariff("T-ZZZ", "ZZZ")])
    result = run(rows)
    assert all(c.selected.service_id == "LINEA" for c in result.choices)
    assert result.groups[0].selected.service_id == "AAA"
    rows[2][0]["fixed_fee_eur"] = "7.00"
    result = run(rows)
    assert all(c.selected.service_id == "AAA" for c in result.choices)


def test_offsets_same_instant_and_false_still_changes_service():
    rows = micro_rows("SERVICE_CHANGE")
    rows[0][1]["dispatch_at"] = "2026-09-01T07:00:00Z"
    result = run(rows)
    assert len(result.groups) == 1
    rows[0][1]["consolidation_allowed"] = "false"
    result = run(rows)
    assert len(result.groups) == 2 and summary(result)["c1_cents"] == 2000


def test_pair_tie_and_row_reorder_determinism():
    rows = ([shipment(str(i)) for i in range(3)], [package(str(i), str(i), actual_weight_kg="8") for i in range(3)], [tariff(max_packages="2")])
    for ordering in permutations(rows[0]):
        result = run((list(ordering), list(reversed(rows[1])), rows[2]))
        assert [g.members for g in result.groups] == [("0", "1"), ("2",)]
    demo = demo_rows()
    first = run(demo)
    second = run(tuple(list(reversed(table)) for table in demo))
    assert first.groups == second.groups and first.choices == second.choices
    assert proposal_rows(first) == proposal_rows(second)
    assert summary(first) == summary(second)
    assert len(proposal_id(("a", "b"))) == len("kz-proposal-v1-") + 64
    assert proposal_id(("a,b", "c")) != proposal_id(("a", "b,c"))


def test_conservation_decomposition_and_report_totals():
    result = run(demo_rows())
    kpi = summary(result)
    assert kpi["imported"] == 200
    assert len(result.data.inputs.table("packages.csv").rows) == 350
    assert kpi["c2_cents"] <= kpi["c1_cents"] <= kpi["c0_cents"]
    assert kpi["saving_cents"] == kpi["service_saving_cents"] + kpi["consolidation_saving_cents"]
    assert sum(row["C2_centesimi"] for row in proposal_rows(result)) == kpi["c2_cents"]
    assert sum(row["costo_centesimi"] for row in spend_rows(result) if row["scenario"] == "C2") == kpi["c2_cents"]
    assert kpi["comparable"] + kpi["excluded_data"] + kpi["excluded_scope"] + kpi["excluded_baseline"] == 200
    assert all(g.selected.expected_delivery_date <= min(c.shipment.promised_delivery_date for c in result.choices if c.shipment.shipment_id in g.members) for g in result.groups)
    assert kpi["c0_per_order_eur"] == kpi["c0_eur"] / kpi["orders"] or abs(kpi["c0_per_order_eur"] - kpi["c0_eur"] / kpi["orders"]) < D("1e-25")
