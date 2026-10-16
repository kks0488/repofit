from datetime import date

import httpx

from src.collector.search import _six_months_ago, build_need_queries, search_need


def test_need_filters_and_calendar_month_cutoff() -> None:
    queries, terms = build_need_queries("automate gemini.google.com from scripts without API", date(2026, 10, 16))
    assert "gemini" in terms
    assert '"gemini.google.com"' in queries[0]
    assert all("stars:>=300 pushed:>=2026-04-16 archived:false fork:false" in q for q in queries)
    assert _six_months_ago(date(2026, 8, 31)) == date(2026, 2, 28)
    queries, _ = build_need_queries("bulk image generation via Google Flow web", date(2026, 10, 16))
    assert '"Google Flow"' in queries[0]


async def test_need_search_deduplicates_and_ranks_fit_before_popularity(monkeypatch) -> None:
    def repo(name: str, description: str, stars: int, license_id: str | None) -> dict:
        return {
            "full_name": f"owner/{name}", "name": name, "description": description,
            "stargazers_count": stars, "html_url": f"https://github.com/owner/{name}",
            "pushed_at": "2026-10-15T12:00:00Z",
            "license": {"spdx_id": license_id} if license_id else None,
        }

    items = [
        repo("awesome-gemini", "A list of tools", 100_000, "MIT"),
        repo("gemini-web2api", "Reverse-engineered Gemini browser automation", 400, None),
        {**repo("gemini-stale", "Gemini web API", 3000, "MIT"), "pushed_at": "2025-01-01T00:00:00Z"},
        repo("gemini-small", "Gemini web API", 20, "MIT"),
        {**repo("gemini-fork", "Gemini web API", 3000, "MIT"), "fork": True},
        {**repo("gemini-archived", "Gemini web API", 3000, "MIT"), "archived": True},
    ]
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/search/repositories":
            return httpx.Response(200, json={"items": items})
        return httpx.Response(200, text="Python wrapper for Gemini browser automation using session cookies.")

    original_client = httpx.AsyncClient
    monkeypatch.setattr("src.collector.search._get_headers", lambda: {"Authorization": "Bearer fake"})
    monkeypatch.setattr(
        "src.collector.search.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    results = await search_need("automate gemini.google.com from scripts without API", today=date(2026, 10, 16))
    assert len(results) == 2
    assert results[0]["full_name"] == "owner/gemini-web2api"
    assert results[0]["license"] == "UNKNOWN"
    assert "Reverse-engineered Gemini browser automation" in results[0]["fit"]
    assert len([request for request in requests if request.url.path.endswith("/readme")]) == 2
