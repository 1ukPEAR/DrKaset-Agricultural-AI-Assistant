from __future__ import annotations
from langchain_community.vectorstores import FAISS
from rag.embedder import get_embedder
from config import settings
from rag.constants import TOP_K
import os
import re

_faiss_store: FAISS | None = None
THAI_RE = re.compile(r"[\u0E00-\u0E7F]")
DISEASE_TERMS = [
    "โรค", "แมลง", "ศัตรูพืช", "เพลี้ย", "หนอน", "เชื้อรา", "ราแป้ง", "ราสนิม", "สนิม", "ใบด่าง",
    "ใบเหลือง", "ใบไหม้", "ใบขาว", "ใบร่วง", "ใบจุด", "รากเน่า", "โคนเน่า", "รากขาว",
    "แส้ดำ", "แส้", "เส้นดำ", "ไหม้คอรวง", "ทะลายเน่า", "หน้ายางแห้ง", "ระบาด", "พาหะ",
]
DISEASE_SYMPTOM_TERMS = [
    "แผล", "จุด", "ด่าง", "เหลือง", "ไหม้", "แห้ง", "ลีบ", "หงิก", "แคระ", "ช้ำ",
    "เปื่อย", "ผุ", "กลิ่น", "รู", "ขุย", "มูลหนอน", "ผง", "ขาว", "ร่วง", "เน่า",
    "ยอดแห้ง", "ลำต้นมีรู", "รากผุ", "รากเปื่อย", "เส้นใย", "หน้ากรีดแห้ง",
    "ถูกกัด", "โดนกัด", "กัดยอด",
]


def _looks_readable_thai(text: str, metadata: dict) -> bool:
    haystack = " ".join(
        str(value)
        for value in [text, metadata.get("crop", ""), metadata.get("keywords", "")]
        if value
    )
    thai_chars = len(THAI_RE.findall(haystack))
    return thai_chars >= 8


def _doc_matches(doc, crop: str | None, region: str | None, topic: str | None) -> bool:
    meta = doc.metadata
    if not _looks_readable_thai(doc.page_content, meta):
        return False
    if crop and meta.get("crop") and meta["crop"] != crop:
        return False
    if region and meta.get("region") and meta["region"] != region:
        return False
    if topic and topic not in str(meta.get("topic", "")).split(","):
        return False
    return True


def _doc_source_allowed(doc, source_types: list[str] | None) -> bool:
    if not source_types:
        return True
    source_type = str(doc.metadata.get("source_type", "")).lower()
    return source_type in {item.lower() for item in source_types}


def _has_disease_signal(text: str, metadata: dict) -> bool:
    haystack = " ".join(
        str(value)
        for value in [text, metadata.get("file_name", ""), metadata.get("keywords", "")]
        if value
    )
    return any(term in haystack for term in DISEASE_TERMS)


def _query_terms(text: str) -> list[str]:
    terms = [term for term in re.split(r"\s+", text.strip()) if len(term) >= 2]
    terms.extend(term for term in DISEASE_TERMS if term in text)
    terms.extend(term for term in DISEASE_SYMPTOM_TERMS if term in text)
    seen: set[str] = set()
    unique_terms = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            unique_terms.append(term)
    return unique_terms


def _lexical_score(query: str, text: str, metadata: dict) -> int:
    haystack = " ".join(
        str(value)
        for value in [text, metadata.get("file_name", ""), metadata.get("keywords", "")]
        if value
    )
    score = sum(1 for term in _query_terms(query) if term in haystack)
    if any(term in haystack for term in DISEASE_TERMS):
        score += 2
    file_name = str(metadata.get("file_name", ""))
    if "โรค" in file_name or "ศัตรูพืช" in file_name:
        score += 4
    if any(word in file_name for word in ["ปุ๋ย", "ราคา", "suitability", "คาดการณ์", "สถานที่ปลูก"]):
        score -= 3
    return score


def _scan_docstore(
    crop: str | None,
    region: str | None,
    topic: str | None,
    k: int,
    source_types: list[str] | None = None,
) -> list[dict]:
    if _faiss_store is None:
        return []
    docs = getattr(_faiss_store.docstore, "_dict", {}).values()
    results = []
    for doc in docs:
        if not _doc_source_allowed(doc, source_types):
            continue
        if _doc_matches(doc, crop, region, topic):
            results.append({"content": doc.page_content, "metadata": doc.metadata})
            if len(results) >= k:
                break
    return results


def _scan_disease_docstore(
    query: str,
    crop: str | None,
    region: str | None,
    k: int,
    source_types: list[str] | None = None,
) -> list[dict]:
    if _faiss_store is None:
        return []
    docs = getattr(_faiss_store.docstore, "_dict", {}).values()
    candidates = []
    for doc in docs:
        if not _doc_source_allowed(doc, source_types):
            continue
        meta = doc.metadata
        if not _doc_matches(doc, crop, region, None):
            continue
        score = _lexical_score(query, doc.page_content, meta)
        if score <= 0:
            continue
        candidates.append((score, doc))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [
        {"content": doc.page_content, "metadata": doc.metadata}
        for _, doc in candidates[:k]
    ]


def load_faiss() -> FAISS | None:
    global _faiss_store
    path = settings.FAISS_INDEX_PATH
    if os.path.exists(path):
        _faiss_store = FAISS.load_local(
            path,
            get_embedder(),
            allow_dangerous_deserialization=True,
        )
        print(f"[FAISS] Loaded index from {path}")
    else:
        print(f"[FAISS] Index not found at {path}. Run data_preparation pipeline first.")
    return _faiss_store


def get_store() -> FAISS | None:
    return _faiss_store


def retrieve(
    query: str,
    crop: str | None = None,
    region: str | None = None,
    topic: str | None = None,
    k: int = TOP_K,
    source_types: list[str] | None = None,
) -> list[dict]:
    """Search FAISS and return list of {page_content, metadata} dicts."""
    if _faiss_store is None:
        return []

    try:
        fetch_k = max(k * 2, 40 if (crop or region or topic) else k * 4)
        docs = _faiss_store.similarity_search(query, k=fetch_k)   # over-fetch then filter
    except AssertionError:
        print("[FAISS] Query embedding dimension does not match the loaded index. Falling back without RAG.")
        return []
    except Exception as exc:
        print(f"[FAISS] Retrieval failed: {exc}. Falling back without RAG.")
        return []

    results = []
    for doc in docs:
        if not _doc_source_allowed(doc, source_types):
            continue
        meta = doc.metadata
        if not _looks_readable_thai(doc.page_content, meta):
            continue
        if crop and meta.get("crop") and meta["crop"] != crop:
            continue
        if region and meta.get("region") and meta["region"] != region:
            continue
        if topic and topic not in str(meta.get("topic", "")).split(","):
            continue
        results.append({"content": doc.page_content, "metadata": meta})
        if len(results) >= k:
            break

    if topic == "disease":
        disease_candidates = [
            item for item in results
            if _lexical_score(query, item["content"], item["metadata"]) > 0
        ]
        seen = {
            (item["metadata"].get("file_name", ""), item["content"][:80])
            for item in disease_candidates
        }
        for item in _scan_disease_docstore(query, crop=crop, region=region, k=max(k * 4, 20)):
            key = (item["metadata"].get("file_name", ""), item["content"][:80])
            if key in seen:
                continue
            seen.add(key)
            disease_candidates.append(item)
        relaxed_crop_docs = []
        for doc in docs:
            if not _doc_source_allowed(doc, source_types):
                continue
            meta = doc.metadata
            if not _looks_readable_thai(doc.page_content, meta):
                continue
            if crop and meta.get("crop") and meta["crop"] != crop:
                continue
            relaxed_crop_docs.append({"content": doc.page_content, "metadata": meta})
        relaxed_crop_docs.sort(
            key=lambda item: _lexical_score(query, item["content"], item["metadata"]),
            reverse=True,
        )
        for item in relaxed_crop_docs:
            key = (item["metadata"].get("file_name", ""), item["content"][:80])
            if key in seen:
                continue
            seen.add(key)
            disease_candidates.append(item)
            if len(disease_candidates) >= k:
                break
        if len(disease_candidates) < k and crop:
            for item in _scan_docstore(crop=crop, region=region, topic=None, k=k, source_types=source_types):
                key = (item["metadata"].get("file_name", ""), item["content"][:80])
                if key in seen:
                    continue
                seen.add(key)
                disease_candidates.append(item)
                if len(disease_candidates) >= k:
                    break
        disease_candidates.sort(
            key=lambda item: _lexical_score(query, item["content"], item["metadata"]),
            reverse=True,
        )
        return disease_candidates[:k]

    # If a crop/region filter was requested but no readable matched docs remain,
    # avoid feeding unrelated or corrupted context to the LLM.
    if not results and topic:
        scanned = _scan_docstore(crop=crop, region=region, topic=topic, k=k, source_types=source_types)
        if scanned:
            return scanned
        return retrieve(query, crop=crop, region=region, topic=None, k=k, source_types=source_types)

    if not results and (crop or region):
        relaxed = []
        for doc in docs:
            if not _doc_source_allowed(doc, source_types):
                continue
            meta = doc.metadata
            if not _looks_readable_thai(doc.page_content, meta):
                continue
            if crop and meta.get("crop") and meta["crop"] != crop:
                continue
            relaxed.append({"content": doc.page_content, "metadata": meta})
            if len(relaxed) >= k:
                return relaxed
        return _scan_docstore(crop=crop, region=region, topic=None, k=k, source_types=source_types)

    # If no strict filter was requested, return readable top-k docs only.
    if not results:
        readable_docs = [d for d in docs if _doc_source_allowed(d, source_types) and _looks_readable_thai(d.page_content, d.metadata)]
        results = [{"content": d.page_content, "metadata": d.metadata} for d in readable_docs[:k]]

    return results

