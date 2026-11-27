"""Parsing of user-supplied GitHub repository references."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.github.errors import InvalidRepositoryURLError

_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_SSH_RE = re.compile(r"^(?:ssh://)?git@github\.com[:/](?P<path>.+)$", re.IGNORECASE)
_ALLOWED_HOSTS = {"github.com", "www.github.com"}


@dataclass(frozen=True, slots=True)
class RepositoryRef:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def key(self) -> str:
        """Case-insensitive identity: GitHub treats owner/name case-insensitively."""
        return self.full_name.lower()


def parse_repository_ref(raw: str) -> RepositoryRef:
    """Parse ``owner/repo``, HTTPS, SSH and deep-link GitHub URLs into a :class:`RepositoryRef`.

    Examples of accepted input::

        octocat/Hello-World
        https://github.com/octocat/Hello-World
        github.com/octocat/Hello-World/tree/main/docs
        git@github.com:octocat/Hello-World.git
    """
    value = (raw or "").strip()
    if not value:
        raise InvalidRepositoryURLError("Repository URL must not be empty.")
    if len(value) > 500:
        raise InvalidRepositoryURLError("Repository URL is too long.")

    path = _extract_path(value)
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) < 2:
        raise InvalidRepositoryURLError(
            f"'{raw}' does not point to a repository. Expected 'owner/repository'."
        )

    owner, name = segments[0], segments[1]
    name = name.removesuffix(".git")

    if not _OWNER_RE.fullmatch(owner):
        raise InvalidRepositoryURLError(f"'{owner}' is not a valid GitHub owner name.")
    if not _REPO_RE.fullmatch(name) or name in {".", ".."}:
        raise InvalidRepositoryURLError(f"'{name}' is not a valid GitHub repository name.")

    return RepositoryRef(owner=owner, name=name)


def _extract_path(value: str) -> str:
    ssh_match = _SSH_RE.match(value)
    if ssh_match:
        return ssh_match.group("path")

    has_scheme = "://" in value
    looks_like_host = value.lower().startswith(("github.com/", "www.github.com/"))
    if not has_scheme and not looks_like_host:
        # Plain "owner/repo" shorthand.
        return value

    parts = urlsplit(value if has_scheme else f"https://{value}")
    if parts.scheme not in {"http", "https"}:
        raise InvalidRepositoryURLError(f"Unsupported URL scheme '{parts.scheme}'.")
    host = (parts.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        raise InvalidRepositoryURLError(
            f"Only github.com repositories are supported, got host '{host or value}'."
        )
    return parts.path
