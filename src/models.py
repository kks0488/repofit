from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class TrendingRepo(BaseModel):
    rank: int
    github_id: int | None = None
    owner: str
    name: str
    full_name: str
    url: str
    description: str | None = None
    language: str | None = None
    stars: int = 0
    stars_today: int = 0
    forks: int = 0


class EnrichedRepo(TrendingRepo):
    open_issues: int = 0
    watchers: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pushed_at: datetime | None = None
    license: str | None = None
    topics: list[str] = Field(default_factory=list)
    default_branch: str = "main"
    has_wiki: bool = False
    has_discussions: bool = False
    archived: bool = False
    days_since_push: int | None = None
    is_active: bool = True


class AnalyzedRepo(EnrichedRepo):
    health_score: int = 0
    activity_score: int = 0
    community_score: int = 0
    documentation_score: int = 0
    overall_score: int = 0

    summary: str | None = None
    use_cases: list[str] = Field(default_factory=list)
    integration_tips: str | None = None
    potential_risks: list[str] = Field(default_factory=list)

    analyzed_at: datetime | None = None
    collected_at: datetime | None = None

    # Model replies sometimes put a bare number where text is expected (e.g. 1.5).
    # Keep the repo instead of dropping the whole analysis.
    @field_validator("summary", "integration_tips", mode="before")
    @classmethod
    def _scalar_to_text(cls, value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        return value

    @field_validator("use_cases", "potential_risks", mode="before")
    @classmethod
    def _items_to_text(cls, value):
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            value = [value]
        if isinstance(value, list):
            return [str(item) if isinstance(item, (int, float)) and not isinstance(item, bool) else item for item in value]
        return value


class TrendingSnapshot(BaseModel):
    collected_at: datetime
    language: str | None = None
    since: str = "daily"
    repositories: list[AnalyzedRepo] = Field(default_factory=list)
