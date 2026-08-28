# A3 Agent Registry & Governance - developer tasks.
# Everything below runs offline on the SDK-free 'local' profile (SQLite catalog, no GCP SDKs).

.DEFAULT_GOAL := help
PY ?= python3
PY := $(if $(wildcard .venv/bin/python),.venv/bin/python,$(PY))
PORT ?= 8083
IMAGE ?= agent-registry:latest
# The default profile is 'local' everywhere (settings.yaml too); production sets HRZ_REGISTRY_PROFILE=gcp explicitly.
export HRZ_REGISTRY_PROFILE ?= local
# The no-auth local dev server binds loopback; override deliberately to expose it.
API_HOST ?= 127.0.0.1

.PHONY: help venv install run lint format typecheck test eval check smoke demo demo-selftest portability-demo docker-build clean

help: ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

venv: ## Create a local virtualenv in .venv.
	$(PY) -m venv .venv
	@echo "Activate with: source .venv/bin/activate"

install: ## Install the package with dev extras (core deps only, no GCP SDKs).
	$(PY) -m pip install -e ".[dev]"

run: ## Run the service locally (local profile) on $(PORT).
	HRZ_REGISTRY_PROFILE=local uvicorn agent_registry.api.app:app \
		--host $(API_HOST) --port $(PORT) --reload

lint: ## ruff check + format check.
	ruff check src tests eval scripts/demo_selftest.py scripts/portability_demo.py scripts/rename_fork.py
	ruff format --check src tests eval scripts/demo_selftest.py scripts/portability_demo.py scripts/rename_fork.py

format: ## Auto-format and auto-fix with ruff.
	ruff check --fix src tests eval
	ruff format src tests eval

typecheck: ## Static type check with mypy.
	mypy src

test: ## Run the offline pytest suite (local profile).
	pytest -m 'not integration' -q

eval: ## Run the offline promotion eval gate (exit non-zero on fail).
	$(PY) eval/run_eval.py

smoke: ## End-to-end local smoke: register a card via the CLI, then list it.
	HRZ_REGISTRY_PROFILE=local HRZ_REGISTRY_LOCAL_DB=$${TMPDIR:-/tmp}/hrz-smoke.db \
		agent-registry register --card '{"name":"compliance-advisory","description":"C1 Compliance Assistant","url":"https://compliance-advisory.asia-southeast1.example/a2a","version":"1.0.0","provider":"compliance-advisory","skills":[{"id":"answer","name":"Grounded compliance Q&A","description":"Cited answers."}]}'
	HRZ_REGISTRY_PROFILE=local HRZ_REGISTRY_LOCAL_DB=$${TMPDIR:-/tmp}/hrz-smoke.db agent-registry list

demo: ## Run the guided offline walkthrough (DEMO_AUTO=1 self-runs; see scripts/README.md).
	HRZ_REGISTRY_PROFILE=local PYTHONPATH=src $(PY) scripts/registry_demo.py

demo-selftest: ## Run the real demo unattended and assert every transcript outcome.
	HRZ_REGISTRY_PROFILE=local PYTHONPATH=src $(PY) scripts/demo_selftest.py

portability: portability-demo ## Standard fleet alias for the executable portability proof.

portability-demo: ## Run the bounded executable portability proof.
	HRZ_REGISTRY_PROFILE=local PYTHONPATH=src $(PY) scripts/portability_demo.py

plugin: ## Render the Agent Plugins 1.0.0 directory from this repo's own declarations.
	python scripts/render_plugin.py --dest dist/plugin

mcp-serve: ## Serve the read-only discovery catalog over MCP 2026-07-28 (stdio).
	python -m agent_registry.mcp

check: lint typecheck test eval demo-selftest portability-demo plugin ## Full offline quality gate.

docker-build: ## Build the container image.
	docker build -t $(IMAGE) .

clean: ## Remove caches and build artefacts.
	rm -rf .pytest_cache .ruff_cache .mypy_cache dist build *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
