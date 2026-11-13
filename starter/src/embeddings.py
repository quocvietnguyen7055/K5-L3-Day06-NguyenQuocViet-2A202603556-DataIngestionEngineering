"""OpenAI-compatible embeddings API adapter; fails loudly on provider errors."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class MyEmbedder:
    def __init__(self, model_name: str | None = None) -> None:
        self.provider = os.getenv("EMBEDDING_PROVIDER", "api").casefold()
        if self.provider == "sentence-transformers":
            offline = os.getenv("EMBEDDING_OFFLINE", "false").casefold() == "true"
            if offline:
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
            from sentence_transformers import SentenceTransformer

            self.model_name = model_name or os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
            self._model = SentenceTransformer(
                self.model_name, model_kwargs={"local_files_only": True} if offline else None)
            dimension_getter = getattr(self._model, "get_embedding_dimension", None)
            if dimension_getter is None:
                dimension_getter = self._model.get_sentence_embedding_dimension
            self.dimensions = dimension_getter()
            self.api_key = ""
            self.endpoint = ""
            return
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", "")
        self.api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
        self.endpoint = os.getenv("EMBEDDING_API_URL", "https://api.openai.com/v1/embeddings")
        if not self.model_name or not self.api_key:
            raise RuntimeError("Set EMBEDDING_MODEL and EMBEDDING_API_KEY (or OPENAI_API_KEY/OPENROUTER_API_KEY).")
        self.dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", "0"))

    def _embed(self, inputs: list[str]) -> list[list[float]]:
        if not inputs:
            return []
        body = {"model": self.model_name, "input": inputs}
        if self.dimensions:
            body["dimensions"] = self.dimensions
        request = Request(self.endpoint, data=json.dumps(body).encode(), method="POST", headers={
            "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
        })
        try:
            with urlopen(request, timeout=90) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            detail = exc.read().decode("utf-8", "replace")[:500] if isinstance(exc, HTTPError) else str(exc)
            raise RuntimeError(f"Embedding provider request failed: {detail}") from exc
        rows = sorted(payload.get("data", []), key=lambda row: row.get("index", 0))
        vectors = [row["embedding"] for row in rows]
        if len(vectors) != len(inputs) or not vectors:
            raise RuntimeError("Embedding provider returned a different number of vectors than inputs.")
        actual = len(vectors[0])
        if any(len(vector) != actual for vector in vectors):
            raise RuntimeError("Embedding provider returned inconsistent vector dimensions.")
        if self.dimensions and self.dimensions != actual:
            raise RuntimeError(f"Embedding provider changed dimensions from {self.dimensions} to {actual}.")
        self.dimensions = actual
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.provider == "sentence-transformers":
            if not texts:
                return []
            vectors = self._model.encode(texts, batch_size=16, normalize_embeddings=True,
                                         convert_to_numpy=True, show_progress_bar=True)
            return vectors.tolist()
        vectors: list[list[float]] = []
        for offset in range(0, len(texts), 64):
            vectors.extend(self._embed(texts[offset:offset + 64]))
        return vectors

    def embed_query(self, question: str) -> list[float]:
        if self.provider == "sentence-transformers":
            vector = self._model.encode([question], normalize_embeddings=True, convert_to_numpy=True)
            return vector[0].tolist()
        return self._embed([question])[0]
