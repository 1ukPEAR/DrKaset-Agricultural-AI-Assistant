from __future__ import annotations

import re

from cleansing.normalizer import TARGET_CROPS, detect_crop


THAI_RE = re.compile(r"[\u0E00-\u0E7F]")
MOJIBAKE_RE = re.compile(r"(เธ|เน|โ€”|โ|๏|ใ€|¢|Å|Ò|ä|§|�)")
MIN_TEXT_LENGTH = 20


class RecordValidator:
    def __init__(self, cfg: dict):
        config_crops = cfg.get("target_crops") or []
        self.target_crops = set(config_crops) | set(TARGET_CROPS)

    def text_quality(self, text: str) -> dict[str, int | bool]:
        thai_chars = len(THAI_RE.findall(text or ""))
        mojibake_hits = len(MOJIBAKE_RE.findall(text or ""))
        replacement_hits = (text or "").count("�")
        readable_thai = thai_chars >= 10 and mojibake_hits <= max(2, thai_chars // 40) and replacement_hits <= 2
        return {
            "thai_chars": thai_chars,
            "mojibake_hits": mojibake_hits,
            "replacement_hits": replacement_hits,
            "readable_thai": readable_thai,
        }

    def is_in_scope(self, record: dict) -> bool:
        text = str(record.get("text") or "")
        if len(text.strip()) < MIN_TEXT_LENGTH:
            return False

        quality = self.text_quality(text)
        if not quality["readable_thai"]:
            return False

        crop = record.get("crop") or detect_crop(text, str(record.get("_source_file") or ""))
        if not crop:
            return False
        if str(crop) not in self.target_crops:
            return False
        record["crop"] = str(crop)
        record["readable_thai"] = True
        record["mojibake_hits"] = quality["mojibake_hits"]
        return True

    def validate_fields(self, record: dict) -> dict[str, list[str]]:
        issues: dict[str, list[str]] = {}
        text = str(record.get("text") or "")
        quality = self.text_quality(text)
        if len(text.strip()) < MIN_TEXT_LENGTH:
            issues.setdefault("text", []).append("text too short")
        if not quality["readable_thai"]:
            issues.setdefault("text", []).append("Thai text is unreadable or mojibake")
        if not record.get("crop"):
            issues.setdefault("crop", []).append("missing target crop")
        return issues
