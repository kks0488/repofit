from typing import Optional

import httpx

from src.config import get_settings


class SlackNotifier:
    def __init__(
        self,
        token: Optional[str] = None,
        channel_id: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self.token = token or settings.slack_bot_token
        self.channel_id = channel_id or settings.slack_channel_id
        self._headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def is_configured(self) -> bool:
        return bool(self.token) and bool(self.channel_id)

    def send_message(
        self,
        text: str,
        blocks: Optional[list[dict]] = None,
        thread_ts: Optional[str] = None,
    ) -> bool:
        if not self.is_configured():
            return False

        payload: dict = {
            "channel": self.channel_id,
            "text": text,
        }
        if blocks:
            payload["blocks"] = blocks
        if thread_ts:
            payload["thread_ts"] = thread_ts

        try:
            response = httpx.post(
                "https://slack.com/api/chat.postMessage",
                headers=self._headers,
                json=payload,
                timeout=10.0,
            )
            data = response.json()
            return data.get("ok", False)
        except httpx.RequestError:
            return False

    def notify_trending_summary(
        self,
        total_repos: int,
        language: Optional[str] = None,
        top_repos: Optional[list[dict]] = None,
    ) -> bool:
        blocks = self._build_trending_blocks(total_repos, language, top_repos or [])
        fallback = f"GitHub Trending: {total_repos} repos analyzed ({language or 'All'})"
        return self.send_message(text=fallback, blocks=blocks)

    def notify_recommendations(
        self,
        recommendations: list[dict],
        threshold: float,
        trending_summary: Optional[dict] = None,
    ) -> bool:
        if not recommendations:
            return False

        blocks = self._build_recommendation_blocks(
            recommendations=recommendations,
            threshold=threshold,
            trending_summary=trending_summary,
        )

        count = len(recommendations)
        fallback = f"Found {count} recommendation(s) with score >= {threshold:.0%}"
        return self.send_message(text=fallback, blocks=blocks)

    def _build_trending_blocks(
        self,
        total_repos: int,
        language: Optional[str],
        top_repos: list[dict],
    ) -> list[dict]:
        blocks: list[dict] = []

        blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": "GitHub Trending Daily", "emoji": True},
        })

        lang_text = language or "All Languages"
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{total_repos}* repositories analyzed ({lang_text})"},
        })

        if top_repos:
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Top Trending Today:*"},
            })

            for repo in top_repos[:5]:
                name = repo.get("full_name", "unknown")
                stars = repo.get("stars", 0)
                stars_today = repo.get("stars_today", 0)
                lang = repo.get("language") or "-"
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"<https://github.com/{name}|*{name}*> | {lang} | {stars} stars (+{stars_today} today)",
                    },
                })

        return blocks

    def _build_recommendation_blocks(
        self,
        recommendations: list[dict],
        threshold: float,
        trending_summary: Optional[dict] = None,
    ) -> list[dict]:
        blocks: list[dict] = []

        blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": "GitHub Trending: New Recommendations", "emoji": True},
        })

        if trending_summary:
            lang = trending_summary.get("language") or "All Languages"
            total = trending_summary.get("total_repos", 0)
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Trending Today* ({lang}): {total} repositories analyzed"},
            })
            blocks.append({"type": "divider"})

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{len(recommendations)} recommendation(s)* above threshold ({threshold:.0%})"},
        })

        for rec in recommendations[:5]:
            score = rec.get("score", 0)
            full_name = rec.get("full_name", "unknown")
            project_name = rec.get("project_name", "")
            reasons = rec.get("reasons", [])
            stars = rec.get("stars", 0)

            reason_text = ""
            if reasons and isinstance(reasons[0], dict):
                reason_text = f"\n>{reasons[0].get('text', '')}"
            elif reasons and isinstance(reasons[0], str):
                reason_text = f"\n>{reasons[0]}"

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*<https://github.com/{full_name}|{full_name}>* ({stars} stars)\n"
                        f"Score: *{score:.0%}* | For: _{project_name}_"
                        f"{reason_text}"
                    ),
                },
            })

        if len(recommendations) > 5:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"_...and {len(recommendations) - 5} more_"}],
            })

        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "View all: `gt recommendations` | Web: http://localhost:3003"}],
        })

        return blocks
