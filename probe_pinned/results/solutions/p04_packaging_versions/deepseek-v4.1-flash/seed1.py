"""Utilities for extracting stable PEP 440 releases from git tags."""

from packaging.version import InvalidVersion, Version


def _stable_version(tag: str) -> Version | None:
    """Parse *tag* as a stable PEP 440 version, or return None."""
    try:
        version = Version(tag)
    except InvalidVersion:
        return None

    if version.is_prerelease or version.is_devrelease:
        return None

    return version


def stable_versions(tags: list[str]) -> list[str]:
    """Return the tags that are valid PEP 440 versions and are neither
    pre-releases nor dev releases, sorted from lowest to highest version.
    Return the original tag strings, unchanged. Tags that are not valid
    PEP 440 versions are skipped.
    """
    parsed: list[tuple[Version, str]] = []

    for tag in tags:
        version = _stable_version(tag)
        if version is not None:
            parsed.append((version, tag))

    parsed.sort(key=lambda item: item[0])
    return [tag for _, tag in parsed]


def newest_stable(tags: list[str]) -> str | None:
    """The highest tag stable_versions would return, or None if there is
    none.
    """
    versions = stable_versions(tags)
    return versions[-1] if versions else None
