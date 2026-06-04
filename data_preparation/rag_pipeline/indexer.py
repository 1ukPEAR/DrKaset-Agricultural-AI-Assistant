"""
DrKaset — FAISS Indexer
========================
  - build_faiss_index() : สร้าง index จาก Documents
  - save_faiss_index()  : บันทึกลง disk
  - load_faiss_index()  : โหลดจาก disk
  - merge_from()        : incremental merge (เพิ่ม docs โดยไม่ rebuild)
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional

from langchain.schema import Document

logger = logging.getLogger(__name__)

# Batch size สำหรับ embed (ป้องกัน OOM)
EMBED_BATCH_SIZE = 64


class FAISSIndexer:
    """
    จัดการ FAISS index สำหรับ DrKaset

    ใช้งาน:
        indexer = FAISSIndexer(cfg)
        indexer.build_index(docs, embedding_fn)
        indexer.save("data/faiss_index")
        indexer.load("data/faiss_index", embedding_fn)
        indexer.merge_from(new_docs, embedding_fn)
    """

    def __init__(self, cfg: Optional[dict] = None):
        self.cfg   = cfg or {}
        self._db   = None  # FAISS vectorstore object

    # ── Build ──────────────────────────────────────────────────────────────────

    def build_index(self, docs: list[Document], embedding_fn) -> None:
        """
        สร้าง FAISS index จาก Documents

        Args:
            docs:         list[Document] จาก chunker
            embedding_fn: HuggingFaceEmbeddings object
        """
        from langchain_community.vectorstores import FAISS

        if not docs:
            raise ValueError("ไม่มี documents ให้ build index")

        logger.info(f"กำลัง build FAISS index จาก {len(docs)} documents...")
        batches = self._batch(docs, EMBED_BATCH_SIZE)
        total   = len(batches)

        self._db = None
        for i, batch in enumerate(batches, 1):
            logger.info(f"  Batch {i}/{total} ({len(batch)} docs)")
            if self._db is None:
                self._db = FAISS.from_documents(batch, embedding_fn)
            else:
                batch_db = FAISS.from_documents(batch, embedding_fn)
                self._db.merge_from(batch_db)

        logger.info(
            f"Build เสร็จ: {self._db.index.ntotal} vectors ใน index"
        )

    # ── Save / Load ────────────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        """บันทึก index ลง disk"""
        if self._db is None:
            raise RuntimeError("ยังไม่มี index — รัน build_index() ก่อน")
        save_path = Path(path)
        save_path.mkdir(parents=True, exist_ok=True)
        self._db.save_local(str(save_path))
        logger.info(f"บันทึก FAISS index → {save_path}")

    def load(self, path: str, embedding_fn) -> None:
        """โหลด index จาก disk"""
        from langchain_community.vectorstores import FAISS

        load_path = Path(path)
        if not load_path.exists():
            raise FileNotFoundError(f"ไม่พบ FAISS index ที่ {load_path}")

        self._db = FAISS.load_local(
            str(load_path),
            embedding_fn,
            allow_dangerous_deserialization=True,
        )
        logger.info(
            f"โหลด FAISS index จาก {load_path} "
            f"({self._db.index.ntotal} vectors)"
        )

    # ── Incremental merge ──────────────────────────────────────────────────────

    def merge_from(self, new_docs: list[Document], embedding_fn) -> None:
        """
        เพิ่ม documents เข้า index ที่มีอยู่โดยไม่ต้อง rebuild ทั้งหมด
        (Incremental ingestion)
        """
        from langchain_community.vectorstores import FAISS

        if not new_docs:
            logger.warning("merge_from: ไม่มี documents ใหม่")
            return

        if self._db is None:
            logger.info("ไม่มี index เดิม — build index ใหม่")
            self.build_index(new_docs, embedding_fn)
            return

        logger.info(f"Merge {len(new_docs)} documents เข้า index ที่มีอยู่...")
        batches = self._batch(new_docs, EMBED_BATCH_SIZE)
        for i, batch in enumerate(batches, 1):
            batch_db = FAISS.from_documents(batch, embedding_fn)
            self._db.merge_from(batch_db)
            logger.info(f"  Merged batch {i}/{len(batches)}")

        logger.info(
            f"Merge เสร็จ: {self._db.index.ntotal} vectors รวม"
        )

    # ── Search ─────────────────────────────────────────────────────────────────

    def similarity_search(
        self,
        query: str,
        k: int = 8,
        filter: Optional[dict] = None,
    ) -> list[Document]:
        """
        ค้นหา documents ที่คล้ายกับ query

        Args:
            query:  query text
            k:      จำนวน results ที่ต้องการ
            filter: metadata filter dict (เช่น {"crop": "ข้าว"})
        """
        if self._db is None:
            raise RuntimeError("ยังไม่มี index")
        kwargs: dict = {"k": k}
        if filter:
            kwargs["filter"] = filter
        return self._db.similarity_search(query, **kwargs)

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 8,
        filter: Optional[dict] = None,
    ) -> list[tuple[Document, float]]:
        """Return (Document, score) pairs"""
        if self._db is None:
            raise RuntimeError("ยังไม่มี index")
        kwargs: dict = {"k": k}
        if filter:
            kwargs["filter"] = filter
        return self._db.similarity_search_with_score(query, **kwargs)

    def as_retriever(self, k: int = 8):
        """Return LangChain retriever object"""
        if self._db is None:
            raise RuntimeError("ยังไม่มี index")
        return self._db.as_retriever(search_kwargs={"k": k})

    @property
    def vector_count(self) -> int:
        if self._db is None:
            return 0
        return self._db.index.ntotal

    # ── Utils ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _batch(items: list, size: int) -> list[list]:
        return [items[i : i + size] for i in range(0, len(items), size)]


# ── Convenience functions ──────────────────────────────────────────────────────

def build_faiss_index(docs: list[Document], embedding_fn, cfg: Optional[dict] = None) -> FAISSIndexer:
    """Shortcut สำหรับ build + return indexer"""
    indexer = FAISSIndexer(cfg)
    indexer.build_index(docs, embedding_fn)
    return indexer


def save_faiss_index(indexer: FAISSIndexer, path: str) -> None:
    """Shortcut สำหรับ save"""
    indexer.save(path)


def load_faiss_index(path: str, embedding_fn, cfg: Optional[dict] = None) -> FAISSIndexer:
    """Shortcut สำหรับ load"""
    indexer = FAISSIndexer(cfg)
    indexer.load(path, embedding_fn)
    return indexer
