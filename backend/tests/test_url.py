from __future__ import annotations

import pytest

from app.github.errors import InvalidRepositoryURLError
from app.github.url import RepositoryRef, parse_repository_ref


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("octocat/Hello-World", ("octocat", "Hello-World")),
        ("  octocat/Hello-World  ", ("octocat", "Hello-World")),
        ("https://github.com/octocat/Hello-World", ("octocat", "Hello-World")),
        ("http://github.com/octocat/Hello-World/", ("octocat", "Hello-World")),
        ("https://www.github.com/octocat/Hello-World", ("octocat", "Hello-World")),
        ("github.com/octocat/Hello-World", ("octocat", "Hello-World")),
        ("https://github.com/octocat/Hello-World.git", ("octocat", "Hello-World")),
        ("https://github.com/octocat/Hello-World/tree/main/docs", ("octocat", "Hello-World")),
        ("https://github.com/octocat/Hello-World?tab=readme#top", ("octocat", "Hello-World")),
        ("git@github.com:octocat/Hello-World.git", ("octocat", "Hello-World")),
        ("ssh://git@github.com/octocat/Hello-World.git", ("octocat", "Hello-World")),
        ("pallets/flask.ext", ("pallets", "flask.ext")),
        ("a-b-c/repo_name.v2", ("a-b-c", "repo_name.v2")),
    ],
)
def test_parses_supported_formats(raw: str, expected: tuple[str, str]) -> None:
    ref = parse_repository_ref(raw)
    assert (ref.owner, ref.name) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "octocat",
        "https://github.com/octocat",
        "https://gitlab.com/octocat/Hello-World",
        "ftp://github.com/octocat/Hello-World",
        "-bad/repo",
        "bad-/repo",
        "dou--ble/repo",
        "owner/..",
        "owner/re po",
        "a" * 40 + "/repo",
        "https://github.com/" + "x" * 600,
    ],
)
def test_rejects_invalid_references(raw: str) -> None:
    with pytest.raises(InvalidRepositoryURLError):
        parse_repository_ref(raw)


def test_key_is_case_insensitive() -> None:
    assert (
        RepositoryRef("OctoCat", "Hello-World").key == RepositoryRef("octocat", "hello-world").key
    )
    assert RepositoryRef("OctoCat", "Hello-World").full_name == "OctoCat/Hello-World"
