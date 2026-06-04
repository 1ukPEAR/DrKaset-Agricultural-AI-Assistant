from __future__ import annotations

import hashlib
import logging
from typing import Any

from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

THAI_SEPARATORS = [
    "\n\n",
    "\n",
    "。",
    ".",
    "!",
    "?",
    ";",
    ",",
    " ",
    "",
]


class RecordChunker:
    def __init__(self, cfg: dict):
        chunk_cfg = cfg.get("chunking", {})
        self.chunk_size = int(chunk_cfg.get("chunk_size", 900))
        self.chunk_overlap = int(chunk_cfg.get("chunk_overlap", 150))
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=THAI_SEPARATORS,
            length_function=len,
            is_separator_regex=False,
        )

    def chunk_records(self, records: list[dict]) -> list[Document]:
        documents: list[Document] = []
        for index, record in enumerate(records):
            try:
                documents.extend(self._record_to_docs(record, index))
            except Exception as exc:
                logger.debug("chunk error record %s: %s", index, exc)
        logger.info("Chunking complete: %s records -> %s documents", len(records), len(documents))
        return documents

    def _record_to_docs(self, record: dict[str, Any], record_index: int) -> list[Document]:
        text = self._extract_text(record)
        if len(text.strip()) < 30:
            return []

        base_meta = self._build_metadata(record, record_index)
        chunks = [text] if len(text) <= self.chunk_size else self.splitter.split_text(text)
        docs: list[Document] = []
        for chunk_index, chunk in enumerate(chunks):
            chunk = chunk.strip()
            if len(chunk) < 30:
                continue
            metadata = {
                **base_meta,
                "chunk_index": chunk_index,
                "total_chunks": len(chunks),
            }
            metadata["chunk_id"] = self._make_chunk_id(chunk, metadata)
            docs.append(Document(page_content=chunk, metadata=metadata))
        return docs

    def _extract_text(self, record: dict[str, Any]) -> str:
        text = record.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

        parts: list[str] = []
        priority = ["crop", "topic", "region", "province", "price", "price_unit", "date", "year", "season", "variety", "yield"]
        for key in priority:
            value = record.get(key)
            if value not in (None, ""):
                parts.append(f"{key}: {value}")

        skip = set(priority) | {
            "text",
            "_source_type",
            "_source_file",
            "_source_url",
            "_source",
            "_scraped_at",
            "_fetched_at",
            "_page",
            "_sheet",
            "_zip_source",
            "chunk_id",
        }
        for key, value in record.items():
            if key not in skip and value not in (None, ""):
                parts.append(f"{key}: {value}")
        return " | ".join(parts)

    def _build_metadata(self, record: dict[str, Any], record_index: int) -> dict[str, Any]:
        return {
            "crop": record.get("crop", ""),
            "topic": record.get("topic", ""),
            "region": record.get("region") or record.get("province", ""),
            "source_type": record.get("_source_type", "unknown"),
            "file_name": record.get("_source_file", ""),
            "source_url": record.get("_source_url", ""),
            "page": record.get("_page", ""),
            "sheet": record.get("_sheet", ""),
            "record_idx": record_index,
            "price": record.get("price"),
            "price_unit": record.get("price_unit", ""),
            "date": str(record.get("date") or record.get("year", "")),
            "year": str(record.get("year", "")),
            "season": record.get("season", ""),
            "variety": record.get("variety", ""),
            "confidence": record.get("confidence", ""),
            "readable_thai": record.get("readable_thai", True),
        }

    @staticmethod
    def _make_chunk_id(text: str, metadata: dict[str, Any]) -> str:
        key = f"{metadata.get('file_name')}:{metadata.get('record_idx')}:{metadata.get('chunk_index')}:{text[:120]}"
        return hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
