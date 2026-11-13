"""Build three comparable retrieval strategies and save traces and metrics."""
import json
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .models import DocumentPage
from .store import ChromaVectorStore, PgVectorStore

ROOT = Path(__file__).resolve().parents[1]

# The source corpus and embedding model are English; benchmark prompts are Vietnamese.
RETRIEVAL_QUESTIONS_EN = {
    "q01": "How does NIST define an event in this guidance?",
    "q02": "Give two examples of events listed in the document.",
    "q03": "What makes an event an adverse event in this guidance?",
    "q04": "What cases are included in NIST's definition of a cybersecurity incident?",
    "q05": "How does the glossary define incident response?",
    "q06": "Does NIST require every organization to use the incident response life cycle model in this document?",
    "q07": "Why does the document organize incident response guidance by CSF 2.0 functions, categories, and subcategories?",
    "q08": "Does the document say only the internal incident handling team is responsible for incident response?",
    "q09": "According to section 2.2, what is one responsibility of organizational leadership in incident response?",
    "q10": "According to section 2.3, name three common components of an incident response policy.",
    "q11": "What does the scope of an incident response policy define?",
    "q12": "According to section 2.3, what can an organization do to make incident response procedures easier to use?",
    "q13": "Are the Community Profile recommendations comprehensive and applicable to every organization?",
    "q14": "In section 3.1 on preparation and improvement, how can a standardized cybersecurity risk calculation method help an organization?",
    "q15": "Besides an organization's direct employees, who may share incident response responsibilities?",
    "q16": "What inventories should an organization maintain and automatically update to support vulnerability discovery and incident detection?",
    "q17": "What factors does NIST mention for prioritizing an organization's assets?",
    "q18": "According to the continuous monitoring recommendation in section 3.2, which two types of errors should monitoring technologies be tuned to reduce?",
    "q19": "Which network components must network monitoring recommendations cover?",
    "q20": "According to the CSF 2.0 Community Profile incident analysis recommendation, what should investigators determine about the incident and its causes?",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"Required input missing: {path}. See starter/README.md for the input schema.")
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    load_dotenv(ROOT / ".env")
    manifest_path = ROOT / "data" / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"Required input missing: {manifest_path}. Record source and permission before ingesting.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("source_id") or not manifest.get("license_or_permission"):
        raise SystemExit("manifest.json must include source_id and license_or_permission.")
    page_rows = _read_jsonl(ROOT / "data" / "pages.jsonl")
    questions = _read_jsonl(ROOT / "benchmark" / "questions.jsonl")
    if len([row for row in page_rows if row.get("text", "").strip()]) < 30:
        raise SystemExit("Corpus must contain at least 30 non-empty content pages/units.")
    if len(questions) < 20:
        raise SystemExit("Benchmark must contain at least 20 verified questions.")
    if len({row.get("id") for row in questions}) != len(questions):
        raise SystemExit("Benchmark question IDs must be unique.")
    if sum(row.get("split") == "dev" for row in questions) < 15 or sum(row.get("split") == "test" for row in questions) < 5:
        raise SystemExit("Benchmark must have at least 15 dev and 5 test questions.")
    if sum(bool(row.get("filter")) for row in questions) < 3 or not any(row.get("split") == "test" and row.get("filter") for row in questions):
        raise SystemExit("Benchmark needs at least 3 filter questions, including one test question.")
    for question in questions:
        if not all(question.get(key) for key in ("id", "split", "question", "evidence_quote")):
            raise SystemExit("Each benchmark row needs id, split, question, and verified evidence_quote.")
        if question["split"] not in {"dev", "test"}:
            raise SystemExit(f"Question {question['id']} has invalid split; use dev or test.")
        if not question.get("gold_sources") and not all(question.get(key) is not None for key in ("gold_source_id", "gold_page")):
            raise SystemExit(f"Question {question['id']} needs gold_source_id and gold_page, or gold_sources.")
        if question.get("filter") and not isinstance(question["filter"], dict):
            raise SystemExit(f"Question {question['id']} filter must be a JSON object.")

    pages = [DocumentPage(row["document_id"], row["source"], int(row["page"]), row["text"],
                          row.get("metadata", {})) for row in page_rows]
    embedder = MyEmbedder()
    vector_store_name = os.getenv("VECTOR_STORE", "pgvector").casefold()
    database_url = os.getenv("DATABASE_URL", "")
    if vector_store_name == "pgvector" and not database_url:
        raise SystemExit("DATABASE_URL is missing. Configure starter/.env and start PostgreSQL + pgvector.")
    if vector_store_name not in {"pgvector", "chroma"}:
        raise SystemExit("VECTOR_STORE must be pgvector or chroma.")
    # If dimensions are provider-discovered, embed once first, then initialize the typed vector table.
    configs = {
        "A": ("fixed_size", 500, 50),
        "B": ("paragraph", 500, 0),
        "C": ("paragraph", 500, 0),
    }
    ingestion_started = time.perf_counter()
    chunking_seconds_by_strategy = {}
    chunks_by_strategy = {}
    for strategy in configs:
        chunk_started = time.perf_counter()
        chunker = fixed_size if strategy == "A" else by_paragraph
        args = (500, 50) if strategy == "A" else (500,)
        chunks_by_strategy[strategy] = [chunk for page in pages for chunk in chunker(page, *args)]
        chunking_seconds_by_strategy[strategy] = time.perf_counter() - chunk_started

    embedding_seconds_by_strategy = {}
    vectors_by_strategy = {}
    for strategy, chunks in chunks_by_strategy.items():
        embedding_started = time.perf_counter()
        vectors_by_strategy[strategy] = embedder.embed_documents([chunk.text for chunk in chunks])
        embedding_seconds_by_strategy[strategy] = time.perf_counter() - embedding_started
    store_setup_started = time.perf_counter()
    store = (ChromaVectorStore(str(ROOT / "results" / "chroma"), embedder.dimensions)
             if vector_store_name == "chroma" else PgVectorStore(database_url, embedder.dimensions))
    store.create_schema()
    store_setup_seconds = time.perf_counter() - store_setup_started
    index_write_seconds_by_strategy = {}
    for strategy, chunks in chunks_by_strategy.items():
        index_started = time.perf_counter()
        store.upsert(strategy, chunks, vectors_by_strategy[strategy])
        index_write_seconds_by_strategy[strategy] = time.perf_counter() - index_started
    ingestion_seconds = time.perf_counter() - ingestion_started
    ingestion_seconds_by_strategy = {
        strategy: round(chunking_seconds_by_strategy[strategy]
                        + embedding_seconds_by_strategy[strategy]
                        + index_write_seconds_by_strategy[strategy], 3)
        for strategy in configs
    }

    traces = []
    query_started = time.perf_counter()
    for strategy in configs:
        for question in questions:
            vector = embedder.embed_query(RETRIEVAL_QUESTIONS_EN.get(question["id"], question["question"]))
            filters = question.get("filter") if strategy == "C" else None
            hits = store.search(strategy, vector, 3, filters)
            trace = evaluate_query(question, hits)
            trace["strategy"] = strategy
            trace["applied_filter"] = filters or {}
            traces.append(trace)
    query_seconds = time.perf_counter() - query_started
    results_dir = ROOT / "results"
    _write_json(results_dir / "retrieval_traces.json", traces)
    metrics = {strategy: summarize([row for row in traces if row["strategy"] == strategy]) for strategy in configs}
    _write_json(results_dir / "metrics.json", metrics)
    _write_json(results_dir / "run_metadata.json", {
        "source_id": manifest["source_id"], "content_units": sum(bool(row.get("text", "").strip()) for row in page_rows),
        "embedding_model": embedder.model_name, "embedding_dimensions": embedder.dimensions,
        "vector_store": "Chroma PersistentClient" if vector_store_name == "chroma" else "PostgreSQL + pgvector",
        "distance": "cosine", "strategies": configs,
        "chunk_counts": {key: len(value) for key, value in chunks_by_strategy.items()},
        "ingestion_seconds_all_strategies": round(ingestion_seconds, 3),
        "ingestion_seconds_by_strategy": ingestion_seconds_by_strategy,
        "chunking_seconds_by_strategy": {key: round(value, 3) for key, value in chunking_seconds_by_strategy.items()},
        "embedding_seconds_by_strategy": {key: round(value, 3) for key, value in embedding_seconds_by_strategy.items()},
        "index_write_seconds_by_strategy": {key: round(value, 3) for key, value in index_write_seconds_by_strategy.items()},
        "vector_store_setup_seconds": round(store_setup_seconds, 3),
        "query_and_evaluation_seconds": round(query_seconds, 3),
        "estimated_cost_usd": ("0 (embedding cục bộ; chưa tính điện năng máy)"
                                if embedder.provider == "sentence-transformers"
                                else os.getenv("ESTIMATED_COST_USD", "not supplied")),
        "note": "Chiến lược C chỉ khác B ở việc áp dụng bộ lọc metadata được cung cấp cho câu hỏi.",
    })
    print(f"Completed: {len(traces)} query-strategy traces. See results/metrics.json and results/retrieval_traces.json.")


if __name__ == "__main__":
    main()
