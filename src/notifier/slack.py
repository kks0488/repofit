
import logging

import httpx

from src.config import get_settings


class SlackNotifier:
    def __init__(
        self,
        token: str | None = None,
        channel_id: str | None = None,
    ) -> None:
        settings = get_settings()
        self.token = token or settings.slack_bot_token
        self.channel_id = channel_id or settings.slack_channel_id
        self._headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self._logger = logging.getLogger(__name__)

    def is_configured(self) -> bool:
        return bool(self.token) and bool(self.channel_id)

    def send_message(
        self,
        text: str,
        blocks: list[dict] | None = None,
        thread_ts: str | None = None,
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
        except httpx.RequestError as exc:
            self._logger.warning("Slack request failed: %s", exc)
            return False
        except ValueError:
            self._logger.warning("Slack response was not JSON (status=%s)", response.status_code)
            return False

        if not data.get("ok", False):
            self._logger.warning("Slack postMessage failed: %s", data.get("error", "unknown"))
        return data.get("ok", False)

    def notify_trending_summary(
        self,
        total_repos: int,
        language: str | None = None,
        top_repos: list[dict] | None = None,
    ) -> bool:
        blocks = self._build_trending_blocks(total_repos, language, top_repos or [])
        fallback = f"📈 오늘의 트렌딩: {total_repos}개 레포 분석 ({language or '전체'})"
        return self.send_message(text=fallback, blocks=blocks)

    def notify_recommendations(
        self,
        recommendations: list[dict],
        threshold: float,
        trending_summary: dict | None = None,
    ) -> bool:
        if not recommendations:
            return False

        blocks = self._build_recommendation_blocks(
            recommendations=recommendations,
            threshold=threshold,
            trending_summary=trending_summary,
        )

        count = len(recommendations)
        fallback = f"🎯 맞춤 추천 {count}개 (적합도 {threshold:.0%} 이상)"
        return self.send_message(text=fallback, blocks=blocks)

    def _build_trending_blocks(
        self,
        total_repos: int,
        language: str | None,
        top_repos: list[dict],
    ) -> list[dict]:
        blocks: list[dict] = []

        blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": "📈 오늘의 GitHub 트렌딩", "emoji": True},
        })

        lang_text = language or "전체 언어"
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"총 *{total_repos}*개 레포지토리 분석 완료 ({lang_text})"},
        })

        if top_repos:
            blocks.append({"type": "divider"})

            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            for i, repo in enumerate(top_repos[:5]):
                name = repo.get("full_name", "unknown")
                stars = repo.get("stars", 0)
                stars_today = repo.get("stars_today", 0)
                lang = repo.get("language") or ""

                lang_badge = f"`{lang}`" if lang else ""
                stars_text = f"⭐ {stars:,}"
                today_text = f"  _+{stars_today} 오늘_" if stars_today else ""

                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{medals[i]} <https://github.com/{name}|*{name}*>  {lang_badge}\n      {stars_text}{today_text}",
                    },
                })

        return blocks

    def _build_recommendation_blocks(
        self,
        recommendations: list[dict],
        threshold: float,
        trending_summary: dict | None = None,
    ) -> list[dict]:
        blocks: list[dict] = []

        blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": "🎯 맞춤 레포 추천", "emoji": True},
        })

        if trending_summary:
            lang = trending_summary.get("language") or "전체 언어"
            total = trending_summary.get("total_repos", 0)
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"📊 오늘 트렌딩 {total}개 분석 ({lang})"}],
            })

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"✨ *{len(recommendations)}개 추천* (적합도 {threshold:.0%} 이상)"},
        })
        blocks.append({"type": "divider"})

        # 프로젝트별로 그룹화
        by_project: dict[str, list[dict]] = {}
        for rec in recommendations:
            proj = rec.get("project_name", "기타")
            if proj not in by_project:
                by_project[proj] = []
            by_project[proj].append(rec)

        for project_name, recs in list(by_project.items())[:3]:
            # 프로젝트 헤더
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"📁 *{project_name}*"},
            })

            # 해당 프로젝트의 추천 레포들
            for rec in recs[:3]:
                score = rec.get("score", 0)
                full_name = rec.get("full_name", "unknown")
                reasons = rec.get("reasons", [])
                stars = rec.get("stars", 0)

                # 점수 표시 바
                score_bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))

                # reason 텍스트 처리
                reason_text = ""
                if reasons:
                    first_reason = reasons[0]
                    if isinstance(first_reason, dict):
                        reason_text = first_reason.get("text", "")
                    elif isinstance(first_reason, str):
                        reason_text = first_reason

                text_content = (
                    f"<https://github.com/{full_name}|*{full_name}*>\n"
                    f"`{score_bar}` *{score:.0%}*  ⭐ {stars:,}"
                )
                if reason_text:
                    text_content += f"\n_{reason_text}_"

                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": text_content},
                })

        remaining = len(recommendations) - sum(min(3, len(r)) for r in list(by_project.values())[:3])
        if remaining > 0:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"_...외 {remaining}개 더 있음_"}],
            })

        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "🔍 전체 보기: `gt recommendations`"}],
        })

        return blocks
