"""Select stable, releasable versions from git tags."""

from packaging.version import InvalidVersion, Version

__all__ = ["stable_versions", "newest_stable"]


def stable_versions(tags: list[str]) -> list[str]:
    """Return stable PEP 440 version tags, sorted from lowest to highest.

    Pre-releases and development releases are excluded. Invalid version tags
    are ignored, and valid tags are returned as their original strings.
    """
    parsed: list[tuple[Version, str]] = []

    for tag in tags:
        try:
            version = Version(tag)
        except InvalidVersion:
            continue

        if version.is_prerelease or version.is_devrelease:
            continue

        parsed.append((version, tag))

    parsed.sort(key=lambda item: item[0])
    return [tag for _, tag in parsed]


def newest_stable(tags: list[str]) -> str | None:
    """Return the highest stable version tag, or None if there is none."""
    versions = stable_versions(tags)
    return versions[-1] if versions else None
