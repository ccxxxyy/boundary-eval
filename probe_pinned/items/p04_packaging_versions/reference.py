from packaging.version import InvalidVersion, Version


def _parsed(tags):
    for tag in tags:
        try:
            yield Version(tag), tag
        except InvalidVersion:
            continue


def stable_versions(tags):
    keep = [(v, t) for v, t in _parsed(tags) if not v.is_prerelease and not v.is_devrelease]
    return [t for _, t in sorted(keep, key=lambda pair: pair[0])]


def newest_stable(tags):
    found = stable_versions(tags)
    return found[-1] if found else None
