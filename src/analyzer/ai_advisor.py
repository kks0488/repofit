import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from google import genai

from src.config import get_settings
from src.models import AnalyzedRepo, EnrichedRepo

ANALYSIS_PROMPT = """Analyze this GitHub repository and provide insights.

Repository: {full_name}
Description: {description}
Language: {language}
Stars: {stars} (gained {stars_today} today)
Forks: {forks}
Open Issues: {open_issues}
License: {license}
Topics: {topics}
Days Since Last Push: {days_since_push}
Archived: {archived}

Provide your analysis in the following JSON format:
{{
    "health_score": <0-100 based on activity and maintenance>,
    "activity_score": <0-100 based on recent commits and issue response>,
    "community_score": <0-100 based on stars, forks, contributors>,
    "documentation_score": <0-100 estimate based on description quality>,
    "overall_score": <0-100 weighted average>,
    "summary": "<1-2 sentence summary of what this repo does and why it's trending>",
    "use_cases": ["<use case 1>", "<use case 2>", "<use case 3>"],
    "integration_tips": "<how a developer could integrate this into their project>",
    "potential_risks": ["<risk 1>", "<risk 2>"]
}}

Be concise and practical. Focus on actionable insights for developers."""


_genai_client: Optional[genai.Client] = None


def _get_genai_client() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        settings = get_settings()
        _genai_client = genai.Client(api_key=settings.gemini_api_key)
    return _genai_client


def _calculate_basic_scores(repo: EnrichedRepo) -> dict[str, int]:
    activity_score = 100
    if repo.days_since_push is not None:
        if repo.days_since_push > 365:
            activity_score = 10
        elif repo.days_since_push > 180:
            activity_score = 30
        elif repo.days_since_push > 90:
            activity_score = 50
        elif repo.days_since_push > 30:
            activity_score = 70

    if repo.archived:
        activity_score = 0

    community_score = min(100, (repo.stars / 100) + (repo.forks * 2))

    health_score = (activity_score + community_score) // 2

    doc_score = 50
    if repo.description and len(repo.description) > 50:
        doc_score = 70
    if repo.has_wiki:
        doc_score += 15

    overall = (health_score * 3 + activity_score * 2 + community_score * 2 + doc_score) // 8

    return {
        "health_score": int(health_score),
        "activity_score": int(activity_score),
        "community_score": int(min(100, community_score)),
        "documentation_score": int(min(100, doc_score)),
        "overall_score": int(overall),
    }


async def analyze_single_repo(
    client: genai.Client,
    model_name: str,
    repo: EnrichedRepo,
) -> AnalyzedRepo:
    prompt = ANALYSIS_PROMPT.format(
        full_name=repo.full_name,
        description=repo.description or "No description",
        language=repo.language or "Unknown",
        stars=repo.stars,
        stars_today=repo.stars_today,
        forks=repo.forks,
        open_issues=repo.open_issues,
        license=repo.license or "Unknown",
        topics=", ".join(repo.topics) if repo.topics else "None",
        days_since_push=repo.days_since_push or "Unknown",
        archived=repo.archived,
    )

    basic_scores = _calculate_basic_scores(repo)
    now = datetime.now(timezone.utc)

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model_name,
            contents=prompt,
        )
        text = (response.text or "").strip()

        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        analysis = json.loads(text.strip())

        return AnalyzedRepo(
            rank=repo.rank,
            owner=repo.owner,
            name=repo.name,
            full_name=repo.full_name,
            url=repo.url,
            description=repo.description,
            language=repo.language,
            stars=repo.stars,
            stars_today=repo.stars_today,
            forks=repo.forks,
            open_issues=repo.open_issues,
            watchers=repo.watchers,
            created_at=repo.created_at,
            updated_at=repo.updated_at,
            pushed_at=repo.pushed_at,
            license=repo.license,
            topics=repo.topics,
            default_branch=repo.default_branch,
            has_wiki=repo.has_wiki,
            has_discussions=repo.has_discussions,
            archived=repo.archived,
            days_since_push=repo.days_since_push,
            is_active=repo.is_active,
            health_score=analysis.get("health_score", basic_scores["health_score"]),
            activity_score=analysis.get("activity_score", basic_scores["activity_score"]),
            community_score=analysis.get("community_score", basic_scores["community_score"]),
            documentation_score=analysis.get(
                "documentation_score", basic_scores["documentation_score"]
            ),
            overall_score=analysis.get("overall_score", basic_scores["overall_score"]),
            summary=analysis.get("summary"),
            use_cases=analysis.get("use_cases", []),
            integration_tips=analysis.get("integration_tips"),
            potential_risks=analysis.get("potential_risks", []),
            analyzed_at=now,
            collected_at=now,
        )

    except (json.JSONDecodeError, Exception):
        return AnalyzedRepo(
            rank=repo.rank,
            owner=repo.owner,
            name=repo.name,
            full_name=repo.full_name,
            url=repo.url,
            description=repo.description,
            language=repo.language,
            stars=repo.stars,
            stars_today=repo.stars_today,
            forks=repo.forks,
            open_issues=repo.open_issues,
            watchers=repo.watchers,
            created_at=repo.created_at,
            updated_at=repo.updated_at,
            pushed_at=repo.pushed_at,
            license=repo.license,
            topics=repo.topics,
            default_branch=repo.default_branch,
            has_wiki=repo.has_wiki,
            has_discussions=repo.has_discussions,
            archived=repo.archived,
            days_since_push=repo.days_since_push,
            is_active=repo.is_active,
            health_score=basic_scores["health_score"],
            activity_score=basic_scores["activity_score"],
            community_score=basic_scores["community_score"],
            documentation_score=basic_scores["documentation_score"],
            overall_score=basic_scores["overall_score"],
            summary=f"Trending {repo.language or ''} repository with {repo.stars} stars.",
            use_cases=[],
            integration_tips=None,
            potential_risks=[],
            analyzed_at=now,
            collected_at=now,
        )


def _enriched_to_analyzed(repo: EnrichedRepo, scores: dict[str, int]) -> AnalyzedRepo:
    now = datetime.now(timezone.utc)
    return AnalyzedRepo(
        rank=repo.rank,
        owner=repo.owner,
        name=repo.name,
        full_name=repo.full_name,
        url=repo.url,
        description=repo.description,
        language=repo.language,
        stars=repo.stars,
        stars_today=repo.stars_today,
        forks=repo.forks,
        open_issues=repo.open_issues,
        watchers=repo.watchers,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
        pushed_at=repo.pushed_at,
        license=repo.license,
        topics=repo.topics,
        default_branch=repo.default_branch,
        has_wiki=repo.has_wiki,
        has_discussions=repo.has_discussions,
        archived=repo.archived,
        days_since_push=repo.days_since_push,
        is_active=repo.is_active,
        health_score=scores["health_score"],
        activity_score=scores["activity_score"],
        community_score=scores["community_score"],
        documentation_score=scores["documentation_score"],
        overall_score=scores["overall_score"],
        analyzed_at=now,
        collected_at=now,
    )


async def analyze_repos(
    repos: list[EnrichedRepo],
    skip_ai: bool = False,
    batch_size: int = 5,
) -> list[AnalyzedRepo]:
    if skip_ai:
        return [_enriched_to_analyzed(repo, _calculate_basic_scores(repo)) for repo in repos]

    settings = get_settings()
    client = _get_genai_client()

    analyzed: list[AnalyzedRepo] = []

    for i in range(0, len(repos), batch_size):
        batch = repos[i : i + batch_size]
        tasks = [analyze_single_repo(client, settings.gemini_model, repo) for repo in batch]
        results = await asyncio.gather(*tasks)
        analyzed.extend(results)
        if i + batch_size < len(repos):
            await asyncio.sleep(1)

    return analyzed
