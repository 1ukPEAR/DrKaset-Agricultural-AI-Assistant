"""
DrKaset — Embedder
==================
Singleton wrapper สำหรับ HuggingFaceEmbeddings
  - Model: BAAI/bge-small-en-v1.5
  - device: cpu
  - normalize: True
  - Lazy loading — โหลด model ตอนใช้งานครั้งแรก
"""

import logging
import os
from functools import lru_cache
from typing import Callable, Optional

logger = logging.getLogger(__name__)
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")

_EMBEDDER_INSTANCE: Optional["DrKasetEmbedder"] = None


class DrKasetEmbedder:
    """
    Singleton HuggingFace Embeddings

    ใช้งาน:
        embedder    = DrKasetEmbedder(cfg)
        embed_fn    = embedder.get_embedding_fn()   # ใช้กับ FAISSIndexer
        vectors     = embedder.embed_texts(["text1", "text2"])
        vector      = embedder.embed_query("query")
    """

    def __init__(self, cfg: dict):
        embed_cfg   = cfg.get("embedding", {})
        self.model  = embed_cfg.get("model",     "BAAI/bge-small-en-v1.5")
        self.device = embed_cfg.get("device",    "cpu")
        self.normalize = embed_cfg.get("normalize", True)
        self._embeddings = None  # lazy load

    def _load(self):
        if self._embeddings is not None:
            return
        logger.info(f"กำลังโหลด embedding model: {self.model} (device={self.device})")
        from langchain_community.embeddings import HuggingFaceEmbeddings

        self._embeddings = HuggingFaceEmbeddings(
            model_name = self.model,
            model_kwargs = {"device": self.device},
            encode_kwargs = {"normalize_embeddings": self.normalize},
        )
        logger.info("โหลด embedding model สำเร็จ")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed list ของ texts → list of vectors"""
        self._load()
        return self._embeddings.embed_documents(texts)

    def embed_query(self, query: str) -> list[float]:
        """Embed query string เดียว → vector"""
        self._load()
        return self._embeddings.embed_query(query)

    def get_embedding_fn(self):
        """Return HuggingFaceEmbeddings object (ใช้กับ FAISS.from_documents)"""
        self._load()
        return self._embeddings

    def get_raw_embedder(self):
        """Alias ของ get_embedding_fn"""
        return self.get_embedding_fn()


def get_embedder(cfg: dict) -> DrKasetEmbedder:
    """Global singleton accessor"""
    global _EMBEDDER_INSTANCE
    if _EMBEDDER_INSTANCE is None:
        _EMBEDDER_INSTANCE = DrKasetEmbedder(cfg)
    return _EMBEDDER_INSTANCE
