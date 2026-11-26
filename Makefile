PYTHON ?= python

RAW     := data/raw/wow-full.parquet
FIXTURE := data/fixture/wow-fixture.parquet

.PHONY: all data analysis docs test lint fixture fixture-run clean

## Full run: download, analyze, write docs, test
all: data analysis docs test

data:
	$(PYTHON) ingest/download.py --out $(RAW)

analysis:
	$(PYTHON) scripts/run_analysis.py --raw $(RAW) --out reports

docs:
	$(PYTHON) scripts/render_docs.py

test:
	$(PYTHON) -m pytest -q

lint:
	ruff check .
	ruff format --check .

## Same pipeline on synthetic data (what CI runs)
fixture:
	$(PYTHON) scripts/make_fixture.py --out $(FIXTURE)

fixture-run: fixture
	$(PYTHON) scripts/run_analysis.py --raw $(FIXTURE) --out data/fixture_reports --interim data/fixture_interim --quick

clean:
	rm -rf data/interim data/fixture data/fixture_reports data/fixture_interim
