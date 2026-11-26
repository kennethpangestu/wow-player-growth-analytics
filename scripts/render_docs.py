"""Fill the README and memo templates with numbers from reports/headline_metrics.json.

Placeholders look like {{q2.tbc.lift|pct0}}: a dotted path into the JSON (list
items by index) and an optional format. Nothing in the rendered files is typed
by hand, and tests/test_docs.py fails if they drift from the JSON.

Usage: python scripts/render_docs.py [--check]
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = [
    (ROOT / "docs" / "README.template.md", ROOT / "README.md"),
    (ROOT / "docs" / "memo.template.md", ROOT / "reports" / "memo.md"),
    (ROOT / "docs" / "experiment_plan.template.md", ROOT / "experiments" / "README.md"),
]
PATTERN = re.compile(r"\{\{\s*([\w.\-]+)\s*(?:\|\s*(\w+))?\s*\}\}")


def lookup(data, path):
    cur = data
    for part in path.split("."):
        cur = cur[int(part)] if isinstance(cur, list) else cur[part]
    return cur


def fmt(value, kind):
    if kind is None:
        return str(value)
    if value is None:
        raise ValueError("missing value")
    v = float(value) if kind not in ("date", "str") else value
    if kind == "pct0":
        return f"{v * 100:.0f}%"
    if kind == "pct1":
        return f"{v * 100:.1f}%"
    if kind == "spct0":  # signed percent
        return f"{v * 100:+.0f}%"
    if kind == "pts1":  # percentage points
        return f"{v * 100:.1f}"
    if kind == "int":
        return f"{round(v):,}"
    if kind == "num1":
        return f"{v:,.1f}"
    if kind == "num2":
        return f"{v:,.2f}"
    if kind == "x1":
        return f"{v:.1f}x"
    if kind == "k1":
        return f"{v / 1000:.1f}K"
    if kind == "m1":
        return f"{v / 1e6:.1f}M"
    if kind == "p":  # p-value
        return "< 0.001" if v < 0.001 else f"{v:.3f}"
    if kind == "date":
        from datetime import date

        d = date.fromisoformat(str(value))
        return f"{d.strftime('%B')} {d.day}, {d.year}"
    if kind == "str":
        return str(value)
    raise ValueError(f"unknown format {kind}")


def render(template, data):
    def sub(m):
        return fmt(lookup(data, m.group(1)), m.group(2))

    return PATTERN.sub(sub, template)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if a rendered file is out of date")
    args = ap.parse_args()
    data = json.loads((ROOT / "reports" / "headline_metrics.json").read_text())
    stale = []
    for tpl, out in PAIRS:
        text = render(tpl.read_text(), data)
        if args.check:
            if not out.exists() or out.read_text() != text:
                stale.append(str(out.relative_to(ROOT)))
        else:
            out.write_text(text)
            print(f"wrote {out.relative_to(ROOT)}")
    if stale:
        sys.exit(f"out of date: {', '.join(stale)} (run `make docs`)")


if __name__ == "__main__":
    main()
