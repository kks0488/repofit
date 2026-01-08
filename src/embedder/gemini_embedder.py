from typing import Optional

from google import genai

from src.config import get_settings

EMBEDDING_MODEL = "models/text-embedding-004"
EMBEDDING_DIM = 768


class GeminiEmbedder:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def embed(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
        result = self._client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config={"task_type": task_type},
        )
        if not result.embeddings:
            return []
        return result.embeddings[0].values or []

    def embed_batch(self, texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
        embeddings = []
        for text in texts:
            embeddings.append(self.embed(text, task_type))
        return embeddings


_embedder: Optional[GeminiEmbedder] = None


def _get_embedder() -> GeminiEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = GeminiEmbedder()
    return _embedder


def embed_text(text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    return _get_embedder().embed(text, task_type)


def embed_batch(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    return _get_embedder().embed_batch(texts, task_type)


def create_repo_summary(
    full_name: str,
    description: Optional[str],
    language: Optional[str],
    topics: list[str],
    readme_summary: Optional[str] = None,
) -> str:
    parts = [f"Repository: {full_name}"]
    if description:
        parts.append(f"Description: {description}")
    if language:
        parts.append(f"Language: {language}")
    if topics:
        parts.append(f"Topics: {', '.join(topics)}")
    if readme_summary:
        parts.append(f"Summary: {readme_summary}")
    return "\n".join(parts)


def create_project_summary(
    name: str,
    description: Optional[str],
    tech_stack: list[str],
    tags: list[str],
    goals: Optional[str] = None,
    readme_excerpt: Optional[str] = None,
) -> str:
    parts = [f"Project: {name}"]
    if description:
        parts.append(f"Description: {description}")
    if tech_stack:
        parts.append(f"Tech Stack: {', '.join(tech_stack)}")
    if tags:
        parts.append(f"Tags: {', '.join(tags)}")
    if goals:
        parts.append(f"Goals: {goals}")
    if readme_excerpt:
        parts.append(f"Details: {readme_excerpt[:1000]}")
    return "\n".join(parts)
