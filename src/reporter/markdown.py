"""Daily file delivery, using public project metadata and the existing stack matcher."""

import os
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import quote

import httpx

from src.enricher.github_sync import extract_tags, extract_tech_stack
from src.matcher.recommender import Recommender
from src.models import AnalyzedRepo
from src.utils import build_github_api_headers


async def fetch_public_projects(owner: str) -> list[dict]:
    projects = []
    async with httpx.AsyncClient(headers=build_github_api_headers(), timeout=30) as client:
        page = 1
        while True:
            response = await client.get(
                f"https://api.github.com/users/{quote(owner, safe='')}/repos",
                params={"type": "owner", "sort": "updated", "per_page": 100, "page": page},
            )
            response.raise_for_status()
            batch = response.json()
            for repo in batch:
                if repo.get("private") or repo.get("fork") or repo.get("archived"):
                    continue
                projects.append({
                    "name": repo["full_name"],
                    "tech_stack": extract_tech_stack(repo),
                    "tags": extract_tags(repo),
                })
            if len(batch) < 100:
                return projects
            page += 1


def _text(value: str) -> str:
    return " ".join(value.split()).replace("<", "&lt;").replace(">", "&gt;")


def write_markdown_digest(
    directory: Path,
    repos: list[AnalyzedRepo],
    projects: list[dict],
    *,
    total_repos: int,
    day: date | None = None,
) -> Path:
    if not repos:
        raise ValueError("Refusing to write an empty digest")
    day = day or date.today()
    lines = [
        f"# repofit 오늘의 오픈소스 — {day.isoformat()}",
        "",
        f"{total_repos}개 트렌딩 중 상위 {len(repos)}개 · 공개 프로젝트 {len(projects)}개와 비교",
        "",
        "프로젝트 매칭은 언어·주제의 일치 기준이며, 실제 적용을 검증한 결과는 아닙니다.",
        "",
        "## Top picks",
        "",
    ]
    for rank, repo in enumerate(repos, 1):
        matches = []
        for project in projects:
            if project["name"].casefold() == repo.full_name.casefold():
                continue
            score, overlap = Recommender._calculate_stack_overlap(
                project["tech_stack"], project["tags"], repo.language, repo.topics,
            )
            if overlap:
                matches.append((score, project["name"], sorted(overlap)))
        matches.sort(key=lambda match: (-match[0], match[1]))
        fit = "; ".join(
            f"[{name}](https://github.com/{name}) ({', '.join(overlap)})"
            for _, name, overlap in matches[:3]
        ) or "뚜렷한 언어·주제 일치 없음"
        why = _text(repo.summary or repo.description or "설명 없음")
        lines.extend([
            f"### {rank}. [{repo.full_name}](https://github.com/{repo.full_name})",
            "",
            f"⭐ {repo.stars:,} · 오늘 +{repo.stars_today:,} · {repo.language or '언어 미상'}",
            "",
            f"- **Why it matters / 주목할 이유:** {why} "
            f"오늘 별 {repo.stars_today:,}개 증가, 활동·커뮤니티 기반 품질 점수 {repo.overall_score}/100.",
            f"- **Matches to our projects / 우리 프로젝트:** {fit}",
            "",
        ])
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{day.isoformat()}.md"
    fd, temporary = tempfile.mkstemp(dir=directory, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("\n".join(lines))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path
