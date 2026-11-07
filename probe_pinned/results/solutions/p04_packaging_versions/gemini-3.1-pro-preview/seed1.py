from packaging.version import Version, InvalidVersion

def stable_versions(tags: list[str]) -> list[str]:
    """Return the tags that are valid PEP 440 versions and are neither
    pre-releases nor dev releases, sorted from lowest to highest version.
    Return the original tag strings, unchanged. Tags that are not valid
    PEP 440 versions are skipped."""
    stable = []
    for tag in tags:
        try:
            parsed_version = Version(tag)
        except InvalidVersion:
            continue
        
        if not parsed_version.is_prerelease and not parsed_version.is_devrelease:
            stable.append((parsed_version, tag))
            
    # Sort by the parsed Version object to ensure correct PEP 440 ordering
    stable.sort(key=lambda x: x[0])
    
    return [tag for _, tag in stable]


def newest_stable(tags: list[str]) -> str | None:
    """The highest tag stable_versions would return, or None if there is
    none."""
    stable = stable_versions(tags)
    return stable[-1] if stable else None
