import json
from pathlib import Path

import httpx
import pytest

from src import cli
from src.analyzer import ai_advisor
from src.collector import scraper
from src.config import Settings
from src.models import EnrichedRepo, TrendingRepo, TrendingSnapshot


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
