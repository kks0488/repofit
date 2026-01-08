import re

import httpx

from src.config import get_settings
from src.models import TrendingRepo

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"

LANGUAGE_ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "csharp": "c#",
    "cpp": "c++",
}

KNOWN_LANGUAGES = {
    "python",
    "javascript",
    "typescript",
    "go",
    "rust",
    "java",
    "kotlin",
    "swift",
    "c",
    "c++",
    "c#",
    "php",
    "ruby",
    "dart",
    "scala",
    "elixir",
    "clojure",
    "shell",
    "bash",
    "lua",
    "r",
    "objective-c",
    "objective-c++",
    "haskell",
    "erlang",
    "perl",
    "ocaml",
    "nim",
    "zig",
    "solidity",
}


def _normalize_term(term: str) -> str:
    cleaned = term.strip().lower()
    cleaned = re.sub(r"[^a-z0-9#+._-]+", "-", cleaned)
    return cleaned.strip("-")


def _pick_language(terms: list[str]) -> str | None:
    for term in terms:
        normalized = term.strip().lower()
        normalized = LANGUAGE_ALIASES.get(normalized, normalized)
        if normalized in KNOWN_LANGUAGES:
            return normalized
    return None


def build_project_queries(
    project: dict,
    min_stars: int = 50,
    max_queries: int = 3,
) -> list[str]:
    tags = project.get("tags") or []
    stack = project.get("tech_stack") or []
    name = project.get("name") or ""

    terms: list[tuple[str, str]] = []
    for tech in stack:
        norm = _normalize_term(tech)
        if norm:
            terms.append(("keyword", norm))
    for tag in tags:
        norm = _normalize_term(tag)
        if norm:
            terms.append(("topic", norm))
    if not terms and name:
        norm = _normalize_term(name)
        if norm:
            terms.append(("keyword", norm))

    base_filters = ["is:public", "archived:false"]
    if min_stars > 0:
        base_filters.append(f"stars:>={min_stars}")

    language = _pick_language(tags + stack)
    if language:
        base_filters.append(f"language:{language}")

    queries: list[str] = []
    for kind, term in terms:
        token = f"topic:{term}" if kind == "topic" else term
        queries.append(" ".join([token] + base_filters))
        if len(queries) >= max_queries:
            break

    if not queries:
        queries.append(" ".join(base_filters))

    return queries


def _get_headers() -> dict[str, str]:
    settings = get_settings()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "RepoFitBot/0.1",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


async def search_github_repos(
    query: str,
    per_page: int = 20,
    page: int = 1,
    timeout: float = 30.0,
) -> list[TrendingRepo]:
    per_page = max(1, min(per_page, 100))
    page = max(1, page)
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": per_page,
        "page": page,
    }

    async with httpx.AsyncClient(headers=_get_headers(), timeout=timeout) as client:
        response = await client.get(GITHUB_SEARCH_URL, params=params)
        response.raise_for_status()
        data = response.json()

    repos: list[TrendingRepo] = []
    items = data.get("items", [])
    for rank, item in enumerate(items, start=1):
        full_name = item.get("full_name") or ""
        if "/" not in full_name:
            continue

        owner = item.get("owner", {}).get("login") or full_name.split("/", 1)[0]
        name = item.get("name") or full_name.split("/", 1)[1]

        repos.append(
            TrendingRepo(
                rank=rank,
                github_id=item.get("id"),
                owner=owner,
                name=name,
                full_name=full_name,
                url=item.get("html_url") or f"https://github.com/{full_name}",
                description=item.get("description"),
                language=item.get("language"),
                stars=item.get("stargazers_count") or 0,
                stars_today=0,
                forks=item.get("forks_count") or 0,
            )
        )

    return repos
