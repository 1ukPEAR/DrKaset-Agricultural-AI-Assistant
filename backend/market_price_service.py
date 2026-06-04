from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote
from uuid import uuid4

import requests


OAE_PRICE_ARTICLE_API = "https://oae.go.th/api/v1/article/476"
POWERBI_RESOURCE_KEY = "a285616d-dde2-4933-b533-94d99021f97e"
POWERBI_API_BASE = "https://wabi-south-east-asia-b-primary-api.analysis.windows.net"
POWERBI_REPORT_URL = (
    "https://app.powerbi.com/view?r="
    "eyJrIjoiYTI4NTYxNmQtZGRlMi00OTMzLWI1MzMtOTRkOTkwMjFmOTdlIiwidCI6IjI0M2Q1MDVlLWZlZmEtNGQwOC1hNmQ3LTZhOGJlNjcxNTYzMSIsImMiOjEwfQ%3D%3D"
)
TARGET_PRICE_NAMES = (
    "ข้าวหอมมะลิ",
    "ข้าวเปลือกเจ้า",
    "ข้าวโพด",
    "มันสำปะหลัง",
    "สัปปะรด",
    "สับปะรด",
    "ยางพารา",
    "ยางแผ่น",
    "น้ำยาง",
)
POWERBI_TARGET_VISUALS = [
    {"price_index": 18, "name": "ข้าวเปลือกเจ้าหอมมะลิ 105", "unit": "บาท/ตัน", "pdf_hint": "ข้าวหอมมะลิ.pdf"},
    {"price_index": 19, "name": "ข้าวเปลือกเจ้า พันธุ์สุพรรณบุรี", "unit": "บาท/ตัน", "pdf_hint": "ข้าวเปลือกเจ้า.pdf"},
    {"price_index": 16, "name": "ข้าวโพดเลี้ยงสัตว์ ความชื้น 14.5%", "unit": "บาท/กก.", "pdf_hint": "ข้าวโพด.pdf"},
    {"price_index": 26, "name": "หัวมันสำปะหลังสด (แป้ง 25%)", "unit": "บาท/กก.", "pdf_hint": "มัน 25.pdf"},
    {"price_index": 27, "name": "ยางพาราแผ่นดิบ ชั้น 3", "unit": "บาท/กก.", "pdf_hint": "ยางพารา.pdf"},
    {"price_index": 22, "name": "สับปะรดปัตตาเวียส่งโรงงาน", "unit": "บาท/กก.", "pdf_hint": "สัปปะรดโรงงาน.pdf"},
]


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._current_href: str | None = None
        self._current_class = ""
        self._text_parts: list[str] = []
        self._category: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: value or "" for name, value in attrs}
        class_name = attr.get("class", "")
        if tag == "div" and "category-header" in class_name:
            self._text_parts = []
            self._current_class = "category"
        if tag == "a":
            self._current_href = attr.get("href")
            self._current_class = class_name
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href or self._current_class == "category":
            text = data.strip()
            if text:
                self._text_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._current_class == "category":
            text = " ".join(self._text_parts).strip()
            if text:
                self._category = text
            self._current_class = ""
            self._text_parts = []
        if tag == "a" and self._current_href:
            label = " ".join(self._text_parts).strip()
            self.links.append(
                {
                    "name": label or _name_from_url(self._current_href),
                    "url": self._current_href,
                    "category": self._category or "",
                }
            )
            self._current_href = None
            self._text_parts = []
            self._current_class = ""


def _name_from_url(url: str) -> str:
    name = unquote(url.rsplit("/", 1)[-1]).replace(".pdf", "")
    return name.strip()


def _is_target_price_link(item: dict[str, str]) -> bool:
    haystack = f"{item.get('name', '')} {unquote(item.get('url', ''))}"
    return item.get("url", "").lower().endswith(".pdf") and any(name in haystack for name in TARGET_PRICE_NAMES)


def _powerbi_headers(content_type: bool = False) -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Origin": "https://app.powerbi.com",
        "Referer": POWERBI_REPORT_URL,
        "Accept": "application/json",
        "ActivityId": str(uuid4()),
        "RequestId": str(uuid4()),
        "X-PowerBI-ResourceKey": POWERBI_RESOURCE_KEY,
    }
    if content_type:
        headers["Content-Type"] = "application/json"
    return headers


def _extract_scalar(dsr: dict[str, Any]) -> Any:
    for dataset in dsr.get("DS", []):
        for ph in dataset.get("PH", []):
            for rows in ph.values():
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    for key, value in row.items():
                        if key != "S":
                            return value
    return None


def _query_powerbi_visual(meta: dict[str, Any], model_id: int, visual_index: int) -> Any:
    visual = meta["exploration"]["sections"][3]["visualContainers"][visual_index]
    query = json_loads(visual["query"])
    body = {
        "version": "1.0.0",
        "queries": [{"Query": query}],
        "cancelQueries": [],
        "modelId": model_id,
    }
    response = requests.post(
        f"{POWERBI_API_BASE}/public/reports/querydata?synchronous=true",
        timeout=30,
        headers=_powerbi_headers(content_type=True),
        json=body,
    )
    response.raise_for_status()
    data = response.json()
    dsr = data["results"][0]["result"]["data"].get("dsr", {})
    return _extract_scalar(dsr)


def _scrape_powerbi_prices() -> tuple[list[dict[str, Any]], str | None]:
    response = requests.get(
        f"{POWERBI_API_BASE}/public/reports/{POWERBI_RESOURCE_KEY}/modelsAndExploration?preferReadOnlySession=true",
        timeout=60,
        headers=_powerbi_headers(),
    )
    response.raise_for_status()
    meta = response.json()
    model_id = meta["models"][0]["id"]

    updated_text = _query_powerbi_visual(meta, model_id, 48)
    items = []
    for target in POWERBI_TARGET_VISUALS:
        price = _query_powerbi_visual(meta, model_id, target["price_index"])
        items.append(
            {
                "name": target["name"],
                "price": price,
                "unit": target["unit"],
                "pdf_hint": target["pdf_hint"],
                "source": "Power BI OAE",
            }
        )
    return items, updated_text


def json_loads(value: str) -> Any:
    import json

    return json.loads(value)


@lru_cache(maxsize=8)
def _scrape_oae_prices_cached(cache_key: str) -> dict[str, Any]:
    del cache_key
    response = requests.get(
        OAE_PRICE_ARTICLE_API,
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    item = payload.get("data", {}).get("items", [{}])[0]
    detail = item.get("detail", "")

    parser = _LinkParser()
    parser.feed(detail)

    pdf_links = []
    seen: set[str] = set()
    for link in parser.links:
        if not _is_target_price_link(link):
            continue
        url = link["url"].replace("http://oae.go.th", "https://oae.go.th")
        if url in seen:
            continue
        seen.add(url)
        pdf_links.append(
            {
                "name": link["name"],
                "category": link.get("category") or "สินค้าเกษตร",
                "url": url,
                "source": "สำนักงานเศรษฐกิจการเกษตร (OAE)",
            }
        )

    try:
        prices, updated_text = _scrape_powerbi_prices()
    except Exception:
        prices, updated_text = [], None

    for item in prices:
        matching_pdf = next(
            (
                pdf["url"]
                for pdf in pdf_links
                if item.get("pdf_hint") in unquote(pdf["url"])
            ),
            None,
        )
        item["url"] = matching_pdf
        item.pop("pdf_hint", None)

    return {
        "source": "OAE",
        "source_url": "https://oae.go.th/home/article/476",
        "api_url": OAE_PRICE_ARTICLE_API,
        "powerbi_url": POWERBI_REPORT_URL,
        "title": item.get("title", "ราคาสินค้าเกษตรรายวัน"),
        "updated_text": updated_text,
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
        "items": prices,
        "pdf_links": pdf_links,
        "summary_for_model": build_market_price_summary(prices),
    }


def get_market_prices() -> dict[str, Any]:
    cache_key = datetime.now().strftime("%Y-%m-%d-%H")
    return _scrape_oae_prices_cached(cache_key)


def build_market_price_summary(items: list[dict[str, str]]) -> str:
    if not items:
        return ""
    names = ", ".join(item["name"] for item in items[:10])
    return (
        "พบแหล่งข้อมูลราคาสินค้าเกษตรรายวันจาก OAE สำหรับ "
        f"{names} โดยเป็นลิงก์ PDF รายสินค้า ให้ใช้เป็นแหล่งอ้างอิงราคาล่าสุดเมื่อผู้ใช้ถามเรื่องราคา"
    )


def get_market_price_summary_for_prompt() -> str | None:
    try:
        return get_market_prices().get("summary_for_model")
    except Exception:
        return None
