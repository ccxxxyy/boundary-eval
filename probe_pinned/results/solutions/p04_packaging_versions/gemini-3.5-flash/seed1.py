"""Utilities for parsing and filtering PEP 440 release versions from git tags."""

from packaging.version import InvalidVersion, Version


def stable_versions(tags: list[str]) -> list[str]:
    """Return the tags that are valid PEP 440 versions and are neither
    pre-releases nor dev releases, sorted from lowest to highest version.
    Return the original tag strings, unchanged. Tags that are not valid
    PEP 440 versions are skipped.
    """
    valid_tags: list[tuple[Version, str]] = []
    for tag in tags:
        try:
            version = Version(tag)
        except InvalidVersion:
            continue

        if not version.is_prerelease and not version.is_devrelease:
            valid_tags.append((version, tag))

    valid_tags.sort(key=lambda pair: pair[0])
    return [tag for _, tag in valid_tags]


def newest_stable(tags: list[str]) -> str | None:
    """The highest tag stable_versions would return, or None if there is
    none.
    """
    stables = stable_versions(tags)
    return stables[-1] if stables else None
