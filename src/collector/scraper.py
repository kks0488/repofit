import re
from typing import Literal

import httpx
from selectolax.parser import HTMLParser

from src.models import TrendingRepo

GITHUB_TRENDING_URL = "https://github.com/trending"

SinceFilter = Literal["daily", "weekly", "monthly"]


def _parse_stars_today(text: str) -> int:
    if not text:
        return 0
    match = re.search(r"([\d,]+)\s*stars?\s*today", text.lower())
    if match:
        return int(match.group(1).replace(",", ""))
    return 0


def _parse_number(text: str) -> int:
    if not text:
        return 0
    cleaned = re.sub(r"[^\d]", "", text.strip())
    return int(cleaned) if cleaned else 0


def _build_url(language: str | None = None, since: SinceFilter = "daily") -> str:
    url = GITHUB_TRENDING_URL
    if language:
        url = f"{url}/{language.lower()}"
    return f"{url}?since={since}"


async def fetch_trending(
    language: str | None = None,
    since: SinceFilter = "daily",
    timeout: float = 30.0,
) -> list[TrendingRepo]:
    url = _build_url(language, since)

    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; GitHubTrendingBot/1.0)",
                "Accept": "text/html",
            },
            timeout=timeout,
            follow_redirects=True,
        )
        response.raise_for_status()

    parser = HTMLParser(response.text)
    repos: list[TrendingRepo] = []

    article_nodes = parser.css("article.Box-row")

    for rank, article in enumerate(article_nodes, start=1):
        h2_node = article.css_first("h2 a")
        if not h2_node:
            continue

        href = h2_node.attributes.get("href", "")
        parts = href.strip("/").split("/")
        if len(parts) < 2:
            continue

        owner, name = parts[0], parts[1]
        full_name = f"{owner}/{name}"

        desc_node = article.css_first("p")
        description = desc_node.text(strip=True) if desc_node else None

        lang_node = article.css_first('[itemprop="programmingLanguage"]')
        language_val = lang_node.text(strip=True) if lang_node else None

        star_links = article.css("a[href$='/stargazers']")
        stars = 0
        if star_links:
            stars = _parse_number(star_links[0].text(strip=True))

        fork_links = article.css("a[href$='/forks']")
        forks = 0
        if fork_links:
            forks = _parse_number(fork_links[0].text(strip=True))

        stars_today_node = article.css_first("span.d-inline-block.float-sm-right")
        stars_today = 0
        if stars_today_node:
            stars_today = _parse_stars_today(stars_today_node.text(strip=True))

        repos.append(
            TrendingRepo(
                rank=rank,
                owner=owner,
                name=name,
                full_name=full_name,
                url=f"https://github.com/{full_name}",
                description=description,
                language=language_val,
                stars=stars,
                stars_today=stars_today,
                forks=forks,
            )
        )

    return repos


async def fetch_trending_sync(
    language: str | None = None,
    since: SinceFilter = "daily",
) -> list[TrendingRepo]:
    import asyncio

    return asyncio.run(fetch_trending(language, since))
