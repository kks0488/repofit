import asyncio
import calendar
import math
import os
import re
import subprocess
from datetime import UTC, date, datetime

import httpx

from src.models import TrendingRepo
from src.utils import build_github_api_headers

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
    return build_github_api_headers(user_agent="RepoFitBot/0.1")


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


_NEED_STOPWORDS = {
    "a", "an", "and", "as", "at", "be", "by", "can", "for", "from", "given",
    "i", "in", "is", "it", "me", "my", "of", "on", "or", "our", "repo",
    "repos", "repository", "scripts", "the", "to", "tool", "tools", "use", "via",
    "want", "with", "without", "automate", "automation", "bulk", "generation", "web", "api",
}


def _six_months_ago(today: date) -> date:
    month = today.month - 6
    year = today.year
    if month <= 0:
        month += 12
        year -= 1
    return date(year, month, min(today.day, calendar.monthrange(year, month)[1]))


def build_need_queries(need: str, today: date | None = None) -> tuple[list[str], list[str]]:
    """Turn a need into a few bounded searches, retaining product/domain names."""
    words = re.findall(r"[a-z0-9][a-z0-9.+-]*", need.lower())
    terms = list(dict.fromkeys(word for word in words if word not in _NEED_STOPWORDS))
    if not terms:
        raise ValueError("Describe a product or task, for example 'Google Flow image generation'.")
    domains = [word for word in terms if "." in word]
    # Product phrases and domains prevent popular but unrelated keyword matches.
    if domains:
        anchor = domains[0].split(".")[0]
        searches = [f'"{domains[0]}" in:name,description,readme', f"{anchor} web in:name,description,readme"]
        terms = list(dict.fromkeys([anchor] + terms))
    elif "google" in terms and "flow" in terms:
        searches = ['"Google Flow" in:name,description,readme', '"flow.google.com" in:name,description,readme']
    else:
        searches = [" ".join(terms[:3]) + " in:name,description,readme"]
        if len(terms) > 1:
            searches.append(" ".join(terms[:2]) + " in:name,description,readme")
    cutoff = _six_months_ago(today or datetime.now(UTC).date())
    filters = f"stars:>=300 pushed:>={cutoff.isoformat()} archived:false fork:false"
    return [f"{query} {filters}" for query in dict.fromkeys(searches)], terms


def _need_score(item: dict, terms: list[str], need: str, readme: str = "") -> float:
    name = item.get("name", "").lower()
    description = (item.get("description") or "").lower()
    metadata = f"{name} {description} {' '.join(item.get('topics') or [])}"
    body = readme.lower()
    score = 0.0
    for term in terms:
        score += 10 * (term in name) + 7 * (term in metadata) + 2 * (term in body)
    if "google" in terms and "flow" in terms:
        score += 30 * ("google flow" in metadata) + 20 * ("google flow" in body)
    if any(word in need.lower() for word in ("automate", "scripts", "without api")):
        score += 15 * ("api" in name) + 8 * ("web" in name)
        score += sum(8 for word in ("web2api", "web-to-api", "reverse-engineer", "browser", "automation") if word in metadata)
        score += sum(3 for word in ("python", "script", "cookie", "no api key") if word in body)
    if any(word in need.lower() for word in ("image", "bulk")):
        score += sum(5 for word in ("image", "batch", "bulk", "concurrent", "图片", "图像", "批量") if word in metadata)
        score += sum(2 for word in ("image", "batch", "bulk", "图片", "批量") if word in body)
        score += 12 * ("browser bridge" in body)
        score += 8 * bool(re.search(r"\b(batch|bulk|concurrent)\b", body))
        if re.search(r"animation style|video prompts|prompt (library|collection)|style library", metadata):
            score -= 60
    if any(word in name for word in ("awesome", "cheat-sheet", "resources", "prompts")):
        score -= 30  # A directory/prompt collection is weaker than an implementation.
    return score + math.log10(max(item.get("stargazers_count", 0), 1))


def _fit_evidence(item: dict, readme: str, terms: list[str], need: str) -> str:
    description = " ".join((item.get("description") or "").split())
    if "image" not in need.lower() and re.search(
        r"reverse-engineer|web.{0,30}(api|interface)|browser|automation", description, re.I,
    ):
        return description[:210] + ("…" if len(description) > 210 else "")
    feature_words = ["reverse-engineer", "python", "wrapper", "browser", "script", "cookie"]
    if "image" in need.lower():
        feature_words = ["image generation", "batch", "bulk", "concurrent", "图片生成", "批量", "并发"]
    evidence = []
    for line in readme.splitlines():
        if any(skip in line.lower() for skip in ("<", "](", "shields.io", "sponsor", "thanks to", "useapi.net")):
            continue
        clean = re.sub(r"[#*`>]", "", line).strip()
        if not 30 <= len(clean) <= 350:
            continue
        score = sum(3 for word in feature_words if word in clean.lower())
        if "image" in need.lower():
            score += 6 * ("image generation" in clean.lower() or "图片生成" in clean)
        score += sum(term in clean.lower() for term in terms)
        if score >= 3:
            evidence.append((score, clean))
    if evidence:
        best = max(evidence, key=lambda pair: pair[0])[1]
        return "README: " + best[:210] + ("…" if len(best) > 210 else "")
    if description:
        return "Related match; " + description[:190] + ("…" if len(description) > 190 else "")
    for line in readme.splitlines():
        clean = re.sub(r"[#*`<>]", "", line).strip()
        if len(clean) >= 25 and any(term in clean.lower() for term in terms):
            return "README: " + clean[:200]
    return "Keyword match; inspect the README to confirm the requested capability."


async def search_need(need: str, limit: int = 5, today: date | None = None) -> list[dict]:
    """Search maintained, popular repos and rank their documented fit without AI."""
    queries, terms = build_need_queries(need, today=today)
    cutoff = _six_months_ago(today or datetime.now(UTC).date()).isoformat()
    headers = _get_headers()
    if "Authorization" not in headers:
        token = os.environ.get("GH_TOKEN", "")
        if not token:
            try:
                token = subprocess.run(
                    ["gh", "auth", "token"], capture_output=True, text=True, check=True,
                    timeout=10,
                ).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                pass
        if token:
            headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
        candidates: dict[str, dict] = {}
        for query in queries:
            response = await client.get(GITHUB_SEARCH_URL, params={
                "q": query, "sort": "stars", "order": "desc", "per_page": 40,
            })
            response.raise_for_status()
            for item in response.json().get("items", []):
                if (item.get("archived") or item.get("fork")
                        or (item.get("stargazers_count") or 0) < 300
                        or (item.get("pushed_at") or "")[:10] < cutoff):
                    continue
                candidates[item["full_name"]] = item

        shortlist = sorted(candidates.values(), key=lambda item: _need_score(item, terms, need), reverse=True)[:20]
        semaphore = asyncio.Semaphore(5)

        async def read_readme(item: dict) -> tuple[dict, str]:
            async with semaphore:
                try:
                    response = await client.get(
                        f"https://api.github.com/repos/{item['full_name']}/readme",
                        headers={"Accept": "application/vnd.github.raw+json"},
                    )
                    response.raise_for_status()
                    return item, response.text[:100_000]
                except httpx.HTTPError:
                    return item, ""

        documented = await asyncio.gather(*(read_readme(item) for item in shortlist))

    if "google" in terms and "flow" in terms:
        documented = [
            (item, readme) for item, readme in documented
            if any(phrase in f"{item.get('description') or ''} {readme}".lower()
                   for phrase in ("google flow", "flow.google.com"))
            and re.search(r"flow|browser|webai", f"{item.get('name', '')} {item.get('description') or ''}", re.I)
            and not re.search(
                r"awesome|cheat-sheet|animation style|video prompts|prompt (library|collection)|style library",
                f"{item.get('name', '')} {item.get('description') or ''}", re.I,
            )
        ]
    documented.sort(key=lambda pair: _need_score(pair[0], terms, need, pair[1]), reverse=True)
    return [{
        "full_name": item["full_name"],
        "url": item["html_url"],
        "stars": item["stargazers_count"],
        "pushed_at": item["pushed_at"],
        "license": (item.get("license") or {}).get("spdx_id") or "UNKNOWN",
        "fit": _fit_evidence(item, readme, terms, need),
    } for item, readme in documented[:max(1, min(limit, 5))]]
