"""
RepoFit RAG - Retrieval-Augmented Generation for Slack Bot

langchain + Gemini + Supabase pgvector를 사용하여
저장된 레포 데이터를 검색하고 더 정확한 답변을 제공합니다.
"""

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from src.config import get_settings
from src.storage import SupabaseStorage


class RepoFitRAG:
    """RAG 기반 RepoFit 질의응답 시스템"""

    def __init__(self) -> None:
        settings = get_settings()
        self.storage = SupabaseStorage()

        # Gemini 모델
        self.llm = ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            temperature=0.7,
        )

        # 임베딩 모델
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=settings.gemini_api_key,
        )

        # 시스템 프롬프트
        self.system_prompt = """당신은 RepoFit의 AI 어시스턴트입니다.
GitHub 트렌딩 레포지토리, 프로젝트 추천, 수익화 아이디어에 대해 도움을 줍니다.

다음 정보를 바탕으로 사용자 질문에 답변하세요:

{context}

답변 시 유의사항:
- 한국어로 친근하게 답변하세요
- 구체적인 레포 이름과 정보를 제공하세요
- 추천 이유를 설명하세요
- 모르는 정보는 솔직히 모른다고 하세요
"""

    def retrieve(self, query: str, limit: int = 5) -> list[dict]:
        """쿼리와 관련된 레포 검색"""
        results = []

        # 1. 쿼리 임베딩 생성
        try:
            query_embedding = self.embeddings.embed_query(query)
        except Exception:
            # 임베딩 실패 시 키워드 검색으로 폴백
            return self._keyword_search(query, limit)

        # 2. 벡터 유사도 검색
        similar_repos = self.storage.search_similar_repos(
            embedding=query_embedding,
            limit=limit,
        )
        results.extend(similar_repos)

        # 3. 트렌딩 데이터에서도 검색
        trending = self.storage.get_latest_trending(limit=10)
        for repo in trending:
            if any(
                query.lower() in str(v).lower()
                for v in [repo.get("full_name", ""), repo.get("description", "")]
            ):
                if repo not in results:
                    results.append(repo)

        return results[:limit]

    def _keyword_search(self, query: str, limit: int) -> list[dict]:
        """키워드 기반 검색 (폴백)"""
        results = []

        # 트렌딩에서 검색
        trending = self.storage.get_latest_trending(limit=50)
        query_lower = query.lower()

        for repo in trending:
            name = repo.get("full_name", "").lower()
            desc = (repo.get("description") or "").lower()
            lang = (repo.get("language") or "").lower()

            if query_lower in name or query_lower in desc or query_lower in lang:
                results.append(repo)

        return results[:limit]

    def _format_context(self, repos: list[dict], projects: list[dict] = None, recommendations: list[dict] = None) -> str:
        """컨텍스트 포맷팅"""
        parts = []

        if repos:
            parts.append("## 관련 레포지토리")
            for repo in repos[:5]:
                name = repo.get("full_name", "unknown")
                desc = repo.get("description", "설명 없음")
                stars = repo.get("stars", 0)
                lang = repo.get("language", "")
                parts.append(f"- **{name}** ({lang}): {desc} (⭐{stars:,})")

        if projects:
            parts.append("\n## 사용자 프로젝트")
            for proj in projects[:3]:
                name = proj.get("name", "unknown")
                stack = ", ".join(proj.get("tech_stack", [])[:5])
                parts.append(f"- **{name}**: {stack}")

        if recommendations:
            parts.append("\n## 추천 결과")
            for rec in recommendations[:5]:
                repo = rec.get("full_name", "unknown")
                proj = rec.get("project_name", "unknown")
                score = rec.get("score", 0)
                parts.append(f"- {repo} → {proj} ({score:.0%})")

        return "\n".join(parts) if parts else "관련 정보를 찾을 수 없습니다."

    def query(self, question: str, chat_history: list[tuple[str, str]] = None) -> str:
        """일반 질문에 답변"""
        # 관련 데이터 검색
        repos = self.retrieve(question, limit=5)
        projects = self.storage.get_projects()[:3]
        recommendations = self.storage.get_recommendations(limit=5)

        context = self._format_context(repos, projects, recommendations)

        # 대화 기록 구성
        messages = [SystemMessage(content=self.system_prompt.format(context=context))]

        if chat_history:
            for human, ai in chat_history:
                messages.append(HumanMessage(content=human))
                messages.append(AIMessage(content=ai))

        messages.append(HumanMessage(content=question))

        # 응답 생성
        try:
            response = self.llm.invoke(messages)
            return response.content
        except Exception as e:
            return f"죄송합니다, 응답 생성 중 오류가 발생했습니다: {str(e)[:100]}"

    def query_with_repos(self, question: str, repo_names: list[str], chat_history: list[tuple[str, str]] = None) -> str:
        """특정 레포에 대한 질문에 답변"""
        repos = []

        # 언급된 레포 정보 가져오기
        for name in repo_names[:5]:
            repo = self.storage.get_repository_by_name(name)
            if repo:
                repos.append(repo)

        # 추가로 유사 레포 검색
        if len(repos) < 3:
            similar = self.retrieve(question, limit=3)
            for r in similar:
                if r not in repos:
                    repos.append(r)

        context = self._format_context(repos)

        # 대화 기록 구성
        messages = [SystemMessage(content=self.system_prompt.format(context=context))]

        if chat_history:
            for human, ai in chat_history:
                messages.append(HumanMessage(content=human))
                messages.append(AIMessage(content=ai))

        messages.append(HumanMessage(content=question))

        # 응답 생성
        try:
            response = self.llm.invoke(messages)
            return response.content
        except Exception as e:
            return f"죄송합니다, 응답 생성 중 오류가 발생했습니다: {str(e)[:100]}"
