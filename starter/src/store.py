"""PostgreSQL + pgvector persistence with cosine search and JSON metadata filters."""
from typing import Any

from .models import Chunk


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if not database_url or dimensions < 1:
            raise ValueError("database_url and positive embedding dimensions are required")
        self.database_url = database_url
        self.dimensions = dimensions

    def _connect(self):
        import psycopg
        from pgvector.psycopg import register_vector

        connection = psycopg.connect(self.database_url)
        register_vector(connection)
        return connection

    def create_schema(self) -> None:
        import psycopg

        with psycopg.connect(self.database_url) as connection, connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cursor.execute(f"""CREATE TABLE IF NOT EXISTS ingestion_chunks (
                strategy TEXT NOT NULL, chunk_id TEXT NOT NULL, document_id TEXT NOT NULL,
                source TEXT NOT NULL, page INTEGER NOT NULL, content TEXT NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                embedding vector({self.dimensions}) NOT NULL,
                PRIMARY KEY (strategy, chunk_id))""")
            cursor.execute("CREATE INDEX IF NOT EXISTS ingestion_chunks_metadata_idx ON ingestion_chunks USING GIN (metadata)")

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        from psycopg.types.json import Jsonb

        if not strategy or len(chunks) != len(vectors):
            raise ValueError("strategy is required and chunks/vectors lengths must match")
        if any(len(vector) != self.dimensions for vector in vectors):
            raise ValueError(f"Every vector must have {self.dimensions} dimensions")
        rows = [(strategy, chunk.chunk_id, chunk.document_id, chunk.source, chunk.page,
                 chunk.text, Jsonb(chunk.metadata), vector)
                for chunk, vector in zip(chunks, vectors)]
        with self._connect() as connection, connection.cursor() as cursor:
            # A strategy is a complete snapshot: replacing it also removes stale chunks.
            cursor.execute("DELETE FROM ingestion_chunks WHERE strategy = %s", (strategy,))
            if rows:
                cursor.executemany("""INSERT INTO ingestion_chunks
                    (strategy, chunk_id, document_id, source, page, content, metadata, embedding)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", rows)

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        from psycopg.types.json import Jsonb

        if len(query_vector) != self.dimensions or top_k < 1:
            raise ValueError("query vector dimension must match store and top_k must be positive")
        query = """SELECT chunk_id, document_id, source, page, content, metadata,
                          1 - (embedding <=> %s) AS score
                   FROM ingestion_chunks WHERE strategy = %s"""
        params: list[Any] = [query_vector, strategy]
        if filters:
            query += " AND metadata @> %s"
            params.append(Jsonb(filters))
        query += " ORDER BY embedding <=> %s LIMIT %s"
        params.extend([query_vector, top_k])
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(query, params)
            return [dict(chunk_id=row[0], document_id=row[1], source=row[2], page=row[3],
                         text=row[4], metadata=row[5], score=float(row[6])) for row in cursor.fetchall()]


class ChromaVectorStore:
    """Persistent local Chroma store with cosine search and metadata filters."""
    def __init__(self, path: str, dimensions: int) -> None:
        import chromadb

        if dimensions < 1:
            raise ValueError("positive embedding dimensions are required")
        self.client = chromadb.PersistentClient(path=path)
        self.dimensions = dimensions

    def create_schema(self) -> None:
        # Collections are created per strategy when their vectors are first written.
        return None

    def _collection(self, strategy: str):
        return self.client.get_or_create_collection(
            name=f"day06_{strategy}", metadata={"hnsw:space": "cosine"})

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if not strategy or len(chunks) != len(vectors):
            raise ValueError("strategy is required and chunks/vectors lengths must match")
        if any(len(vector) != self.dimensions for vector in vectors):
            raise ValueError(f"Every vector must have {self.dimensions} dimensions")
        collection = self._collection(strategy)
        existing = collection.get(include=[]).get("ids", [])
        if existing:
            collection.delete(ids=existing)
        if chunks:
            metadata = []
            for chunk in chunks:
                row = dict(chunk.metadata)
                row.update({"document_id": chunk.document_id, "source": chunk.source,
                            "page": chunk.page})
                metadata.append(row)
            collection.add(ids=[chunk.chunk_id for chunk in chunks],
                            documents=[chunk.text for chunk in chunks],
                            metadatas=metadata, embeddings=vectors)

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if len(query_vector) != self.dimensions or top_k < 1:
            raise ValueError("query vector dimension must match store and top_k must be positive")
        result = self._collection(strategy).query(
            query_embeddings=[query_vector], n_results=top_k,
            where=filters or None, include=["documents", "metadatas", "distances"])
        rows = []
        for i, chunk_id in enumerate(result["ids"][0]):
            metadata = result["metadatas"][0][i] or {}
            distance = result["distances"][0][i]
            rows.append({"chunk_id": chunk_id, "document_id": metadata.pop("document_id"),
                         "source": metadata.pop("source"), "page": metadata.pop("page"),
                         "text": result["documents"][0][i], "metadata": metadata,
                         "score": 1.0 - float(distance)})
        return rows
