PY ?= python

.PHONY: install validate-grader demo reproduce dev-run frontier-run models-check clean

install:
	uv sync --extra dev || $(PY) -m pip install -e ".[dev]"

# Proves the grader has no false passes and no false failures. No API key,
# no network, no cost.
validate-grader:
	$(PY) -m pytest -q

# The finding in one command: code that passes its own self-check and is still
# not crash-safe, with the counterexample printed.
demo:
	$(PY) -m faultline.grade --task tasks/t01_idempotent_charge \
		--solution tasks/t01_idempotent_charge/reference.py
	@echo ""
	$(PY) -m faultline.grade --task tasks/t01_idempotent_charge \
		--solution tasks/t01_idempotent_charge/broken/b01_fresh_key_per_call.py || true

# Everything a judge needs, from the shipped response cache. Offline and free.
reproduce: validate-grader demo
	$(PY) -m faultline.run_eval --set frontier --offline

models-check:
	$(PY) -m faultline.models_check

dev-run:
	$(PY) -m faultline.run_eval --set dev --seeds 1

frontier-run:
	$(PY) -m faultline.run_eval --set frontier

clean:
	rm -rf .pytest_cache results/solutions
