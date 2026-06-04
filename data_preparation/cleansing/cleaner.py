"""
DrKaset — Text Cleaner
=======================
clean_text():
  - ลบ \u00a0 (non-breaking space), zero-width chars
  - normalize whitespace และ line endings
  - ลบ control characters
  - normalize unicode (NFC)
"""

import re
import unicodedata
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Regex patterns ─────────────────────────────────────────────────────────────

# Zero-width + invisible chars
_ZW_CHARS = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f"
    r"\u00ad\ufeff\u2028\u2029\u180e]"
)

# Non-breaking space และ variants
_NBSP_CHARS = re.compile(r"[\u00a0\u202f\u2007\u2060]")

# Control characters (ยกเว้น \t, \n, \r)
_CTRL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Line endings หลายแบบ → \n
_LINE_ENDINGS = re.compile(r"\r\n|\r")

# Whitespace หลายตัวติดกัน (ไม่ใช่ newline)
_MULTI_SPACE = re.compile(r"[^\S\n]+")

# Newlines หลายตัวติดกัน
_MULTI_NEWLINE = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """
    ทำความสะอาด text string

    Steps:
      1. NFC normalization
      2. ลบ zero-width chars
      3. แทน NBSP ด้วย space
      4. ลบ control chars
      5. normalize line endings
      6. collapse whitespace
    """
    if not isinstance(text, str):
        text = str(text)
    if not text.strip():
        return ""

    # 1. NFC
    text = unicodedata.normalize("NFC", text)
    text = text.replace("ํา", "ำ")

    # 2. zero-width
    text = _ZW_CHARS.sub("", text)

    # 3. NBSP → space
    text = _NBSP_CHARS.sub(" ", text)

    # 4. control chars
    text = _CTRL_CHARS.sub("", text)

    # 5. line endings
    text = _LINE_ENDINGS.sub("\n", text)

    # 6. collapse
    text = _MULTI_SPACE.sub(" ", text)
    text = _MULTI_NEWLINE.sub("\n\n", text)

    return text.strip()


class TextCleaner:
    """
    ทำความสะอาด record dict ทั้งหมด

    ใช้งาน:
        cleaner = TextCleaner()
        clean   = cleaner.clean_record(record)
    """

    # field ที่เป็น numeric ไม่ต้อง clean เป็น text
    NUMERIC_FIELDS = {
        "price", "ราคา", "yield", "ผลผลิต", "area", "พื้นที่",
        "lat", "lon", "temp_c", "humidity", "pressure",
        "wind_speed", "rainfall_1h", "rainfall_3h", "value",
        "_page",
    }

    def clean_record(self, record: dict) -> dict:
        cleaned: dict = {}
        for key, val in record.items():
            cleaned_key = clean_text(str(key)) if isinstance(key, str) else key
            cleaned[cleaned_key] = self._clean_value(key, val)
        return cleaned

    def _clean_value(self, key: Any, val: Any) -> Any:
        if val is None:
            return None

        # numeric fields — พยายาม cast เป็น float
        if str(key) in self.NUMERIC_FIELDS:
            return self._to_number(val)

        if isinstance(val, str):
            return clean_text(val) or None

        if isinstance(val, (int, float)):
            return val

        if isinstance(val, list):
            return [self._clean_value(key, v) for v in val]

        if isinstance(val, dict):
            return {k: self._clean_value(k, v) for k, v in val.items()}

        # อื่นๆ ส่ง str แล้ว clean
        return clean_text(str(val)) or None

    @staticmethod
    def _to_number(val: Any) -> Optional[float]:
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        try:
            # ลบ comma, ช่องว่าง
            s = re.sub(r"[,\s]", "", str(val))
            return float(s)
        except (ValueError, TypeError):
            return None
