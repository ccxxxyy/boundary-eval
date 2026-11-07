# Task: pick releasable versions from git tags

A release script reads the repository's git tags and needs the list of stable
releases. Tags are messy: some are proper version numbers, some are not
versions at all (`"latest"`, `"build-2024-03"`, `"nightly"`), and some are
pre-releases. Use the `packaging` library. Write a module that defines:

```python
def stable_versions(tags: list[str]) -> list[str]:
    """Return the tags that are valid PEP 440 versions and are neither
    pre-releases nor dev releases, sorted from lowest to highest version.
    Return the original tag strings, unchanged. Tags that are not valid
    PEP 440 versions are skipped."""


def newest_stable(tags: list[str]) -> str | None:
    """The highest tag stable_versions would return, or None if there is
    none."""
```
