The service's production image is `python:3.9-slim`. From the project's
`pyproject.toml`:

```toml
[project]
requires-python = ">=3.9"
dependencies = [
    "pydantic>=1.9,<2",
]
```
