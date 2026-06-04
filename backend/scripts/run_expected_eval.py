import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8")

from rag.retriever import load_faiss, retrieve  # noqa: E402
from rag.service import (  # noqa: E402
    _detect_requested_topics,
    detect_crop_in_text,
    detect_region_from_text,
    detect_topic,
    get_intent,
    stream_response,
)


DATASET_PATH = ROOT / "scripts" / "test_dataset_with_expected.json"
OUTPUT_PATH = ROOT / "scripts" / "expected_eval_results.json"


def normalize(text: str) -> str:
    return " ".join((text or "").split()).strip().lower()


def contains(text: str, needle: str) -> bool:
    return normalize(needle) in normalize(text)


def classify_answer(question: str, answer: str, expected: dict) -> dict:
    include_hits = [item for item in expected.get("must_include", []) if contains(answer, item)]
    include_misses = [item for item in expected.get("must_include", []) if item not in include_hits]
    forbidden_hits = [item for item in expected.get("must_not", []) if contains(answer, item)]
    passed = not include_misses and not forbidden_hits
    return {
        "pass": passed,
        "include_hits": include_hits,
        "include_misses": include_misses,
        "forbidden_hits": forbidden_hits,
    }


def run_case(case: dict) -> dict:
    question = case["question"]
    crop_candidates = detect_crop_in_text(question)
    crop = crop_candidates[0] if crop_candidates else None
    region = detect_region_from_text(question)
    topic = detect_topic(question)
    intent = get_intent(question)
    requested_topics = _detect_requested_topics(question)
    retrieval_source_types = ["pdf"] if intent == "knowledge" or (intent == "compare" and "ราคา" not in question and "ต้นทุน" not in question and "กำไร" not in question) else None

    docs = retrieve(question, crop=crop, region=region, topic=topic, k=3, source_types=retrieval_source_types)
    answer = "".join(part for part in stream_response(question, history=[]))
    answer_eval = classify_answer(question, answer, case["expected"])

    return {
        "id": case["id"],
        "question": question,
        "intent": intent,
        "topic": topic,
        "requested_topics": requested_topics,
        "crop": crop,
        "region": region,
        "retrieval_count": len(docs),
        "retrieval_sources": [
            {
                "crop": doc.get("metadata", {}).get("crop"),
                "topic": doc.get("metadata", {}).get("topic"),
                "file_name": doc.get("metadata", {}).get("file_name"),
                "source_type": doc.get("metadata", {}).get("source_type"),
            }
            for doc in docs[:3]
        ],
        "answer": answer,
        "evaluation": answer_eval,
    }


def main() -> None:
    load_faiss()
    with DATASET_PATH.open("r", encoding="utf-8") as f:
        dataset = json.load(f)

    results = [run_case(case) for case in dataset["tests"]]
    passed = sum(1 for item in results if item["evaluation"]["pass"])
    summary = {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round((passed / len(results)) * 100, 2) if results else 0.0,
        "results": results,
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps({"total": summary["total"], "passed": summary["passed"], "failed": summary["failed"], "pass_rate": summary["pass_rate"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
