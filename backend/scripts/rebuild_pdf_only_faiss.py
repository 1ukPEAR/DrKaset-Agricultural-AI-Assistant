from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
DATA_PREP_ROOT = PROJECT_ROOT / "data_preparation"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(DATA_PREP_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_PREP_ROOT))

from config import settings  # noqa: E402
from rag.embedder import _index_embedding_config, _loaded_faiss_dimension  # noqa: E402
from rag_pipeline.chunker import RecordChunker  # noqa: E402
from rag_pipeline.embedder import DrKasetEmbedder  # noqa: E402
from rag_pipeline.indexer import FAISSIndexer  # noqa: E402


CONFIG_PATH = DATA_PREP_ROOT / "config.yaml"
RECORDS_PATH = DATA_PREP_ROOT / "data" / "processed" / "records.json"
PREVIEW_PATH = DATA_PREP_ROOT / "data" / "processed" / "rag_chunks_preview.json"
FAISS_DIR = BACKEND_ROOT / "data" / "faiss_index"
REPORT_PATH = BACKEND_ROOT / "scripts" / "rebuild_pdf_only_faiss_report.json"


def load_config() -> dict:
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    for key in ["raw_dir", "processed_dir", "faiss_dir"]:
        cfg["paths"][key] = str((DATA_PREP_ROOT / cfg["paths"][key]).resolve())
    return cfg


def backup_existing_index(index_dir: Path) -> Path | None:
    if not index_dir.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = index_dir.parent / f"{index_dir.name}.backup_{timestamp}"
    shutil.copytree(index_dir, backup_dir)
    return backup_dir


def main() -> None:
    cfg = load_config()
    runtime_model = settings.EMBEDDING_MODEL
    effective_model, effective_device, effective_normalize = _index_embedding_config()
    data_model = cfg["embedding"]["model"]
    data_device = cfg["embedding"].get("device", "cpu")
    data_normalize = bool(cfg["embedding"].get("normalize", True))

    if data_model != effective_model or data_device != effective_device or data_normalize != effective_normalize:
        raise RuntimeError(
            "Embedding config mismatch between data preparation and backend effective runtime: "
            f"data=({data_model}, {data_device}, {data_normalize}) "
            f"backend=({effective_model}, {effective_device}, {effective_normalize})"
        )

    records = json.loads(RECORDS_PATH.read_text(encoding="utf-8"))
    before_source_counts = Counter(record.get("_source_type", "") for record in records)
    pdf_records = [record for record in records if record.get("_source_type") == "pdf"]
    if not pdf_records:
        raise RuntimeError("No PDF records found to embed")

    chunker = RecordChunker(cfg)
    docs = chunker.chunk_records(pdf_records)
    if not docs:
        raise RuntimeError("No PDF chunks produced")

    preview_payload = [{"text": doc.page_content, "metadata": doc.metadata} for doc in docs[:300]]
    PREVIEW_PATH.write_text(json.dumps(preview_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    backup_dir = backup_existing_index(FAISS_DIR)

    indexer = FAISSIndexer(cfg)
    embedder = DrKasetEmbedder(cfg).get_embedding_fn()
    indexer.build_index(docs, embedder)

    if FAISS_DIR.exists():
        shutil.rmtree(FAISS_DIR)
    indexer.save(str(FAISS_DIR))

    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "records_total": len(records),
        "records_source_counts": dict(before_source_counts),
        "pdf_records_used": len(pdf_records),
        "chunk_size": cfg["chunking"]["chunk_size"],
        "chunk_overlap": cfg["chunking"]["chunk_overlap"],
        "backend_runtime_embedding_model_setting": runtime_model,
        "backend_effective_embedding_config": {
            "model": effective_model,
            "device": effective_device,
            "normalize": effective_normalize,
            "existing_index_dimension_before_rebuild": _loaded_faiss_dimension(),
        },
        "data_preparation_embedding_config": {
            "model": data_model,
            "device": data_device,
            "normalize": data_normalize,
        },
        "backup_dir": str(backup_dir) if backup_dir else None,
        "vectors_after_rebuild": indexer.vector_count,
        "preview_source_types": sorted({(item.get("metadata") or {}).get("source_type", "") for item in preview_payload}),
        "csv_present_in_preview": any((item.get("metadata") or {}).get("source_type") == "csv" for item in preview_payload),
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
