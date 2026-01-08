from datetime import UTC, datetime

import httpx

from src.config import get_settings
from src.models import EnrichedRepo, TrendingRepo

GITHUB_API_BASE = "https://api.github.com"


def _get_headers() -> dict[str, str]:
    settings = get_settings()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


def _calculate_days_since_push(pushed_at: datetime | None) -> int | None:
    if not pushed_at:
        return None
    now = datetime.now(UTC)
    if pushed_at.tzinfo is None:
        pushed_at = pushed_at.replace(tzinfo=UTC)
    return (now - pushed_at).days


async def enrich_single_repo(
    client: httpx.AsyncClient,
    repo: TrendingRepo,
) -> EnrichedRepo:
    url = f"{GITHUB_API_BASE}/repos/{repo.full_name}"

    try:
        response = await client.get(url)
        if response.status_code == 404:
            return EnrichedRepo(**repo.model_dump())
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError:
        return EnrichedRepo(**repo.model_dump())

    pushed_at = None
    if data.get("pushed_at"):
        pushed_at = datetime.fromisoformat(data["pushed_at"].replace("Z", "+00:00"))

    created_at = None
    if data.get("created_at"):
        created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))

    updated_at = None
    if data.get("updated_at"):
        updated_at = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))

    days_since_push = _calculate_days_since_push(pushed_at)
    is_active = days_since_push is None or days_since_push <= 30

    license_info = data.get("license")
    license_name = license_info.get("spdx_id") if license_info else None

    return EnrichedRepo(
        rank=repo.rank,
        github_id=data.get("id"),
        owner=repo.owner,
        name=repo.name,
        full_name=repo.full_name,
        url=repo.url,
        description=data.get("description") or repo.description,
        language=data.get("language") or repo.language,
        stars=data.get("stargazers_count", repo.stars),
        stars_today=repo.stars_today,
        forks=data.get("forks_count", repo.forks),
        open_issues=data.get("open_issues_count", 0),
        watchers=data.get("subscribers_count", 0),
        created_at=created_at,
        updated_at=updated_at,
        pushed_at=pushed_at,
        license=license_name,
        topics=data.get("topics", []),
        default_branch=data.get("default_branch", "main"),
        has_wiki=data.get("has_wiki", False),
        has_discussions=data.get("has_discussions", False),
        archived=data.get("archived", False),
        days_since_push=days_since_push,
        is_active=is_active,
    )


async def enrich_repos(
    repos: list[TrendingRepo],
    concurrency: int = 5,
) -> list[EnrichedRepo]:
    import asyncio

    enriched: list[EnrichedRepo] = []
    semaphore = asyncio.Semaphore(concurrency)

    async def enrich_with_limit(client: httpx.AsyncClient, repo: TrendingRepo) -> EnrichedRepo:
        async with semaphore:
            await asyncio.sleep(0.1)
            return await enrich_single_repo(client, repo)

    async with httpx.AsyncClient(headers=_get_headers(), timeout=30.0) as client:
        tasks = [enrich_with_limit(client, repo) for repo in repos]
        enriched = await asyncio.gather(*tasks)

    return list(enriched)
