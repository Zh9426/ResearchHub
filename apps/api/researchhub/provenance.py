"""Validate saved GitHub code references without making external requests."""

import re
from urllib.parse import urlsplit


def github_link(value, kind="repository"):
    if value is None:
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("代码来源必须是不含凭据、查询或锚点的 HTTPS GitHub 链接")
    suffix = (
        ""
        if kind == "repository"
        else (r"/issues/[1-9][0-9]*" if kind == "issue" else r"/pull/[1-9][0-9]*")
    )
    path = parsed.path.rstrip("/")
    if not re.fullmatch(
        r"/[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}" + suffix, path
    ):
        raise ValueError("GitHub 链接格式不正确")
    owner, repo = path.split("/")[1:3]
    if owner.endswith("-") or repo in {".", ".."}:
        raise ValueError("GitHub 仓库名称不正确")
    if kind == "repository" and repo.endswith(".git"):
        path = path[:-4]
        if path.split("/")[-1] in {"", ".", ".."}:
            raise ValueError("GitHub 仓库名称不正确")
    return "https://github.com" + path


def same_repository(repository, link):
    return (
        not repository
        or not link
        or "/".join(link.split("/")[:5]).lower() == repository.lower()
    )


def git_branch(value):
    if value is None:
        return None
    if (
        not value
        or len(value) > 255
        or value.startswith(("/", "-"))
        or value.endswith(("/", "."))
        or ".." in value
        or "@{" in value
        or "//" in value
        or value == "@"
        or any(
            part.endswith(".lock") or part.startswith(".") for part in value.split("/")
        )
        or re.search(r"[\x00-\x20\x7f~^:?*\[\\]", value)
    ):
        raise ValueError("Git 分支名称不正确")
    return value
