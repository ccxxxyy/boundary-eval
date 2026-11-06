# Results

`runs_*.jsonl` is one graded model attempt per line.
`solutions/` is the module extracted from each attempt.
`raw/` is the OpenRouter response cache, keyed by the SHA-256 of the
exact request. It is what makes `python -m faultline.run_eval --offline`
replay the published numbers for free.

`raw/` is gitignored so a key or a huge payload cannot land in git by
accident. It **must** be inside the submission ZIP. `scripts/package.py`
copies it.
