
import logging
import re
from collections import defaultdict

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
        curated_repos = self._select_daily_curation(top_repos or [], limit=10)
        blocks = self._build_trending_blocks(total_repos, language, curated_repos)
        fallback = (
            f"📌 RepoFit Daily Curation: {len(curated_repos)} picks "
            f"from {total_repos} trending repos ({language or 'all languages'})"
        )
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
            "text": {"type": "plain_text", "text": "📌 RepoFit Daily Trending Curation", "emoji": True},
        })

        lang_text = language or "All languages"
        curated_count = len(top_repos)
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{curated_count} curated picks* from *{total_repos}* trending repos "
                    f"({lang_text})"
                ),
            },
        })

        if top_repos:
            blocks.append({"type": "divider"})

            grouped: dict[str, list[dict]] = defaultdict(list)
            for repo in top_repos[:10]:
                grouped[self._category_for_repo(repo)].append(repo)

            ordered_categories = [
                "AI/ML",
                "Frontend",
                "Backend",
                "DevOps",
                "Data",
                "Mobile",
                "Security",
                "Developer Tools",
                "General",
            ]
            for category in ordered_categories:
                repos = grouped.get(category)
                if not repos:
                    continue

                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*{category}*"},
                })

                for repo in repos:
                    name = repo.get("full_name", "unknown")
                    url = repo.get("url") or f"https://github.com/{name}"
                    stars = int(repo.get("stars", 0) or 0)
                    stars_today = int(repo.get("stars_today", 0) or 0)
                    lang = repo.get("language") or ""
                    lang_badge = f"`{lang}` " if lang else ""
                    rising_badge = " ⚡ *Rising fast*" if self._is_rising_fast(repo) else ""
                    why_line = self._build_one_line_why(repo)

                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"• <{url}|*{name}*> {lang_badge}\n"
                                f"  ⭐ {stars:,} · +{stars_today:,} today{rising_badge}\n"
                                f"  _Why: {why_line}_"
                            ),
                        },
                    })

            blocks.append({"type": "divider"})
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "Top 10 only: highest momentum and quality signals."}],
            })

        return blocks

    def _select_daily_curation(self, repos: list[dict], limit: int = 10) -> list[dict]:
        ranked = sorted(repos, key=self._curation_score, reverse=True)
        return ranked[:limit]

    def _curation_score(self, repo: dict) -> float:
        stars = max(int(repo.get("stars", 0) or 0), 1)
        stars_today = max(int(repo.get("stars_today", 0) or 0), 0)
        overall = min(100, max(0, int(repo.get("overall_score", 50) or 50)))

        trend_score = min(1.0, stars_today / 250)
        relative_growth = stars_today / stars
        growth_score = min(1.0, relative_growth * 8)
        quality_score = overall / 100
        return (0.5 * trend_score) + (0.3 * growth_score) + (0.2 * quality_score)

    def _is_rising_fast(self, repo: dict) -> bool:
        stars = max(int(repo.get("stars", 0) or 0), 1)
        stars_today = max(int(repo.get("stars_today", 0) or 0), 0)
        growth = stars_today / stars
        return (stars_today >= 50 and growth >= 0.03) or (stars_today >= 200 and growth >= 0.015)

    def _category_for_repo(self, repo: dict) -> str:
        language = (repo.get("language") or "").lower()
        topics = [str(topic).lower() for topic in (repo.get("topics") or [])]
        text = " ".join(
            [
                language,
                " ".join(topics),
                str(repo.get("description") or "").lower(),
                str(repo.get("summary") or "").lower(),
                str(repo.get("full_name") or "").lower(),
            ]
        )
        tokens = set(re.findall(r"[a-z0-9#+.-]+", text))

        category_keywords = {
            "AI/ML": [
                "ai", "ml", "llm", "agent", "rag", "langchain", "gpt", "diffusion", "embedding",
                "transformer", "pytorch", "tensorflow",
            ],
            "Frontend": [
                "react", "next", "vue", "svelte", "angular", "tailwind", "frontend", "ui", "css",
                "web component", "vite", "astro",
            ],
            "Backend": [
                "api", "backend", "server", "fastapi", "django", "flask", "spring", "express",
                "microservice", "graphql", "rest",
            ],
            "DevOps": [
                "devops", "kubernetes", "docker", "terraform", "ansible", "ci/cd", "cicd", "helm",
                "observability", "monitoring", "platform",
            ],
            "Data": [
                "data", "etl", "analytics", "warehouse", "dbt", "spark", "postgres", "sql",
                "lakehouse", "pipeline",
            ],
            "Mobile": [
                "android", "ios", "swift", "kotlin", "react-native", "flutter", "mobile",
            ],
            "Security": [
                "security", "auth", "oauth", "jwt", "encryption", "vulnerability", "pentest",
                "secret", "sandbox",
            ],
            "Developer Tools": [
                "cli", "sdk", "linter", "formatter", "testing", "benchmark", "tooling", "compiler",
                "build", "debug", "automation",
            ],
        }

        exact_token_keywords = {"ai", "ml", "ui"}
        for category, keywords in category_keywords.items():
            for keyword in keywords:
                if keyword in exact_token_keywords and keyword in tokens:
                    return category
                if keyword not in exact_token_keywords and keyword in text:
                    return category
        return "General"

    def _build_one_line_why(self, repo: dict) -> str:
        summary = str(repo.get("summary") or "").strip()
        if summary:
            summary = re.sub(r"\s+", " ", summary)
            first_sentence = re.split(r"(?<=[.!?])\s+", summary, maxsplit=1)[0]
            return self._truncate(first_sentence, max_len=140)

        language = repo.get("language") or "multi-language"
        stars_today = int(repo.get("stars_today", 0) or 0)
        topics = [str(topic) for topic in (repo.get("topics") or []) if topic]
        topic_hint = f" around {', '.join(topics[:2])}" if topics else ""
        reason = f"Strong traction (+{stars_today} stars today) in {language}{topic_hint}."
        return self._truncate(reason, max_len=140)

    def _truncate(self, text: str, max_len: int = 140) -> str:
        text = text.strip()
        if len(text) <= max_len:
            return text
        return text[: max_len - 1].rstrip() + "…"

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
