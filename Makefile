PY ?= python

.PHONY: install validate-grader matrix demo reproduce dev-run frontier-run models-check secret-scan package clean

install:
	uv sync --extra dev || $(PY) -m pip install -e ".[dev]"

# Proves the grader has no false passes and no false failures. No API key,
# no network, no cost.
validate-grader:
	$(PY) -m pytest -q

# Every task, every reference and every known-broken solution, with the
# public self-check and the fault injection side by side.
matrix:
	$(PY) -m faultline.matrix

# The finding in one command: code that passes its own self-check and is still
# not crash-safe, with the counterexample printed.
demo:
	$(PY) -m faultline.grade --task tasks/t03_at_least_once_ledger \
		--solution tasks/t03_at_least_once_ledger/reference.py
	@echo ""
	$(PY) -m faultline.grade --task tasks/t03_at_least_once_ledger \
		--solution tasks/t03_at_least_once_ledger/broken/b01_mark_then_apply.py || true
	@echo ""
	$(PY) -m faultline.grade --task tasks/t03_at_least_once_ledger \
		--solution tasks/t03_at_least_once_ledger/broken/b02_apply_then_mark.py || true

# Everything a judge needs, from the shipped response cache. Offline and free.
reproduce: validate-grader matrix demo
	$(PY) -m faultline.run_eval --set frontier --offline

models-check:
	$(PY) -m faultline.models_check

dev-run:
	$(PY) -m faultline.run_eval --set dev --seeds 1

frontier-run:
	$(PY) -m faultline.run_eval --set frontier

secret-scan:
	$(PY) scripts/secret_scan.py

package: secret-scan
	$(PY) scripts/package.py

clean:
	rm -rf .pytest_cache results/solutions
