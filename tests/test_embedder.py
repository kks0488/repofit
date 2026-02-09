from src.embedder.openai_embedder import OpenAIEmbedder


def test_openai_embedder_class_contract() -> None:
    assert isinstance(OpenAIEmbedder, type)
    assert callable(getattr(OpenAIEmbedder, "embed", None))
    assert callable(getattr(OpenAIEmbedder, "embed_batch", None))
