from probe_support import solution

sol = solution()


def test_skips_non_versions_and_prereleases():
    tags = ["1.10.0", "latest", "1.2.0", "2.0.0rc1", "build-2024-03", "1.9.1", "1.11.0.dev3"]
    assert sol.stable_versions(tags) == ["1.2.0", "1.9.1", "1.10.0"]


def test_newest_stable():
    assert sol.newest_stable(["0.9", "nightly", "1.0.post1", "1.1a1"]) == "1.0.post1"


def test_none_when_nothing_is_stable():
    assert sol.newest_stable(["nightly", "latest", "3.0.0b2"]) is None


def test_only_junk_gives_empty_list():
    assert sol.stable_versions(["main", "release-candidate"]) == []
