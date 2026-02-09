import src.notifier.slack as slack_module


class _DummySettings:
    slack_bot_token = ""
    slack_channel_id = ""


def _notifier(monkeypatch):
    monkeypatch.setattr(slack_module, "get_settings", lambda: _DummySettings())
    return slack_module.SlackNotifier(token="xoxb-test", channel_id="C123")


def test_daily_digest_blocks_are_curated_and_concise(monkeypatch) -> None:
    notifier = _notifier(monkeypatch)

    repos: list[dict] = []
    for i in range(12):
        repos.append(
            {
                "full_name": f"org/repo-{i}",
                "url": f"https://github.com/org/repo-{i}",
                "language": "TypeScript" if i % 2 == 0 else "Python",
                "topics": ["react", "ui"] if i % 2 == 0 else ["llm", "agent"],
                "stars": 1000 + (i * 100),
                "stars_today": 80 + i,
                "overall_score": 70,
                "summary": "Useful for production workflows. It improves developer velocity.",
            }
        )

    curated = notifier._select_daily_curation(repos, limit=10)
    assert len(curated) == 10

    blocks = notifier._build_trending_blocks(total_repos=12, language=None, top_repos=curated)
    section_texts = [
        block["text"]["text"]
        for block in blocks
        if block.get("type") == "section" and "text" in block
    ]
    joined = "\n".join(section_texts)

    assert "Why:" in joined
    assert "AI/ML" in joined or "Frontend" in joined
    assert "Rising fast" in joined


def test_rising_fast_rule(monkeypatch) -> None:
    notifier = _notifier(monkeypatch)

    assert notifier._is_rising_fast({"stars": 1000, "stars_today": 80}) is True
    assert notifier._is_rising_fast({"stars": 10000, "stars_today": 50}) is False
