"""Evidence-aware retrieval metrics and trace aggregation."""
import re
import unicodedata
from collections import defaultdict
from typing import Any


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFC", value).casefold()
    return " ".join(re.findall(r"\w+", value, flags=re.UNICODE))


def _is_hit(question: dict[str, Any], result: dict[str, Any]) -> bool:
    sources = question.get("gold_sources") or [{
        "document_id": question.get("gold_source_id"), "page": question.get("gold_page"),
        "evidence_quote": question.get("evidence_quote", ""),
    }]
    for gold in sources:
        doc_match = gold.get("document_id", gold.get("gold_source_id")) == result.get("document_id")
        page_match = gold.get("page", gold.get("gold_page")) == result.get("page")
        quote = _norm(gold.get("evidence_quote", ""))
        if doc_match and page_match and quote and quote in _norm(result.get("text", "")):
            return True
    return False


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    hit_flags = [_is_hit(question, result) for result in hits]
    return {"question_id": question["id"], "split": question["split"],
            "question": question["question"], "gold": question,
            "top_k": hits, "hit_flags": hit_flags,
            "hit_at_1": bool(hit_flags and hit_flags[0]),
            "evidence_hit_at_3": any(hit_flags[:3])}


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trace in traces:
        groups[trace["split"]].append(trace)
    return {split: {"n": len(rows),
                    "hit_at_1": {"hits": sum(row["hit_at_1"] for row in rows), "total": len(rows)},
                    "evidence_hit_at_3": {"hits": sum(row["evidence_hit_at_3"] for row in rows), "total": len(rows)}}
            for split, rows in sorted(groups.items())}
