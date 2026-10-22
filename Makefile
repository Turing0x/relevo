# relevo development tasks. Compatible with GNU make 3.81 (macOS).
# Missing dev tools are skipped locally (exit 0) and are errors when CI is set.

DEV_PYTHON ?= python3.14
export PYTHONDONTWRITEBYTECODE := 1

ifeq ($(wildcard .venv/bin/python),)
PY ?= python3
else
PY ?= .venv/bin/python
endif

RUFF ?= $(if $(wildcard .venv/bin/ruff),.venv/bin/ruff,ruff)
MYPY ?= $(if $(wildcard .venv/bin/mypy),.venv/bin/mypy,mypy)
ZIZMOR ?= $(if $(wildcard .venv/bin/zizmor),.venv/bin/zizmor,zizmor)
ACTIONLINT ?= actionlint
SHELLCHECK ?= shellcheck
GITLEAKS ?= gitleaks

# $(call missing,tool): SKIP locally, fail in CI.
define missing
if [ -n "$$CI" ]; then echo "ERROR: $(1) not installed" >&2; exit 1; \
else echo "SKIP: $(1) not installed (run make install-dev)"; fi
endef

# Syntax check of every *.py and hooks/* without writing .pyc files.
define COMPILE_CHECK
import os
import sys

skip = {".git", ".claude", ".venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache", ".codeql-shadow"}
paths = []
for dirpath, dirnames, filenames in os.walk("."):
    dirnames[:] = [d for d in dirnames if d not in skip]
    paths += [os.path.join(dirpath, f) for f in filenames if f.endswith(".py")]
if os.path.isdir("hooks"):
    paths += [os.path.join("hooks", f) for f in os.listdir("hooks") if os.path.isfile(os.path.join("hooks", f))]
bad = 0
for path in sorted(paths):
    try:
        with open(path, encoding="utf-8") as handle:
            compile(handle.read(), path, "exec")
    except SyntaxError as exc:
        print("syntax error: %s: %s" % (path, exc))
        bad += 1
print("compile check: %d files, %d errors" % (len(paths), bad))
sys.exit(1 if bad else 0)
endef
export COMPILE_CHECK

.PHONY: help check lint lint-workflows typecheck test docs-check install-dev secret-scan

help: ## List the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -e 's/:.*## /\t/' | sort

check: lint lint-workflows typecheck test docs-check ## Run every check

lint: ## Hidden Unicode, syntax, ruff and shellcheck
	$(PY) scripts/check_hidden_unicode.py
	@$(PY) -c "$$COMPILE_CHECK"
	@if command -v $(RUFF) >/dev/null 2>&1; then $(RUFF) check . && $(RUFF) format --check .; else $(call missing,ruff); fi
	@if command -v $(SHELLCHECK) >/dev/null 2>&1; then $(SHELLCHECK) scripts/*.sh; else $(call missing,shellcheck); fi

lint-workflows: ## actionlint and zizmor on .github/workflows
	@if command -v $(ACTIONLINT) >/dev/null 2>&1; then $(ACTIONLINT); else $(call missing,actionlint); fi
	@if command -v $(ZIZMOR) >/dev/null 2>&1; then $(ZIZMOR) --offline .github/workflows; else $(call missing,zizmor); fi

typecheck: ## mypy (strict on scripts/)
	@if command -v $(MYPY) >/dev/null 2>&1; then \
		$(MYPY) --strict scripts/*.py && \
		$(MYPY) tests orchestrator/stats.py && \
		for hook in hooks/*; do $(MYPY) "$$hook" || exit 1; done; \
	else $(call missing,mypy); fi

test: ## Run the unittest suite
	$(PY) -m unittest discover -s tests -p 'test_*.py' -v

docs-check: ## Links, JSON Schemas and agent cards
	$(PY) scripts/check_links.py
	$(PY) scripts/check_schemas.py
	$(PY) scripts/check_agent_docs.py

install-dev: ## Create .venv and install requirements-dev.txt (needs Python >= 3.11)
	$(DEV_PYTHON) -m venv .venv
	.venv/bin/python -m pip install -r requirements-dev.txt

secret-scan: ## gitleaks over the git history
	@if ! command -v $(GITLEAKS) >/dev/null 2>&1; then $(call missing,gitleaks); \
	elif git rev-parse --verify --quiet HEAD >/dev/null 2>&1; then $(GITLEAKS) git --redact --no-banner .; \
	else echo "SKIP: no commits yet (HEAD does not exist)"; fi
