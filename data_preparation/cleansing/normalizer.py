from __future__ import annotations

import re
from typing import Any


TARGET_CROPS: dict[str, list[str]] = {
    "ข้าว": ["rice", "paddy", "ข้าวเจ้า", "ข้าวหอมมะลิ"],
    "ข้าวโพด": ["corn", "maize", "ข้าวโพดเลี้ยงสัตว์", "ข้าวโพดหวาน"],
    "มันสำปะหลัง": ["cassava", "tapioca", "มัน"],
    "อ้อย": ["sugarcane", "sugar cane"],
    "ยางพารา": ["rubber", "para rubber", "ยาง"],
    "ปาล์มน้ำมัน": ["oil palm", "palm oil", "ปาล์ม"],
    "สับปะรด": ["pineapple", "สัปปะรด"],
    "ลำไย": ["longan"],
    "ทุเรียน": ["durian"],
    "มังคุด": ["mangosteen"],
    "กล้วย": ["banana"],
    "มะพร้าว": ["coconut"],
    "ถั่วเหลือง": ["soybean", "soy"],
    "ถั่วเขียว": ["mung bean", "mungbean"],
    "มะม่วง": ["mango"],
    "กาแฟ": ["coffee", "อาราบิก้า", "โรบัสต้า", "arabica", "robusta"],
}

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "harvest_duration": ["เก็บเกี่ยว", "อายุเก็บ", "วันเก็บ", "เดือนเก็บ", "harvest"],
    "fertilizer": ["ปุ๋ย", "ใส่ปุ๋ย", "ธาตุอาหาร", "ไนโตรเจน", "ฟอสฟอรัส", "โพแทสเซียม"],
    "price": ["ราคา", "บาท", "ตลาด", "price"],
    "disease": ["โรค", "แมลง", "ศัตรูพืช", "เชื้อรา", "หนอน", "เพลี้ย", "disease", "pest"],
    "profit": ["กำไร", "ต้นทุน", "รายได้", "ผลตอบแทน", "คุ้ม"],
    "planting_season": ["ฤดู", "ช่วงปลูก", "ปลูกช่วง", "ฝน", "แล้ง", "season"],
    "water": ["น้ำ", "ให้น้ำ", "ชลประทาน", "ความชื้น"],
    "planting_method": ["วิธีปลูก", "เตรียมดิน", "ระยะปลูก", "เมล็ด", "ท่อนพันธุ์", "ต้นกล้า"],
    "soil": ["ดิน", "ปรับดิน", "ความเหมาะสม", "กรด", "ด่าง"],
    "weather": ["อุณหภูมิ", "ฝน", "ความชื้น", "ภูมิอากาศ"],
}

CROP_ALIAS_MAP = {
    alias.lower(): crop
    for crop, aliases in TARGET_CROPS.items()
    for alias in [crop, *aliases]
}

COLUMN_ALIAS_MAP: dict[str, str] = {
    "ชื่อพืช": "crop",
    "พืช": "crop",
    "สินค้า": "crop",
    "crop": "crop",
    "crop_name": "crop",
    "commodity": "crop",
    "item": "crop",
    "ราคา": "price",
    "ราคาขาย": "price",
    "ราคาเฉลี่ย": "price",
    "price": "price",
    "price_thb": "price",
    "หน่วย": "unit",
    "unit": "unit",
    "ภาค": "region",
    "พื้นที่": "region",
    "จังหวัด": "province",
    "province": "province",
    "region": "region",
    "วันที่": "date",
    "เดือน": "month",
    "ปี": "year",
    "year": "year",
    "ผลผลิต": "yield",
    "yield": "yield",
    "ฤดูกาล": "season",
    "ฤดู": "season",
    "พันธุ์": "variety",
    "สายพันธุ์": "variety",
}

REGION_MAP = {
    "เหนือ": "ภาคเหนือ",
    "north": "ภาคเหนือ",
    "ใต้": "ภาคใต้",
    "south": "ภาคใต้",
    "อีสาน": "ภาคตะวันออกเฉียงเหนือ",
    "ตะวันออกเฉียงเหนือ": "ภาคตะวันออกเฉียงเหนือ",
    "northeast": "ภาคตะวันออกเฉียงเหนือ",
    "กลาง": "ภาคกลาง",
    "central": "ภาคกลาง",
    "ตะวันออก": "ภาคตะวันออก",
    "east": "ภาคตะวันออก",
    "ตะวันตก": "ภาคตะวันตก",
    "west": "ภาคตะวันตก",
}

UNIT_CONVERSION = {
    "บาท/กก.": 1.0,
    "บาท/กิโลกรัม": 1.0,
    "บาท/ตัน": 0.001,
    "บาท/100กก.": 0.01,
    "thb/kg": 1.0,
    "thb/tonne": 0.001,
    "usd/tonne": 0.035,
}

THAI_RE = re.compile(r"[\u0E00-\u0E7F]")
YEAR_RE = re.compile(r"(25[0-9]{2}|20[0-9]{2})")


def detect_crop(text: str, source_name: str = "") -> str | None:
    haystack = f"{source_name} {text}".replace("ํา", "ำ").lower()
    matches: list[tuple[int, int, str]] = []
    for alias, crop in CROP_ALIAS_MAP.items():
        pos = haystack.find(alias)
        if pos >= 0:
            matches.append((pos, -len(alias), crop))
    if not matches:
        return None
    matches.sort()
    return matches[0][2]


def detect_topics(text: str) -> list[str]:
    low = text.lower()
    return [topic for topic, words in TOPIC_KEYWORDS.items() if any(word in low for word in words)]


def normalize_crop(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return detect_crop(text) or text


def normalize_region(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    low = text.lower()
    for alias, canonical in REGION_MAP.items():
        if alias in low:
            return canonical
    return text


def to_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[,\s]", "", str(value))
    try:
        return float(text)
    except ValueError:
        return None


def normalize_price(price: Any, unit: Any) -> float | None:
    number = to_number(price)
    if number is None:
        return None
    unit_text = str(unit or "").strip().lower()
    for unit_name, factor in UNIT_CONVERSION.items():
        if unit_name.lower() in unit_text:
            return round(number * factor, 4)
    return number


def first_year(text: str) -> str:
    match = YEAR_RE.search(text)
    return match.group(1) if match else ""


def build_text(record: dict[str, Any]) -> str:
    existing = record.get("text")
    if isinstance(existing, str) and len(existing.strip()) > 20:
        return existing.strip()

    parts = []
    for key in ["crop", "region", "province", "price", "price_unit", "year", "date", "season", "variety", "yield"]:
        value = record.get(key)
        if value not in (None, ""):
            parts.append(f"{key}: {value}")

    skip = {"text", *[p.split(":")[0] for p in parts]}
    for key, value in record.items():
        if key.startswith("_") or key in skip or value in (None, ""):
            continue
        parts.append(f"{key}: {value}")
    return " | ".join(parts)


class RecordNormalizer:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def normalize(self, record: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in record.items():
            canonical = COLUMN_ALIAS_MAP.get(str(key).strip(), str(key).strip())
            normalized[canonical] = value

        source_name = str(normalized.get("_source_file") or normalized.get("file_name") or "")
        raw_text = " ".join(str(v) for v in normalized.values() if v is not None)

        crop = normalize_crop(normalized.get("crop")) or detect_crop(raw_text, source_name)
        if crop:
            normalized["crop"] = crop

        region = normalize_region(normalized.get("region") or normalized.get("province"))
        if region:
            normalized["region"] = region

        if "price" in normalized:
            price = normalize_price(normalized.get("price"), normalized.get("unit"))
            if price is not None:
                normalized["price"] = price
                normalized["price_unit"] = "บาท/กก."

        text = build_text(normalized)
        if text:
            normalized["text"] = text

        topics = detect_topics(text)
        if topics:
            normalized["topic"] = ",".join(topics)

        year = normalized.get("year") or first_year(text)
        if year:
            normalized["year"] = str(year)

        normalized["confidence"] = "high" if normalized.get("crop") and normalized.get("topic") else "medium"
        return {key: value for key, value in normalized.items() if value not in (None, "")}
