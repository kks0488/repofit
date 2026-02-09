
from openai import OpenAI

from src.config import get_settings

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 768


class OpenAIEmbedder:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = OpenAI(
            api_key=settings.openai_embedding_api_key,
            base_url="https://api.openai.com/v1",
        )

    def embed(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
        response = self._client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
            dimensions=EMBEDDING_DIM,
        )
        if not response.data:
            return []
        return response.data[0].embedding

    def embed_batch(self, texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
            dimensions=EMBEDDING_DIM,
        )
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]


_embedder: OpenAIEmbedder | None = None


def _get_embedder() -> OpenAIEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = OpenAIEmbedder()
    return _embedder


def embed_text(text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    return _get_embedder().embed(text, task_type)


def embed_batch(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    return _get_embedder().embed_batch(texts, task_type)


def create_repo_summary(
    full_name: str,
    description: str | None,
    language: str | None,
    topics: list[str],
    readme_summary: str | None = None,
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
    description: str | None,
    tech_stack: list[str],
    tags: list[str],
    goals: str | None = None,
    readme_excerpt: str | None = None,
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
