from pathlib import Path
import threading

import yaml
from langchain_huggingface import HuggingFaceEmbeddings

from config import settings

_lock = threading.Lock()
_embedder: HuggingFaceEmbeddings | None = None

DIMENSION_MODEL_MAP = {
    384: "BAAI/bge-small-en-v1.5",
    768: "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    1024: "BAAI/bge-m3",
}


def _loaded_faiss_dimension() -> int | None:
    index_path = Path(settings.FAISS_INDEX_PATH) / "index.faiss"
    if not index_path.exists():
        return None

    try:
        import faiss

        return faiss.read_index(str(index_path)).d
    except Exception:
        return None


def _index_embedding_config() -> tuple[str, str, bool]:
    """Use an embedding model with the same dimension as the bundled FAISS index."""
    index_dim = _loaded_faiss_dimension()
    if index_dim in DIMENSION_MODEL_MAP:
        return DIMENSION_MODEL_MAP[index_dim], "cpu", True

    pipeline_config = Path(__file__).resolve().parents[2] / "data_preparation" / "config.yaml"
    if pipeline_config.exists():
        with pipeline_config.open("r", encoding="utf-8") as file:
            cfg = yaml.safe_load(file) or {}
        embedding_cfg = cfg.get("embedding", {})
        return (
            embedding_cfg.get("model", settings.EMBEDDING_MODEL),
            embedding_cfg.get("device", "cpu"),
            embedding_cfg.get("normalize", True),
        )

    return settings.EMBEDDING_MODEL, "cpu", True


def get_embedder() -> HuggingFaceEmbeddings:
    global _embedder
    if _embedder is None:
        with _lock:
            if _embedder is None:
                model_name, device, normalize = _index_embedding_config()
                _embedder = HuggingFaceEmbeddings(
                    model_name=model_name,
                    model_kwargs={"device": device},
                    encode_kwargs={"normalize_embeddings": normalize},
                )
    return _embedder
