"""Every number in the README and memo must come from reports/headline_metrics.json."""

import json
from pathlib import Path

import pytest

from scripts.render_docs import PAIRS, render

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "reports" / "headline_metrics.json"


@pytest.mark.skipif(not METRICS.exists(), reason="no headline metrics yet")
@pytest.mark.parametrize("template,output", PAIRS, ids=["README", "memo", "experiment_plan"])
def test_rendered_docs_match_the_metrics(template, output):
    data = json.loads(METRICS.read_text())
    assert output.read_text() == render(template.read_text(), data), f"{output.name} is stale: run `make docs`"
