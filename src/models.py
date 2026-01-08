from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TrendingRepo(BaseModel):
    rank: int
    owner: str
    name: str
    full_name: str
    url: str
    description: Optional[str] = None
    language: Optional[str] = None
    stars: int = 0
    stars_today: int = 0
    forks: int = 0


class EnrichedRepo(TrendingRepo):
    open_issues: int = 0
    watchers: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    pushed_at: Optional[datetime] = None
    license: Optional[str] = None
    topics: list[str] = Field(default_factory=list)
    default_branch: str = "main"
    has_wiki: bool = False
    has_discussions: bool = False
    archived: bool = False
    days_since_push: Optional[int] = None
    is_active: bool = True


class AnalyzedRepo(EnrichedRepo):
    health_score: int = 0
    activity_score: int = 0
    community_score: int = 0
    documentation_score: int = 0
    overall_score: int = 0

    summary: Optional[str] = None
    use_cases: list[str] = Field(default_factory=list)
    integration_tips: Optional[str] = None
    potential_risks: list[str] = Field(default_factory=list)

    analyzed_at: Optional[datetime] = None
    collected_at: Optional[datetime] = None


class TrendingSnapshot(BaseModel):
    collected_at: datetime
    language: Optional[str] = None
    since: str = "daily"
    repositories: list[AnalyzedRepo] = Field(default_factory=list)
