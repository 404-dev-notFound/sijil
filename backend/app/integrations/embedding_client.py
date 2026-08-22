from functools import lru_cache
from typing import Protocol

from sentence_transformers import SentenceTransformer

from app.config.settings import get_settings


class EmbeddingClient(Protocol):
    def embed(self, text: str) -> list[float]: ...


class LocalEmbeddingClient:
    """Runs a local sentence-transformers model for vector search (architecture doc
    Section 6.1's "embed product description" step) — no external API key or vendor
    account, no per-call cost. Loading the model is the expensive part, so the loaded
    model itself is process-wide cached rather than reloaded per instance.
    """

    def __init__(self) -> None:
        self._model = _load_model(get_settings().embedding_model)

    def embed(self, text: str) -> list[float]:
        vector = self._model.encode(text, normalize_embeddings=True)
        result: list[float] = vector.tolist()
        return result


@lru_cache
def _load_model(model_name: str) -> SentenceTransformer:
    return SentenceTransformer(model_name)


def get_embedding_client() -> EmbeddingClient:
    return LocalEmbeddingClient()
