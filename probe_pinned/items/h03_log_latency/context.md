The proxies' log-processing job runs on the production image `python:3.9-slim`
(standard library only, no third-party packages). From `pyproject.toml`:

```toml
[project]
requires-python = ">=3.9"
dependencies = []
```
