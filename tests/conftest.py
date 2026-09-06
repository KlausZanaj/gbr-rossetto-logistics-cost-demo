import pytest
from kz_logistics_cost_lab.domain import ModelConfig
from kz_logistics_cost_lab.io import load_inputs
from kz_logistics_cost_lab.sample_data import encode, micro_rows
from kz_logistics_cost_lab.validation import validate


@pytest.fixture
def config():
    return ModelConfig()


@pytest.fixture
def rows():
    return micro_rows("CONSOLIDATION_SAVING")


@pytest.fixture
def data(rows, config):
    return validate(load_inputs(encode(*rows)), config)
