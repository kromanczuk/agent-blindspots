.PHONY: setup data reproduce test lint dry-run export site site-build clean

setup:            ## install Python deps (uv) and site deps (npm)
	uv sync
	cd site && npm install

data:             ## download tau2-bench at the pinned commit (~700 MB, only needed to rerun or export)
	./scripts/fetch_tau2.sh

reproduce:        ## recompute every reported number from results/ and check them (no API keys, no download)
	uv run blindspots analyze
	uv run pytest -q

test:
	uv run pytest -q

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

dry-run:          ## exercise all three experiments end to end with stub replies (needs `make data`)
	uv run blindspots lab --dry-run --n 3
	uv run blindspots wild --dry-run --n 10
	uv run blindspots skeptic --dry-run --labels results/dry-run/wild/wild_results.csv
	uv run blindspots analyze --results results/dry-run --out results/dry-run/summary.json

export:           ## rebuild the JSON the website reads (needs `make data`)
	uv run blindspots export-site

site:             ## run the website locally
	cd site && npm run dev

site-build:
	cd site && npm run build

clean:
	rm -rf results/dry-run site/dist .pytest_cache .ruff_cache
