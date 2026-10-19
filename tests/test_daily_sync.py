import json
from pathlib import Path

import httpx
import pytest

from src import cli
from src.analyzer import ai_advisor
from src.collector import scraper
from src.config import Settings
from src.models import AnalyzedRepo, EnrichedRepo, TrendingRepo, TrendingSnapshot


@pytest.mark.asyncio
async def test_daily_sync_without_services_saves_ranked_json(monkeypatch, tmp_path) -> None:
    settings = Settings(_env_file=None, supabase_url="", supabase_service_key="", openai_api_key="")
    monkeypatch.setattr("src.config.get_settings", lambda: settings)
    monkeypatch.setattr(ai_advisor, "get_settings", lambda: settings)
    monkeypatch.setattr(ai_advisor, "_get_openai_client", lambda: pytest.fail("AI must be skipped"))
    monkeypatch.setattr("src.storage.SupabaseStorage", lambda: pytest.fail("No database allowed"))
    repos = [
        TrendingRepo(rank=1, owner="org", name="quiet", full_name="org/quiet",
                     url="https://github.com/org/quiet", stars=1000, stars_today=1),
        TrendingRepo(rank=2, owner="org", name="rising", full_name="org/rising",
                     url="https://github.com/org/rising", stars=1000, stars_today=300),
    ]

    async def fetch(**kwargs):
        return repos

    async def enrich(items):
        return [EnrichedRepo(**repo.model_dump(), license="MIT") for repo in items]

    monkeypatch.setattr("src.collector.fetch_trending", fetch)
    monkeypatch.setattr("src.enricher.enrich_repos", enrich)
    monkeypatch.chdir(tmp_path)
    # No explicit --output and no services: automatically uses a local JSON store.
    result = await cli._run_daily_digest_pipeline(language=None, analyze=True, send_slack=False, limit=1)
    path = Path("repofit-snapshot.json")
    payload = json.loads(path.read_text())
    snapshot = TrendingSnapshot.model_validate(payload)
    assert result == {"total_repos": 2, "curated_count": 1, "slack_sent": False}
    assert payload["curated_repositories"] == ["org/rising"]
    assert len(snapshot.repositories) == 2
    assert snapshot.repositories[0].license == "MIT"
    assert "api_key" not in path.read_text()
    # An explicit output must bypass even a configured database, and replace old data.
    settings.supabase_url = "https://example.supabase.co"
    settings.supabase_service_key = "unused-secret"
    await cli._run_daily_digest_pipeline(language="python", analyze=False, send_slack=False, output=path)
    assert json.loads(path.read_text())["language"] == "python"
    assert list(tmp_path.iterdir()) == [path.resolve()]


@pytest.mark.asyncio
async def test_empty_trending_fails_instead_of_overwriting_snapshot(monkeypatch, tmp_path) -> None:
    async def fetch(**kwargs):
        return []

    monkeypatch.setattr("src.collector.fetch_trending", fetch)
    path = tmp_path / "snapshot.json"
    path.write_text("previous snapshot")
    with pytest.raises(RuntimeError, match="empty snapshot"):
        await cli._run_daily_digest_pipeline(language=None, analyze=False, send_slack=False, output=path)
    assert path.read_text() == "previous snapshot"


@pytest.mark.asyncio
async def test_trending_scrapes_with_supported_lexbor_parser(monkeypatch) -> None:
    html = '''<article class="Box-row"><h2><a href="/org/tool">org/tool</a></h2>
    <p>A useful tool</p><span itemprop="programmingLanguage">Python</span>
    <a href="/org/tool/stargazers">1,234</a><a href="/org/tool/forks">56</a>
    <span class="d-inline-block float-sm-right">321 stars today</span></article>'''
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=html))
    monkeypatch.setattr(scraper.httpx, "AsyncClient", lambda: original_client(transport=transport))
    repos = await scraper.fetch_trending()
    assert len(repos) == 1
    assert (repos[0].full_name, repos[0].stars, repos[0].stars_today) == ("org/tool", 1234, 321)


def test_digest_command_writes_matches_without_slack_or_database(monkeypatch, tmp_path) -> None:
    from datetime import date

    from typer.testing import CliRunner

    settings = Settings(_env_file=None, openai_api_key="")
    monkeypatch.setattr(ai_advisor, "get_settings", lambda: settings)
    monkeypatch.setattr("src.notifier.SlackNotifier", lambda: pytest.fail("Slack must be opt-in"))
    monkeypatch.setattr("src.storage.SupabaseStorage", lambda: pytest.fail("No database allowed"))

    async def fetch(**kwargs):
        return [TrendingRepo(rank=1, owner="org", name="tool", full_name="org/tool",
                             url="https://github.com/org/tool", stars=1000, stars_today=200)]

    async def enrich(repos):
        return [EnrichedRepo(**{**repo.model_dump(), "language": "Python",
                               "topics": ["automation"], "description": "Useful automation"})
                for repo in repos]

    async def projects(owner):
        assert owner == "kks0488"
        return [
            {"name": "kks0488/repofit", "tech_stack": ["python"], "tags": ["automation"]},
            {"name": "kks0488/language-only", "tech_stack": ["python"], "tags": ["video"]},
            {"name": "kks0488/topic-only", "tech_stack": ["rust"], "tags": ["Automation"]},
            {"name": "kks0488/game", "tech_stack": ["c#"], "tags": ["game"]},
        ]

    monkeypatch.setattr("src.collector.fetch_trending", fetch)
    monkeypatch.setattr("src.enricher.enrich_repos", enrich)
    monkeypatch.setattr("src.reporter.markdown.fetch_public_projects", projects)
    result = CliRunner().invoke(cli.app, [
        "digest", "--no-analyze", "--no-save", "--digest-dir", str(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    text = (tmp_path / f"{date.today()}.md").read_text()
    assert "### 1. [org/tool](https://github.com/org/tool)" in text
    assert "Why it matters" in text and "Useful automation" in text
    assert "kks0488/repofit" in text and "automation, python" in text
    assert "kks0488/topic-only" in text
    assert "kks0488/language-only" not in text
    assert "kks0488/game" not in text
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.asyncio
async def test_digest_projects_paginate_and_exclude_private_forks_archived(monkeypatch) -> None:
    from src.reporter import markdown

    pages = []

    def respond(request):
        assert request.url.path == "/users/owner/repos"
        page = int(request.url.params["page"])
        pages.append(page)
        if page == 1:
            return httpx.Response(200, json=[
                {"full_name": "owner/old", "archived": True} for _ in range(100)
            ])
        return httpx.Response(200, json=[
            {"full_name": "owner/private", "private": True},
            {"full_name": "owner/fork", "fork": True},
            {"full_name": "owner/public", "language": "Python", "topics": ["automation"]},
        ])

    original = httpx.AsyncClient
    monkeypatch.setattr(markdown.httpx, "AsyncClient", lambda **kwargs: original(
        **kwargs, transport=httpx.MockTransport(respond),
    ))
    projects = await markdown.fetch_public_projects("owner")
    assert pages == [1, 2]
    assert projects == [{"name": "owner/public", "tech_stack": ["python"], "tags": ["automation"]}]


def test_digest_preserves_previous_file_on_empty_input_and_handles_no_match(tmp_path) -> None:
    from datetime import date

    from src.reporter.markdown import write_markdown_digest

    day = date(2026, 10, 16)
    repo = AnalyzedRepo(rank=1, owner="org", name="tool", full_name="org/tool",
                        url="https://github.com/org/tool", description="<script>\nhello")
    path = write_markdown_digest(tmp_path, [repo], [], total_repos=1, day=day)
    text = path.read_text()
    assert "Matches to our projects" not in text
    assert "<script>" not in text
    with pytest.raises(ValueError, match="empty digest"):
        write_markdown_digest(tmp_path, [], [], total_repos=0, day=day)
    assert path.read_text() == text
