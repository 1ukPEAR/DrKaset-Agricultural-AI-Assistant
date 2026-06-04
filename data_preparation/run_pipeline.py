from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(BASE_DIR / "pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("run_pipeline")


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        cfg = yaml.safe_load(file) or {}
    for key in ["raw_dir", "processed_dir", "faiss_dir"]:
        cfg["paths"][key] = str((BASE_DIR / cfg["paths"][key]).resolve())
    return cfg


def record_key(record: dict) -> str:
    text = "".join(str(record.get("text") or "").lower().split())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def step_load(cfg: dict) -> tuple[list[dict], dict]:
    from input_files.loader import DataLoader

    raw_dir = Path(cfg["paths"]["raw_dir"])
    raw_dir.mkdir(parents=True, exist_ok=True)
    files = [path for path in raw_dir.rglob("*") if path.is_file() and not path.name.startswith(".")]
    loader = DataLoader(cfg)

    all_records: list[dict] = []
    audit_files: list[dict] = []
    logger.info("Found %s raw files in %s", len(files), raw_dir)
    for file_path in files:
        try:
            records = loader.load(file_path)
            all_records.extend(records)
            audit_files.append(
                {
                    "path": str(file_path),
                    "extension": file_path.suffix.lower(),
                    "bytes": file_path.stat().st_size,
                    "loaded_records": len(records),
                    "error": "",
                }
            )
            logger.info("  OK %s -> %s records", file_path.name, len(records))
        except Exception as exc:
            audit_files.append(
                {
                    "path": str(file_path),
                    "extension": file_path.suffix.lower(),
                    "bytes": file_path.stat().st_size,
                    "loaded_records": 0,
                    "error": str(exc),
                }
            )
            logger.error("  FAIL %s - %s", file_path.name, exc)

    return all_records, {"files": audit_files}


def step_clean(cfg: dict, records: list[dict], audit: dict | None = None) -> list[dict]:
    from cleansing.cleaner import TextCleaner
    from cleansing.normalizer import RecordNormalizer
    from cleansing.validator import RecordValidator

    cleaner = TextCleaner()
    normalizer = RecordNormalizer(cfg)
    validator = RecordValidator(cfg)

    cleaned: list[dict] = []
    skipped = Counter()
    crop_counts = Counter()
    topic_counts = Counter()
    seen: set[str] = set()

    for record in records:
        try:
            normalized = normalizer.normalize(cleaner.clean_record(record))
            issues = validator.validate_fields(normalized)
            if issues:
                skipped["invalid"] += 1
                continue
            if not validator.is_in_scope(normalized):
                skipped["out_of_scope_or_unreadable"] += 1
                continue
            key = record_key(normalized)
            if key in seen:
                skipped["duplicate"] += 1
                continue
            seen.add(key)
            cleaned.append(normalized)
            crop_counts[normalized.get("crop", "unknown")] += 1
            for topic in str(normalized.get("topic", "")).split(","):
                if topic:
                    topic_counts[topic] += 1
        except Exception as exc:
            logger.debug("clean error: %s", exc)
            skipped["error"] += 1

    processed_dir = Path(cfg["paths"]["processed_dir"])
    summary = {
        "loaded_records": len(records),
        "accepted_records": len(cleaned),
        "skipped": dict(skipped),
        "crop_counts": dict(crop_counts),
        "topic_counts": dict(topic_counts),
    }
    if audit is not None:
        audit["summary"] = summary
        write_json(processed_dir / "raw_audit_report.json", audit)

    write_json(processed_dir / "records.json", cleaned)
    write_json(processed_dir / "fact_sheets.json", build_fact_sheets(cleaned))
    logger.info("Clean complete: %s valid / skipped=%s", len(cleaned), dict(skipped))
    logger.info("Wrote processed records to %s", processed_dir / "records.json")
    return cleaned


def build_fact_sheets(records: list[dict]) -> dict:
    facts = defaultdict(lambda: defaultdict(list))
    for record in records:
        crop = record.get("crop")
        if not crop:
            continue
        topics = [topic for topic in str(record.get("topic", "")).split(",") if topic]
        for topic in topics or ["general"]:
            if len(facts[crop][topic]) < 8:
                facts[crop][topic].append(
                    {
                        "text": str(record.get("text", ""))[:900],
                        "source": record.get("_source_file", ""),
                        "page": record.get("_page", ""),
                        "confidence": record.get("confidence", ""),
                    }
                )
    return {crop: dict(topics) for crop, topics in facts.items()}


def step_embed(cfg: dict, records: list[dict] | None = None) -> None:
    from rag_pipeline.chunker import RecordChunker
    from rag_pipeline.embedder import DrKasetEmbedder
    from rag_pipeline.indexer import FAISSIndexer

    processed_dir = Path(cfg["paths"]["processed_dir"])
    if records is None:
        processed_path = processed_dir / "records.json"
        if not processed_path.exists():
            raise FileNotFoundError("records.json not found; run load/clean first")
        records = json.loads(processed_path.read_text(encoding="utf-8"))

    if not records:
        raise RuntimeError("No clean records to embed")

    docs = RecordChunker(cfg).chunk_records(records)
    if not docs:
        raise RuntimeError("No chunks produced")

    write_json(
        processed_dir / "rag_chunks_preview.json",
        [{"text": doc.page_content, "metadata": doc.metadata} for doc in docs[:300]],
    )

    indexer = FAISSIndexer(cfg)
    indexer.build_index(docs, DrKasetEmbedder(cfg).get_embedding_fn())

    faiss_dir = Path(cfg["paths"]["faiss_dir"])
    if faiss_dir.exists():
        backup_dir = faiss_dir.with_name(f"{faiss_dir.name}.backup")
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        shutil.move(str(faiss_dir), str(backup_dir))
        logger.info("Backed up previous index to %s", backup_dir)
    indexer.save(str(faiss_dir))
    logger.info("Saved FAISS index to %s", faiss_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="DrKaset data preparation and FAISS rebuild")
    parser.add_argument("--step", choices=["all", "load", "clean", "embed", "audit"], default="all")
    args = parser.parse_args()

    cfg = load_config()
    started = time.time()
    logger.info("Pipeline started: step=%s", args.step)

    if args.step in {"load", "audit"}:
        records, audit = step_load(cfg)
        if args.step == "audit":
            step_clean(cfg, records, audit)
        return

    if args.step == "clean":
        records, audit = step_load(cfg)
        step_clean(cfg, records, audit)
    elif args.step == "embed":
        step_embed(cfg)
    else:
        records, audit = step_load(cfg)
        cleaned = step_clean(cfg, records, audit)
        step_embed(cfg, cleaned)

    logger.info("Pipeline finished in %.1fs", time.time() - started)


if __name__ == "__main__":
    main()
