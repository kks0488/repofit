"""
Slack Bot - 스레드 자동 응답 + 채널 명령어 지원

기능:
1. 스레드 댓글 → RAG 기반 AI 응답
2. 채널에 "스캔" 메시지 → 프로젝트 폴더 스캔 실행

Socket Mode를 사용하여 공개 URL 없이 작동합니다.
"""

import re
from pathlib import Path

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from src.ai import RepoFitRAG
from src.config import get_settings

# 스캔 명령어 키워드
SCAN_KEYWORDS = {"스캔", "scan", "프로젝트스캔", "scan-projects", "폴더스캔"}

# GT 명령어 패턴 (스레드에서 감지 → 채널에 결과 전송)
GT_COMMANDS = {
    "recommend": ["gt recommend", "gt recommendations", "추천", "recommend"],
    "trending": ["gt trending", "트렌딩", "trending"],
    "match": ["gt match", "매칭", "match"],
    "sync": ["gt sync", "동기화", "sync"],
}


class RepoFitBot:
    def __init__(self, projects_path: str = "~/projects") -> None:
        settings = get_settings()

        if not settings.slack_bot_token:
            raise ValueError("SLACK_BOT_TOKEN이 설정되지 않았습니다")
        if not settings.slack_app_token:
            raise ValueError("SLACK_APP_TOKEN이 설정되지 않았습니다 (Socket Mode용 xapp-...)")

        self.app = App(token=settings.slack_bot_token)
        self.handler = SocketModeHandler(self.app, settings.slack_app_token)
        self.bot_user_id: str | None = None
        self.projects_path = Path(projects_path).expanduser().resolve()

        # RAG 체인 (langchain + Gemini + Supabase 벡터 검색)
        self.rag = RepoFitRAG()

        # 이벤트 핸들러 등록
        self._register_handlers()

    def _register_handlers(self) -> None:
        """이벤트 핸들러 등록"""

        @self.app.event("app_mention")
        def handle_mention(event: dict, say, client) -> None:
            """봇 멘션 시 응답"""
            self._handle_message(event, say, client)

        @self.app.event("message")
        def handle_message(event: dict, say, client) -> None:
            """메시지 처리 - 채널 명령어 + 스레드 응답"""
            # 봇 자신의 메시지는 무시
            if event.get("bot_id"):
                return

            # 서브타입 있으면 무시 (메시지 수정, 삭제 등)
            if event.get("subtype"):
                return

            text = event.get("text", "").strip().lower()

            # 채널 메시지에서 스캔 명령어 체크
            if "thread_ts" not in event:
                if self._is_scan_command(text):
                    self._handle_scan_command(event, say)
                return

            # 스레드 답글 처리
            self._handle_thread_message(event, say, client)

    def _detect_gt_command(self, text: str) -> str | None:
        """GT 명령어 감지 - 명령어 타입 반환"""
        text_lower = text.lower().strip()
        for cmd_type, patterns in GT_COMMANDS.items():
            for pattern in patterns:
                if pattern in text_lower:
                    return cmd_type
        return None

    def _handle_thread_message(self, event: dict, say, client) -> None:
        """스레드 메시지 처리 - 명령어 또는 RAG 응답"""
        text = event.get("text", "")
        thread_ts = event.get("thread_ts") or event.get("ts")
        channel = event.get("channel")

        # 봇 멘션 제거
        if self.bot_user_id:
            text = re.sub(f"<@{self.bot_user_id}>", "", text).strip()

        if not text:
            return

        # GT 명령어 감지
        cmd_type = self._detect_gt_command(text)
        if cmd_type:
            self._handle_gt_command(cmd_type, event, say, client)
            return

        # 일반 질문 → RAG 응답
        self._handle_message(event, say, client)

    def _handle_gt_command(self, cmd_type: str, event: dict, say, client) -> None:
        """GT 명령어 실행 → 채널에 새 메시지로 결과 전송"""
        thread_ts = event.get("thread_ts") or event.get("ts")
        channel = event.get("channel")

        try:
            # 스레드에 짧은 응답
            say(text=f"⏳ {cmd_type} 실행 중...", thread_ts=thread_ts)

            from src.storage import SupabaseStorage
            storage = SupabaseStorage()

            if cmd_type == "recommend":
                self._send_recommendations(storage, channel, say, thread_ts)
            elif cmd_type == "trending":
                self._send_trending(storage, channel, say, thread_ts)
            elif cmd_type == "match":
                self._send_match_results(storage, channel, say, thread_ts)
            elif cmd_type == "sync":
                self._send_sync_results(channel, say, thread_ts)

        except Exception as e:
            say(text=f"❌ 실행 실패: {str(e)[:100]}", thread_ts=thread_ts)

    def _send_recommendations(self, storage, channel: str, say, thread_ts: str) -> None:
        """추천 결과를 채널에 새 메시지로 전송"""
        recs = storage.get_recommendations(limit=10)

        if not recs:
            say(text="📭 추천 결과가 없습니다. `gt match` 먼저 실행하세요.", thread_ts=thread_ts)
            return

        # 채널에 새 메시지로 결과 전송
        lines = ["🎯 *프로젝트별 추천 레포*", ""]

        # 프로젝트별로 그룹화
        by_project: dict[str, list] = {}
        for rec in recs:
            proj = rec.get("project_name", "Unknown")
            if proj not in by_project:
                by_project[proj] = []
            by_project[proj].append(rec)

        for proj_name, proj_recs in list(by_project.items())[:3]:
            lines.append(f"*{proj_name}*")
            for r in proj_recs[:3]:
                score = r.get("score", 0)
                repo = r.get("full_name", "unknown")
                lines.append(f"  • {repo} ({score:.0%})")
            lines.append("")

        lines.append("_전체 보기: `gt recommendations`_")

        # 채널에 새 메시지 (스레드 아님)
        say(text="\n".join(lines))

        # 스레드에 완료 알림
        say(text="✅ 추천 결과를 채널에 보냈습니다 ↑", thread_ts=thread_ts)

    def _send_trending(self, storage, channel: str, say, thread_ts: str) -> None:
        """트렌딩 결과를 채널에 새 메시지로 전송"""
        trending = storage.get_latest_trending(limit=10)

        if not trending:
            say(text="📭 트렌딩 데이터가 없습니다. `gt sync` 먼저 실행하세요.", thread_ts=thread_ts)
            return

        lines = ["📈 *오늘의 트렌딩*", ""]

        medals = ["🥇", "🥈", "🥉"]
        for i, repo in enumerate(trending[:10]):
            prefix = medals[i] if i < 3 else f"{i+1}."
            name = repo.get("full_name", "unknown")
            stars = repo.get("stars", 0)
            stars_today = repo.get("stars_today", 0)
            lang = repo.get("language", "")

            line = f"{prefix} *{name}*"
            if lang:
                line += f" ({lang})"
            line += f" ⭐{stars:,}"
            if stars_today:
                line += f" _+{stars_today}_"
            lines.append(line)

        lines.append("")
        lines.append("_전체 보기: `gt trending`_")

        say(text="\n".join(lines))
        say(text="✅ 트렌딩 결과를 채널에 보냈습니다 ↑", thread_ts=thread_ts)

    def _send_match_results(self, storage, channel: str, say, thread_ts: str) -> None:
        """매칭 실행 → 채널에 결과 전송"""
        say(text="🔄 매칭 실행 중... (시간이 걸릴 수 있습니다)", thread_ts=thread_ts)

        from src.matcher import Recommender
        recommender = Recommender()
        recommender.embed_new_repos()
        recommender.embed_new_projects()
        result = recommender.run_full_pipeline(min_stars=100)

        lines = [
            "🎯 *매칭 완료*",
            "",
            f"📊 임베딩: 레포 {result.get('repos_embedded', 0)}개, 프로젝트 {result.get('projects_embedded', 0)}개",
            f"🎯 추천 생성: {result.get('total_recommendations', 0)}개",
            "",
            "_결과 보기: `gt recommendations`_",
        ]

        say(text="\n".join(lines))
        say(text="✅ 매칭 완료! 결과를 채널에 보냈습니다 ↑", thread_ts=thread_ts)

    def _send_sync_results(self, channel: str, say, thread_ts: str) -> None:
        """동기화 실행 → 채널에 결과 전송"""
        say(text="🔄 동기화 중... (트렌딩 수집 + 분석 + 매칭)", thread_ts=thread_ts)

        # 여기서 실제 sync 실행은 시간이 오래 걸리므로 간단히 안내만
        lines = [
            "⚠️ *동기화는 CLI에서 실행하세요*",
            "",
            "```",
            "gt sync --notify",
            "```",
            "",
            "_트렌딩 수집 → 분석 → 매칭 → Slack 알림_",
        ]

        say(text="\n".join(lines))
        say(text="💡 동기화는 터미널에서 `gt sync --notify` 실행하세요", thread_ts=thread_ts)

    def _is_scan_command(self, text: str) -> bool:
        """스캔 명령어인지 확인"""
        text_clean = text.replace(" ", "").replace("-", "")
        return any(keyword in text_clean for keyword in SCAN_KEYWORDS)

    def _handle_scan_command(self, event: dict, say) -> None:
        """프로젝트 폴더 스캔 실행"""
        thread_ts = event.get("ts")

        try:
            say(text="📂 프로젝트 폴더 스캔 중...", thread_ts=thread_ts)

            from src.scanner import FolderScanner

            scanner = FolderScanner(self.projects_path)
            projects = scanner.scan()

            if not projects:
                say(text="❌ 감지된 프로젝트가 없습니다.", thread_ts=thread_ts)
                return

            # 등록 및 매칭
            result = scanner.sync_to_storage(projects, auto_match=True)

            # 결과 메시지 구성
            lines = [
                f"✅ *프로젝트 스캔 완료*",
                f"",
                f"📁 감지: {len(projects)}개",
                f"🆕 신규 등록: {result.get('created', 0)}개",
                f"⏭️ 기존 스킵: {result.get('skipped', 0)}개",
            ]

            if result.get("recommendations"):
                lines.append(f"🎯 추천 생성: {result['recommendations']}개")

            # 신규 프로젝트 목록
            if result.get("created", 0) > 0:
                lines.append("")
                lines.append("*신규 프로젝트:*")
                new_projects = [p for p in projects if p.get("name")][:5]
                for proj in new_projects:
                    stack = ", ".join(proj.get("tech_stack", [])[:3]) or "-"
                    lines.append(f"  • {proj['name']} ({stack})")

            lines.append("")
            lines.append("`gt recommendations` 로 추천 확인")

            say(text="\n".join(lines), thread_ts=thread_ts)

        except Exception as e:
            say(text=f"❌ 스캔 실패: {str(e)[:100]}", thread_ts=thread_ts)

    def _handle_message(self, event: dict, say, client) -> None:
        """메시지 처리 및 RAG 기반 AI 응답"""
        text = event.get("text", "")
        thread_ts = event.get("thread_ts") or event.get("ts")
        channel = event.get("channel")

        # 봇 멘션 제거
        if self.bot_user_id:
            text = re.sub(f"<@{self.bot_user_id}>", "", text).strip()

        if not text:
            return

        try:
            # 스레드 대화 기록 가져오기
            chat_history = self._get_chat_history(client, channel, thread_ts)

            # 레포 이름 추출 (owner/repo 형식)
            repo_names = self._extract_repo_names(text)

            # RAG 기반 응답 생성
            if repo_names:
                response = self.rag.query_with_repos(text, repo_names, chat_history)
            else:
                response = self.rag.query(text, chat_history)

            # 스레드에 답글
            say(text=response, thread_ts=thread_ts)

        except Exception as e:
            say(text=f"죄송합니다, 오류가 발생했습니다: {str(e)[:100]}", thread_ts=thread_ts)

    def _get_chat_history(self, client, channel: str, thread_ts: str) -> list[tuple[str, str]]:
        """스레드 대화 기록을 (human, ai) 튜플 리스트로 변환"""
        history: list[tuple[str, str]] = []

        try:
            result = client.conversations_replies(channel=channel, ts=thread_ts, limit=10)
            messages = result.get("messages", [])

            # 메시지를 human/ai 쌍으로 그룹화
            human_msg = None
            for msg in messages[:-1]:  # 현재 메시지 제외
                is_bot = bool(msg.get("bot_id"))
                content = msg.get("text", "")[:500]

                if not is_bot:
                    human_msg = content
                elif is_bot and human_msg:
                    history.append((human_msg, content))
                    human_msg = None

        except Exception:
            pass

        return history[-3:]  # 최근 3턴만

    def _extract_repo_names(self, text: str) -> list[str]:
        """텍스트에서 owner/repo 형식의 레포 이름 추출"""
        # owner/repo 패턴 (예: langchain-ai/langchain, facebook/react)
        pattern = r'\b([a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)\b'
        matches = re.findall(pattern, text)
        # 일반적인 단어 제외
        excluded = {'http/https', 'src/main', 'test/unit'}
        return [m for m in matches if m.lower() not in excluded][:5]

    def start(self) -> None:
        """봇 시작"""
        # 봇 사용자 ID 가져오기
        try:
            auth_response = self.app.client.auth_test()
            self.bot_user_id = auth_response.get("user_id")
        except Exception as e:
            print(f"봇 인증 실패: {e}")

        print("🤖 RepoFit Slack Bot 시작!")
        print("명령어:")
        print("  • 채널에 '스캔' → 프로젝트 폴더 스캔")
        print("  • 스레드 댓글 → AI 자동 응답")
        print(f"  • 스캔 경로: {self.projects_path}")
        print("종료: Ctrl+C")
        print()
        self.handler.start()


def run_bot(projects_path: str = "~/projects") -> None:
    """봇 실행 헬퍼 함수"""
    bot = RepoFitBot(projects_path=projects_path)
    bot.start()
