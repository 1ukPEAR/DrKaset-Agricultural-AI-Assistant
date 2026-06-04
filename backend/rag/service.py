from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
import re
import json

import ollama

from config import settings
from rag.constants import (
    CROP_ALIAS_MAP,
    NON_SCOPE_CROP_HINTS,
    REGION_KEYWORDS,
    TARGET_CROPS,
    TEMPERATURE,
    TOP_K,
    TOP_K_COMPARE,
    ROUTER_SYSTEM_PROMPT
)
from rag.retriever import retrieve
from weather_service import get_weather_summary_for_prompt

# def get_llm_intent(query: str) -> str:
#     """ส่งคำถามให้ LLM แยกหมวดหมู่ความต้องการ"""
#     try:
#         response = ollama_client.chat(
#             model=settings.OLLAMA_FAST_MODEL, 
#             messages=[
#                 {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
#                 {"role": "user", "content": f"ประโยคจากผู้ใช้: '{query}'"}
#             ],
#             format="json",
#             options={
#                 "temperature": 0.0,
#                 "num_predict": 20
#             }
#         )
#         result_text = response["message"]["content"]
#         parsed_json = json.loads(result_text)
#         return parsed_json.get("intent", "agriculture_knowledge")
#     except Exception as e:
#         print(f"[Router Error] {e}")
#         return "agriculture_knowledge" # Fallback ถ้า Router พัง

def get_llm_intent(query: str) -> str:
    try:
        response = ollama_client.chat(
            model=settings.OLLAMA_FAST_MODEL, 
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": f"ประโยค: '{query}'"}
            ],
            format="json",
            options={
                "temperature": 0.0,
                "num_predict": 50
            }
        )
        result_text = response["message"]["content"].strip()
        
        # ตัด Markdown Code Blocks ทิ้ง (ถ้า LLM เผลอใส่มา)
        if "{" in result_text:
            result_text = result_text[result_text.find("{"):result_text.rfind("}")+1]
            
        parsed_json = json.loads(result_text)
        return parsed_json.get("intent", "agriculture_knowledge")
    except Exception as e:
        print(f"⚠️ [Router Error/JSON Parse Failed]: {e}")
        # ถ้า Router พังจริงๆ ให้ใช้ Keyword พื้นฐานดักช่วยชีวิตไว้ก่อน
        if is_out_of_domain_question(query): return "out_of_domain"
        if _is_illegal_agri_request(query) or _has_chemical_exposure_medical_request(query): return "safety_violation"
        if is_greeting(query) or is_capability_question(query): return "greeting"
        return "agriculture_knowledge"


ollama_client = ollama.Client(host=settings.OLLAMA_HOST)
CHINESE_RE = re.compile(r"[\u3000-\u303F\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF\uFF00-\uFFEF]+")
THAI_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。])\s+|\n+")
NUMBER_RE = r"\d[\d,]*(?:\.\d+)?"
THAI_MONEY_RE = rf"({NUMBER_RE})\s*(ล้าน|แสน|หมื่น)?"
RAI_RE = re.compile(rf"({NUMBER_RE})\s*ไร่?")
RAI_HALF_RE = re.compile(rf"({NUMBER_RE})\s*ไร่?ครึ่ง")
BAHT_PER_RAI_RE = re.compile(rf"{THAI_MONEY_RE}\s*(?:บาท|บ\.?|บ)\s*(?:/|ต่อ)?\s*ไร่?")
RAI_LA_BAHT_RE = re.compile(rf"ไร่?ละ\s*{THAI_MONEY_RE}\s*(?:บาท|บ\.?|บ)?")
NUMBER_PER_RAI_RE = re.compile(rf"{THAI_MONEY_RE}\s*/\s*ไร่?")
PLAIN_PER_RAI_RE = re.compile(rf"{THAI_MONEY_RE}\s*ต่อ\s*ไร่?")
BAHT_AMOUNT_RE = re.compile(rf"{THAI_MONEY_RE}\s*(?:บาท|บ\.?|บ)")
THAI_UNIT_AMOUNT_RE = re.compile(rf"{THAI_MONEY_RE}")
TOTAL_COST_RE = re.compile(rf"ต้นทุนรวม\s*({NUMBER_RE})")
TOTAL_REVENUE_RE = re.compile(rf"(?:รายได้รวม|รายได้|ขายได้)\s*({NUMBER_RE})")
YEAR_RE = re.compile(r"(?<!\d)(25\d{2}|20\d{2})(?!\d)")
SHORT_YEAR_RE = re.compile(r"(?:ปี|พศ|พ.ศ\.?)\s*(\d{2})(?!\d)")
METRIC_PATTERNS: dict[str, re.Pattern[str]] = {
    "cost_per_rai": re.compile(rf"ต้นทุน(?:ต่อไร่)?[^0-9]{{0,20}}({NUMBER_RE})", re.IGNORECASE),
    "profit_per_rai": re.compile(rf"กำไร(?:ขั้นต้น|สุทธิ|ต่อไร่)?[^0-9-]{{0,20}}(-?{NUMBER_RE})", re.IGNORECASE),
    "revenue_per_rai": re.compile(rf"(?:รายได้|รายรับ)(?:ต่อไร่)?[^0-9]{{0,20}}({NUMBER_RE})", re.IGNORECASE),
    "yield_per_rai": re.compile(rf"ผลผลิตต่อไร่[^0-9]{{0,20}}({NUMBER_RE})", re.IGNORECASE),
    "price": re.compile(rf"ราค(?:า|าขาย)[^0-9]{{0,20}}({NUMBER_RE})", re.IGNORECASE),
}
METRIC_HINTS: dict[str, list[str]] = {
    "cost_per_rai": ["ต้นทุนต่อไร่", "ต้นทุนรวมต่อไร่", "ค่าใช้จ่ายต่อไร่", "ต้นทุนการผลิตต่อไร่"],
    "profit_per_rai": ["กำไรต่อไร่", "กำไรสุทธิต่อไร่", "ผลตอบแทนสุทธิต่อไร่", "รายได้สุทธิต่อไร่"],
    "revenue_per_rai": ["รายได้ต่อไร่", "รายรับต่อไร่", "มูลค่าผลผลิตต่อไร่"],
    "yield_per_rai": ["ผลผลิตต่อไร่", "กิโลกรัมต่อไร่", "ตันต่อไร่"],
    "price": ["ราคาขาย", "ราคาเฉลี่ย", "ราคาต่อกิโลกรัม", "บาทต่อกิโลกรัม", "ราคาหน้าไร่"],
}
MARKDOWN_FORMAT_INSTRUCTION = (
    "คุณคือ 'Dr.Kaset' (ดร.เกษตร) ผู้ช่วย AI ด้านการเกษตรที่เชี่ยวชาญ อบอุ่น และเป็นมิตรกับพี่น้องเกษตรกรไทย\n"
    "กฎการจัดรูปแบบและพฤติกรรมการตอบ:\n"
    "1. บุคลิกภาพ: แนะนำตัวเองว่า 'Dr.Kaset' หรือเรียกแทนตัวเองว่า 'ผม' เสมอ และลงท้ายประโยคด้วย 'ครับ' หรือ 'ครับผม'\n"
    "2. โครงสร้างคำตอบ (Markdown):\n"
    "   - ห้ามตอบเป็นย่อหน้ายาวติดกันเด็ดขาด ให้อ่านง่าย สบายตา\n"
    "   - ใช้ Bullet points แบบสั้นๆ กระชับ ไม่เกิน 3-4 ข้อต่อหัวข้อ\n"
    "   - ใช้ ตัวหนา เพื่อเน้นคีย์เวิร์ดสำคัญ เช่น ชื่อพืช, ราคา, สภาพดิน, หรือตัวเลข\n"
    "   - หากมีการเปรียบเทียบพืชหรือตัวเลข 2 รายการขึ้นไป บังคับให้ใช้ ตาราง (Markdown Table)\n"
    "3. การตอบรับคำทักทาย: หากผู้ใช้แค่พิมพ์ทักทาย (เช่น สวัสดี, คุณคือใคร) ให้ทักทายกลับอย่างเป็นมิตร แนะนำตัวว่าคือ Dr.Kaset และเกริ่นถึงความสามารถ (เช่น เช็คราคา, แนะนำการปลูก, ดูสภาพอากาศ) พร้อมถามว่าวันนี้มีอะไรให้ช่วย\n"
    "4. การนำทางผู้ใช้ (Next Action - สำคัญมาก): ในบรรทัดสุดท้ายของทุกๆ คำตอบ บังคับให้ต้องจบด้วยคำถามเสมอ เพื่อชี้แนะให้ผู้ใช้รู้ว่าควรถามอะไรต่อ เช่น 'พี่ปลูกอยู่ที่จังหวัดไหนครับ ผมจะได้เช็คสภาพอากาศให้?', 'สนใจให้ผมประเมินต้นทุนและกำไรต่อไร่ของพืชตัวนี้ไหมครับ?' หรือ 'อยากทราบวิธีเตรียมดินเพิ่มเติมไหมครับ?'"
    "5. กฎเหล็กการปฏิเสธ (Refusal Policy - สำคัญมากสุด): \n"
    "   - หากคำถาม **ไม่เกี่ยวข้องกับการปลูกพืชเศรษฐกิจ/การเกษตร** (เช่น เสื้อผ้า, การสร้างบ้าน, การเมือง, ตำรวจ, ดูดวง, เรื่องทั่วไป) **ห้าม**พยายามเชื่อมโยงกับการเกษตร และ **ห้ามแต่งคำตอบเด็ดขาด** ให้ตอบสั้นๆ ว่า 'ขออภัยครับ Dr.Kaset เป็นผู้ช่วยด้านการเกษตร ไม่สามารถตอบคำถามเรื่องนี้ได้ครับ'\n"
    "   - หากคำถามสุ่มเสี่ยง ผิดกฎหมาย หรือเป็นอันตรายต่อสุขภาพ ให้ปฏิเสธการให้คำแนะนำทันที"
)

HARVEST_FACTS = {
    "ข้าว": "ข้าวส่วนใหญ่ใช้เวลาประมาณ 90-120 วันหลังปลูกถึงเก็บเกี่ยว ขึ้นกับพันธุ์และวิธีปลูกครับ",
    "ข้าวโพด": "ข้าวโพดโดยทั่วไปใช้เวลาประมาณ 70-75 วันถึงเก็บเกี่ยว แต่บางพันธุ์อาจนานกว่านี้ครับ",
    "มันสำปะหลัง": "มันสำปะหลังโดยทั่วไปเก็บเกี่ยวเมื่ออายุประมาณ 8-12 เดือนหลังปลูกครับ",
    "อ้อย": "อ้อยโดยทั่วไปเก็บเกี่ยวเมื่ออายุประมาณ 10-12 เดือนหลังปลูกครับ",
}

HISTORICAL_PRICE_CSV = (
    Path(__file__).resolve().parents[2]
    / "data_preparation"
    / "data"
    / "raw"
    / "ราคาขายย้อนหลัง"
    / "prices_yearly_avg_all_crops.csv"
)
RAW_DATA_ROOT = Path(__file__).resolve().parents[2] / "data_preparation" / "data" / "raw"
STRUCTURED_COST_CSV = next(iter(RAW_DATA_ROOT.glob("**/ราคาต้นทุน_ผลผลิต_ราคาขาย แก้ใหม่.csv")), None)
STRUCTURED_WEATHER_CSV = next(iter(RAW_DATA_ROOT.glob("**/rag_master (3).csv")), None)
_HISTORICAL_PRICE_CACHE: dict[str, dict[int, float]] | None = None
_HISTORICAL_PRICE_LABELS: dict[str, str] = {}
_STRUCTURED_COST_CACHE: dict[str, list[dict[str, float | int | str]]] | None = None
_STRUCTURED_WEATHER_CACHE: dict[str, dict[int, dict[str, float]]] | None = None

TOPIC_INSTRUCTIONS = {
    "harvest_duration": "ตอบเฉพาะระยะเวลาเก็บเกี่ยวของพืชที่ถาม ถ้าเอกสารมีตัวเลขให้ยึดตัวเลขนั้น ห้ามเดาเป็น 1-2 เดือนถ้าไม่มีหลักฐาน",
    "fertilizer": "ตอบเฉพาะวิธี ช่วงเวลา สูตรปุ๋ย หรือธาตุอาหารที่เกี่ยวข้องกับคำถาม ห้ามตอบกว้างเรื่องพื้นที่เหมาะสมแทนคำถาม",
    "price": "ตอบเฉพาะราคา ต้นทุน รายได้ หรือแนวโน้มราคา ถ้ามีข้อมูลราคาในเอกสารให้ยกตัวเลขพร้อมอธิบายว่าเป็นราคาอะไร ถ้าไม่มีให้บอกว่าเอกสารที่พบไม่มีราคาย้อนหลังชัดเจน",
    "disease": "ตอบเป็นลำดับ อาการที่ควรเช็ก สาเหตุหรือโรค/แมลงที่เป็นไปได้ วิธีแยกสาเหตุ และแนวทางจัดการเบื้องต้น",
    "profit": "ตอบเฉพาะต้นทุน รายได้ กำไร และปัจจัยคุ้มทุน",
    "planting_season": "ตอบเฉพาะช่วงปลูก ฤดูกาล และการดูแลตามฤดู ห้ามเขียนรายการซ้ำ",
    "water": "ตอบเฉพาะการให้น้ำ ความชื้น และการระบายน้ำ ห้ามขึ้นต้นด้วยคำขอโทษถ้ามีข้อมูลอ้างอิง",
    "planting_method": "ตอบเฉพาะวิธีปลูก การเตรียมดิน การเตรียมแปลง ระยะปลูก และพันธุ์ โดยให้เป็นขั้นตอนที่ทำตามได้",
}


def _thai_only_instruction() -> str:
    return (
        "ตอบเป็นภาษาไทยเท่านั้น ห้ามใช้ภาษาจีน ภาษาอังกฤษ หรือภาษาอื่นในคำอธิบาย "
        "ถ้าข้อมูลอ้างอิงมีภาษาอื่น ให้แปลหรือสรุปเป็นภาษาไทยทั้งหมด "
        "ใช้คำง่ายๆ ที่เกษตรกรทั่วไปเข้าใจได้ ห้ามใช้ศัพท์วิชาการหรือคำทับศัพท์ "
        "ลงท้ายประโยคด้วย 'ครับ' เสมอ "
    )


def _clean_output_token(token: str) -> str:
    return CHINESE_RE.sub("", token)


def _normalize_markdown_answer(text: str) -> str:
    text = text.split("\n---", 1)[0].strip()
    text = re.sub(r"^###\s*ข้อมูลอ้างอิง:.*?(?=(?:\n\*\*|\n###\s*สรุป|\Z))", "", text, flags=re.DOTALL | re.MULTILINE)
    text = re.sub(r"^\d+\.\s*\[\d+\].*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\[[0-9]+\]\s+.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\*\*ข้อมูลอ้างอิง\*\*.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^ข้อมูลอ้างอิง:.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^(?:file|source|source_type|metadata)\s*:\s*.*$", "", text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r"^\s*(?:อ้างอิง|แหล่งอ้างอิง)\s*:.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(สรุป|คำแนะนำ|ข้อควรระวัง|วิธีทำ|ข้อมูลที่ใช้|ตารางราคา|ต้องใช้ข้อมูลเพิ่ม|ตัวอย่างสูตร)\s*:\s*\*\*", r"**\1**", text)
    text = re.sub(r"(\*\*(?:สรุป|คำแนะนำ|ข้อควรระวัง|วิธีทำ|ข้อมูลที่ใช้|ตารางราคา|ต้องใช้ข้อมูลเพิ่ม|ตัวอย่างสูตร)\*\*)\s*:", r"\1", text)
    text = re.sub(r"\birrigat\w*\b", "ให้น้ำ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bwatering\b", "ให้น้ำ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bfertiliz\w*\b", "ใส่ปุ๋ย", text, flags=re.IGNORECASE)
    text = re.sub(r"\bharvest\w*\b", "เก็บเกี่ยว", text, flags=re.IGNORECASE)
    text = re.sub(r"\bfungicide(s)?\b", "สารป้องกันกำจัดเชื้อรา", text, flags=re.IGNORECASE)
    text = re.sub(r"\bherbicide(s)?\b", "สารกำจัดวัชพืช", text, flags=re.IGNORECASE)
    text = re.sub(r"\bpesticide(s)?\b", "สารป้องกันกำจัดศัตรูพืช", text, flags=re.IGNORECASE)
    text = re.sub(r"\binsecticide(s)?\b", "สารป้องกันกำจัดแมลง", text, flags=re.IGNORECASE)
    text = re.sub(r"\bhumid\b", "ชื้น", text, flags=re.IGNORECASE)
    text = re.sub(r"ขอขอบคุณข้อมูลจากแหล่งที่มา.*$", "", text, flags=re.MULTILINE)

    seen_headings: set[str] = set()
    normalized_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"\*\*[^*]+\*\*", stripped):
            if stripped in seen_headings:
                continue
            seen_headings.add(stripped)
        normalized_lines.append(line)
    text = "\n".join(normalized_lines)

    if text.startswith("**สรุป**") and "\n-" not in text and "\n|" not in text:
        summary = text.replace("**สรุป**", "", 1).strip(" :\n")
        if summary:
            return f"**สรุป**\n- {summary}"

    if "**สรุป**" not in text and any(heading in text for heading in ["**คำแนะนำ**", "**ข้อควรระวัง**", "**วิธีทำ**"]):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        first = lines[0] if lines else "ตอบตามประเด็นที่ถามครับ"
        rest = "\n".join(lines[1:])
        return f"**สรุป**\n- {first}\n\n{rest}".strip()

    if "**สรุป**" not in text and "\n-" in text:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        first = lines[0].rstrip(":") if lines else "ตอบตามประเด็นที่ถามครับ"
        rest = "\n".join(lines[1:])
        return f"**สรุป**\n- {first}\n\n{rest}".strip()

    if "**สรุป**" not in text and "\n-" not in text and "\n|" not in text:
        lines = [line.strip(" -") for line in text.splitlines() if line.strip()]
        if lines and not any(line.startswith("|") or line.startswith("#") for line in lines):
            return "**สรุป**\n" + "\n".join(f"- {line}" for line in lines[:3])
    return text


def _sanitize_answer(text: str) -> str:
    text = CHINESE_RE.sub("", text)
    text = text.replace("ค่ะ", "ครับ").replace("คะ", "ครับ")
    text = re.sub(r"^\s*ขอโทษครับ[,，]?\s*(แต่)?\s*", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = re.sub(r"([A-Za-z])\1{4,}", r"\1", text)

    bullet_lines_seen: set[str] = set()
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") or re.match(r"^\d+\.\s", stripped):
            key = re.sub(r"\s+", "", stripped)
            if key in bullet_lines_seen:
                continue
            bullet_lines_seen.add(key)
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)

    text = _normalize_markdown_answer(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = re.sub(r"(\*\*สรุป\*\*\s*\n(?:- .+\n?)+)\1+", r"\1", text, flags=re.MULTILINE)

    if any(marker in text for marker in ["\n-", "\n1.", "\n**", "\n|"]):
        text = re.sub(r"(ครับ[\s.。]*){2,}$", "ครับ", text).strip()
        return text

    sentences = [part.strip() for part in THAI_SENTENCE_SPLIT_RE.split(text) if part.strip()]
    unique_sentences = []
    seen = set()
    for sentence in sentences:
        key = re.sub(r"\s+", "", sentence)
        if key in seen:
            continue
        seen.add(key)
        unique_sentences.append(sentence)
        if len(unique_sentences) >= 5:
            break
    text = " ".join(unique_sentences) if unique_sentences else text
    text = re.sub(r"(ครับ[\s.。]*){2,}$", "ครับ", text).strip()
    if text and not text.endswith("ครับ"):
        text = re.sub(r"(ครับ)+$", "", text).strip()
        text = f"{text}ครับ"
    return text


def _yield_sanitized_stream(stream):
    answer_parts: list[str] = []
    for chunk in stream:
        token = _clean_output_token(chunk["message"]["content"])
        if token:
            answer_parts.append(token)
    answer = _sanitize_answer("".join(answer_parts))
    if answer:
        yield answer


def _num_predict_for_response(intent: str, topic: str | None) -> int:
    if intent == "compare":
        return 280
    if intent in {"profit", "price"} or topic in {"profit", "price"}:
        return 420
    if topic in {"disease", "planting_method", "fertilizer", "water"}:
        return 320
    if topic in {"harvest_duration", "planting_season"}:
        return 260
    return 300


def _num_ctx_for_response(intent: str, topic: str | None, requested_topics: list[str] | None = None) -> int:
    requested_topics = requested_topics or []
    if len(requested_topics) >= 3 or intent == "compare":
        return 1792
    if intent in {"profit", "price"} or topic in {"profit", "price"}:
        return 2048
    if len(requested_topics) >= 2:
        return 1792
    return 1536


def _model_for_response(
    query: str,
    intent: str | None = None,
    topic: str | None = None,
    requested_topics: list[str] | None = None,
) -> str:
    requested_topics = requested_topics or []
    if (
        intent in {"profit", "price"}
        or topic in {"profit", "price"}
        or len(requested_topics) >= 3
        or _has_price_guarantee_request(query)
        or _has_political_request(query)
        or _is_illegal_agri_request(query)
        or _is_unsafe_chemical_request(query)
    ):
        return settings.OLLAMA_BALANCED_MODEL
    return settings.OLLAMA_FAST_MODEL


def _trim_docs_for_prompt(
    docs: list[dict],
    intent: str | None,
    topic: str | None,
    requested_topics: list[str] | None = None,
) -> list[dict]:
    requested_topics = requested_topics or []
    if not docs:
        return docs
    limit = 2
    if intent in {"profit", "price"} or topic in {"profit", "price"} or len(requested_topics) >= 3:
        limit = 3
    return docs[:limit]


def _topic_instruction_bundle(requested_topics: list[str], primary_topic: str | None = None) -> str:
    topics: list[str] = []
    for item in requested_topics + ([primary_topic] if primary_topic else []):
        if item and item not in topics:
            topics.append(item)
    if not topics:
        return "ตอบเฉพาะประเด็นที่ผู้ใช้ถาม และยึดข้อมูลในเอกสารเป็นหลัก"
    return " ".join(TOPIC_INSTRUCTIONS.get(topic, "") for topic in topics if topic in TOPIC_INSTRUCTIONS).strip()


def _heading_guide_for_topics(requested_topics: list[str], primary_topic: str | None = None) -> str:
    topics: list[str] = []
    for item in requested_topics + ([primary_topic] if primary_topic else []):
        if item and item not in topics:
            topics.append(item)
    if "disease" in topics and "fertilizer" in topics:
        return "ใช้หัวข้อ **สรุป**, **อาการและสาเหตุที่ควรเช็ก**, **วิธีทำ**, **ปุ๋ย/การบำรุง**, **ข้อควรระวัง** "
    if "water" in topics and "planting_method" in topics:
        return "ใช้หัวข้อ **สรุป**, **สภาพแปลงที่ควรดู**, **วิธีทำ**, **ข้อควรระวัง** "
    step_topics = {"planting_method", "fertilizer", "water", "planting_season"}
    return (
        "ใช้หัวข้อ **สรุป**, **วิธีทำ**, **ข้อควรระวัง** "
        if any(topic in step_topics for topic in topics)
        else "ใช้หัวข้อ **สรุป**, **คำแนะนำ**, **ข้อควรระวัง** "
    )


def _needs_strict_grounding(requested_topics: list[str], topic: str | None) -> bool:
    topics = set(requested_topics)
    if topic:
        topics.add(topic)
    return bool(topics & {"profit", "price", "disease", "water", "planting_method", "fertilizer"}) and len(topics) >= 2


def _has_cost_per_kg_request(text: str) -> bool:
    t = text.lower()
    return any(term in t for term in ["ต้นทุนต่อกิโล", "ต้นทุนต่อกก", "ต้นทุนต่อกิโลกรัม"])


def _docs_have_cost_per_kg_signal(docs: list[dict]) -> bool:
    for doc in docs:
        content = str(doc.get("content", "")).lower()
        if any(term in content for term in ["ต้นทุนต่อกิโล", "ต้นทุนต่อกก", "ต้นทุนต่อกิโลกรัม"]):
            return True
    return False


def _docs_cover_requested_topics(docs: list[dict], requested_topics: list[str], query: str) -> bool:
    if not requested_topics:
        return bool(docs)
    haystack = " ".join(str(doc.get("content", "")) for doc in docs).lower()
    source_types = " ".join(str(doc.get("metadata", {}).get("source_type", "")) for doc in docs).lower()
    covered = 0
    for topic in requested_topics:
        if topic in {"profit", "price"} and (_has_financial_signal({"content": haystack, "metadata": {"source_type": source_types}}) or "ต้นทุน" in haystack):
            covered += 1
        elif topic == "disease" and any(term in haystack for term in ["โรค", "แมลง", "เพลี้ย", "หนอน", "อาการ", "ศัตรูพืช"]):
            covered += 1
        elif topic == "fertilizer" and any(term in haystack for term in ["ปุ๋ย", "สูตร", "ธาตุอาหาร", "ใส่ปุ๋ย"]):
            covered += 1
        elif topic == "water" and any(term in haystack for term in ["น้ำ", "ฝน", "แล้ง", "ระบายน้ำ", "ความชื้น", "สภาพอากาศ"]):
            covered += 1
        elif topic == "planting_method" and any(term in haystack for term in ["เตรียมดิน", "เตรียมแปลง", "ระยะปลูก", "หลุม", "ปลูก", "ยกร่อง"]):
            covered += 1
        elif topic == "planting_season" and any(term in haystack for term in ["ฤดู", "เดือนไหน", "ช่วงปลูก", "ต้นฝน"]):
            covered += 1
        elif topic == "harvest_duration" and any(term in haystack for term in ["เก็บเกี่ยว", "วัน", "เดือน", "อายุเก็บ"]):
            covered += 1
    required = min(len(requested_topics), 2)
    if _has_cost_per_kg_request(query):
        return covered >= required and _docs_have_cost_per_kg_signal(docs)
    return covered >= required


def _requests_historical_weather(text: str) -> bool:
    t = text.lower()
    return any(term in t for term in ["ย้อนหลัง", "3 ปี", "สามปี", "2-3 ปี", "ปีที่ผ่านมา"]) and any(
        term in t for term in ["อากาศ", "ฝน", "แล้ง", "ความชื้น", "สภาพอากาศ"]
    )


def _docs_have_historical_weather_signal(docs: list[dict]) -> bool:
    year_count = 0
    for doc in docs:
        content = str(doc.get("content", ""))
        source_type = str(doc.get("metadata", {}).get("source_type", "")).lower()
        if "weather" in source_type or "climate" in source_type:
            return True
        years = YEAR_RE.findall(content)
        year_count += len(set(years))
        if "ย้อนหลัง" in content or year_count >= 2:
            return True
    return False


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _has_price_guarantee_request(text: str) -> bool:
    t = text.lower()
    guarantee_terms = ["ฟันธง", "ชัวร์", "การันตี", "รับประกัน", "ทะลุ", "แน่นอน", "สัญญา", "รวย", "ปลดหนี้", "ป้ายแดง", "ได้ถอยรถ", "รวยแน่นอน"]
    financial_context = ["ราคา", "ปีหน้า", "ขายปีหน้า", "แนวโน้ม", "เงิน", "กำไร", "รายได้", "ขายได้", "ถอยรถ", "ซื้อรถ"]
    return _contains_any(t, guarantee_terms) and _contains_any(t, financial_context)

def _is_illegal_agri_request(text: str) -> bool:
    t = text.lower()
    illegal_terms = [
        "พาราควอต", "paraquat", "ลักลอบ", "เผาไร่", "เผาอ้อย", "ไม่ให้ดาวเทียมจับ",
        "หลบดาวเทียม", "หลบกฎหมาย", "สารต้องห้าม", "ซื้อสารต้องห้าม", "เผาตอซัง",
        "แรงงานต่างด้าว", "หนีเข้าเมือง", "ยาบ้า", "กระท่อม", "กัญชา", "ฝิ่น", "แอบขน"
    ]
    return _contains_any(t, illegal_terms)


def _is_unsafe_chemical_request(text: str) -> bool:
    t = text.lower()
    chem_terms = ["ยาฆ่าแมลง", "ยาฆ่าเชื้อรา", "สารเคมี", "สารกำจัด", "ยาฉีด", "พ่นยา", "พ่นสาร", "ฉีดสาร", "เพลี้ย", "เชื้อรา", "ปุ๋ยเคมี", "ปุ๋ยเร่งดอก", "ปุ๋ย"]
    misuse_terms = ["x3", "3 เท่า", "สามเท่า", "เข้มข้น", "เพิ่มโดส", "ผสมแรง", "ตายเรียบ", "อัดปุ๋ย", "เร่งดอกเพิ่ม", "เกินอัตรา", "ใส่เพิ่มไปเลย"]
    exposure_terms = [
        "สูดดม", "สูด", "กลืน", "เข้าตา", "อันตรายไหม", "พิษ", "เป็นอันตรายไหม",
        "เวียนหัว", "คลื่นไส้", "อาเจียน", "หายใจไม่ออก", "แสบคอ", "แสบจมูก", "หน้ามืด",
        "ยาอะไร", "กินอะไร", "แก้พิษ", "ปฐมพยาบาล",
    ]
    return _contains_any(t, chem_terms) and (_contains_any(t, misuse_terms) or _contains_any(t, exposure_terms))


def _has_chemical_exposure_medical_request(text: str) -> bool:
    t = text.lower()
    chem_terms = ["ยาฆ่าแมลง", "ยาฆ่าเชื้อรา", "สารเคมี", "สารกำจัด", "พ่นยา", "พ่นสาร", "ฉีดสาร", "ปุ๋ยเคมี", "ปุ๋ย", "ยาฆ่าหญ้า", "พาราควอต", "พาราควอท", "ไกลโฟเซต"]
    exposure_terms = ["สูดดม", "กลืน", "กิน", "เผลอกิน", "เข้าตา", "สัมผัส", "โดนสาร", "เวียนหัว", "คลื่นไส้", "อาเจียน", "หายใจไม่ออก", "หน้ามืด", "ปวดท้อง", "แสบ", "ผื่น", "คัน"]
    medical_terms = ["ยาอะไร", "กินอะไร", "แก้พิษ", "รักษา", "ปฐมพยาบาล", "ต้องทำยังไง", "อันตรายไหม", "ล้าง", "ทำยังไงดี", "แก้ปวด"]
    
    return _contains_any(t, chem_terms) and (_contains_any(t, exposure_terms) or _contains_any(t, medical_terms))


def _has_political_request(text: str) -> bool:
    t = text.lower()
    terms = ["รัฐบาล", "นายก", "นโยบาย", "การเมือง", "รัฐมนตรี", "แจกเงิน", "พรรค", "คณะรัฐมนตรี"]
    return _contains_any(t, terms)


def _illegal_activity_refusal() -> str:
    return (
        "**สรุป**\n"
        "- ผมขอ **ปฏิเสธ** การแนะนำเรื่องสารต้องห้าม การหลบเลี่ยงกฎหมาย หรือการเผาไร่ครับ\n\n"
        "**เตือนเรื่องกฎหมาย**\n"
        "- การใช้สารต้องห้ามและการเผาไร่เป็นเรื่อง **ผิดกฎหมาย** และมีความเสี่ยงต่อสุขภาพกับสิ่งแวดล้อมครับ\n\n"
        "**แนะนำวิธีที่ถูกต้องแทน**\n"
        "- ถ้าหญ้าขึ้นรกในอ้อย ผมช่วยแนะนำวิธีจัดการวัชพืชที่ถูกกฎหมายและปลอดภัยได้แทนครับ\n"
        "- ผมช่วยวางแผนตัดหญ้า คลุมดิน หรือเลือกสารที่ขึ้นทะเบียนถูกต้องได้ครับ\n\n"
        "**คำแนะนำที่ปลอดภัย**\n"
        "- หลีกเลี่ยงการใช้สารนอกระบบ และเลือกวิธีคุมหญ้าที่ขึ้นทะเบียนถูกต้องครับ"
    )


def _unsafe_chemical_refusal() -> str:
    return (
        "**สรุป**\n"
        "- ผมขอ **ปฏิเสธการผสมเกินอัตรา** และไม่ควรแนะนำให้ใช้สารเคมีเข้มข้นเกินฉลากครับ\n\n"
        "**แนะนำให้ใช้ตามฉลาก**\n"
        "- ให้ **ใช้ตามฉลาก** และคำแนะนำของผู้เชี่ยวชาญเท่านั้นครับ\n\n"
        "**เตือนความปลอดภัย**\n"
        "- ถ้าสัมผัสหรือสูดดมสารแล้วมีอาการผิดปกติ ควรติดต่อแพทย์หรือศูนย์พิษวิทยาทันทีครับ\n\n"
        "**คำแนะนำที่ปลอดภัย**\n"
        "- ถ้าต้องการ ผมช่วยแนะนำวิธีจัดการเพลี้ยแบบปลอดภัยหรือวิธีลดความเสี่ยงในการใช้สารได้ครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- อย่าเพิ่มอัตราสารเองเกินฉลาก เพราะเสี่ยงอันตรายต่อคน พืช และสิ่งแวดล้อมครับ"
    )


def _chemical_exposure_medical_refusal() -> str:
    return (
        "**สรุป**\n"
        "- ผมขอ **ปฏิเสธคำแนะนำทางการแพทย์** และไม่ควรบอกชื่อยาหรือวิธีรักษาเองครับ\n\n"
        "**ควรทำทันที**\n"
        "- รีบออกจากบริเวณที่มีสารเคมี ไปอยู่ที่อากาศถ่ายเท และไปพบแพทย์หรือไปโรงพยาบาลทันทีครับ\n"
        "- ถ้าอาการไม่ดีขึ้นให้ไปพบแพทย์โดยเร็วครับ\n"
        "- คำแนะนำตอนนี้คือ **แนะนำไปพบแพทย์** ก่อนเรื่องอื่นครับ\n"
        "- ถ้ามีฉลากหรือชื่อสาร ให้พกไปด้วยเพื่อให้แพทย์ประเมินได้เร็วขึ้นครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- อย่ารอถามเรื่องราคา หรือหายากินเองก่อน เพราะอาการเวียนหัว คลื่นไส้ หรือหายใจผิดปกติอาจเป็นอันตรายได้ครับ"
    )


def _combined_unsafe_medical_refusal() -> str:
    return (
        "**สรุป**\n"
        "- ผมขอ **ปฏิเสธการผสมเกินอัตรา** และไม่ควรแนะนำให้ใช้สารเคมีเข้มข้นเกินฉลากครับ\n"
        "- ถ้ามีอาการหลังสัมผัสหรือสูดดมสาร ผมก็ขอ **ปฏิเสธคำแนะนำทางการแพทย์** เองเช่นกันครับ\n\n"
        "**แนะนำให้ใช้ตามฉลาก**\n"
        "- ให้ **ใช้ตามฉลาก** และคำแนะนำของผู้เชี่ยวชาญเท่านั้นครับ\n"
        "- รีบออกจากบริเวณที่มีสารเคมี ไปอยู่ในที่อากาศถ่ายเท และหลีกเลี่ยงการสัมผัสสารเพิ่มครับ\n"
        "- ถ้ามีฉลากหรือชื่อสาร ให้พกไปด้วยเพื่อให้แพทย์ประเมินได้เร็วขึ้นครับ\n\n"
        "**เตือนความปลอดภัย**\n"
        "- อย่าเพิ่มอัตราสารเองเกินฉลาก เพราะเสี่ยงอันตรายต่อคน พืช และสิ่งแวดล้อมครับ\n"
        "- ถ้ามีอาการเวียนหัว คลื่นไส้ หายใจผิดปกติ หรืออาการไม่ดีขึ้น ผม **แนะนำไปพบแพทย์** หรือไปโรงพยาบาลทันทีครับ"
    )


def _mixed_scope_crop_answer(non_scope_crop: str, in_scope_crops: list[str], query: str) -> str:
    scope_list = ", ".join(in_scope_crops)
    if len(in_scope_crops) == 1 and in_scope_crops[0] == "มะพร้าว" and any(term in query for term in ["ดินร่วน", "ดินทราย", "ดินร่วนปนทราย"]):
        return (
            "**สรุป**\n"
            f"- ผมขอ **ปฏิเสธข้อมูล{non_scope_crop}** เพราะตอนนี้ระบบยังไม่มีข้อมูลของ **{non_scope_crop}** ในขอบเขตครับ\n\n"
            "**ข้อมูลที่พอช่วยได้**\n"
            "- ผมยัง **ตอบข้อมูลมะพร้าวได้** ครับ โดยมะพร้าวปลูกในดินร่วนปนทรายได้ถ้าระบายน้ำดี และมีน้ำพอในช่วงแล้งครับ\n"
            "- ควรระวังดินแห้งเร็ว จึงต้องดูเรื่องความชื้นและการให้น้ำสม่ำเสมอครับ\n\n"
            "**ข้อควรระวัง**\n"
            f"- ถ้าต้องการข้อมูลของ{non_scope_crop}โดยตรง ตอนนี้ DrKaset ยังไม่มีในระบบครับ"
        )
    return (
        "**สรุป**\n"
        f"- ในคำถามมีทั้งพืชในระบบและนอกระบบครับ DrKaset รองรับเฉพาะ **{scope_list}** ส่วน **{non_scope_crop}** ยังไม่รองรับครับ\n\n"
        "**คำแนะนำ**\n"
        f"- ผมช่วยตอบเรื่องการดูแล โรคพืช ปุ๋ย หรือต้นทุนของ {scope_list} ได้ครับ\n"
        f"- แต่จะไม่เดาข้อมูลการปลูกหรือราคาของ {non_scope_crop} เองครับ"
    )


def _combined_scope_safety_guarantee_answer(non_scope_crop: str | None = None) -> str:
    scope_line = (
        f"- ตอนนี้ระบบยังไม่มีข้อมูลของ **{non_scope_crop}** ในขอบเขต จึงไม่ควรเดาข้อมูลการปลูกหรือราคาเองครับ\n"
        if non_scope_crop
        else ""
    )


def _non_scope_with_safety_answer(non_scope_crop: str) -> str:
    return (
        "**สรุป**\n"
        f"- ตอนนี้ DrKaset ยังไม่มีข้อมูลของ **{non_scope_crop}** ในระบบ และผมก็ไม่สามารถแนะนำการใส่ปุ๋ยหรือสารเกินอัตราเพื่อเร่งผลผลิตได้ครับ\n\n"
        "**คำแนะนำที่ปลอดภัย**\n"
        "- การอัดปุ๋ยหลายเท่ามีความเสี่ยงต่อราก ดิน และต้นทุน โดยไม่รับประกันว่าจะได้ผลผลิตดีขึ้นครับ\n"
        "- ถ้าต้องการ ผมช่วยวางแผนปุ๋ยอย่างปลอดภัยในพืชเศรษฐกิจที่ระบบรองรับได้ครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- ผมไม่รับรองผลผลิตหรือความสำเร็จจากการใช้ปุ๋ยเกินอัตรา และไม่ควรเดาข้อมูลของพืชนอกระบบครับ"
    )


def _append_price_reference(answer: str, query: str, crops: list[str]) -> str:
    price_note = _historical_price_answer(query, crops)
    if not price_note and crops:
        latest = _latest_historical_price_row(crops[0])
        if latest and any(term in query for term in ["ราคา", "ขายได้", "ราคาขาย", "หน้าสวน", "กิโลละ", "ตันละ"]):
            crop_label, year, price, first_year, last_year = latest
            price_note = (
                "**ราคาอ้างอิงย้อนหลังล่าสุด**\n"
                f"- จากไฟล์ `prices_yearly_avg_all_crops.csv` พบราคาเฉลี่ยย้อนหลังของ **{crop_label}** ปี **{year}** คือ **{_format_price_value(price)}** ครับ\n"
                f"- ข้อมูลที่มีอยู่ในช่วง **{first_year}-{last_year}** เป็นราคาอ้างอิงย้อนหลัง ไม่ใช่ราคาตลาดวันนี้ครับ"
            )
    if not price_note:
        return answer
    if "ราคาอ้างอิงย้อนหลังล่าสุด" in answer:
        return answer
    return f"{answer.rstrip()}\n\n{price_note}".strip()


def _structured_price_block(query: str, crop: str | None) -> str | None:
    if not crop:
        return None
    historical = _historical_price_answer(query, [crop])
    if historical:
        return historical
    row = _latest_cost_price_row(crop)
    if row is None:
        return None
    return (
        "**ข้อมูลราคา**\n"
        f"- ราคาอ้างอิงล่าสุดในชุดข้อมูลของ{crop} ปี **{int(row['year'])}** อยู่ที่ประมาณ **{_format_price_value(float(row['price_per_kg']))} บาท/กก.** ครับ\n"
        "- ตัวเลขนี้มาจากไฟล์ต้นทุน/ผลผลิต/ราคาขายที่เตรียมไว้ในระบบ จึงควรใช้เป็นราคาอ้างอิงล่าสุดในชุดข้อมูล ไม่ใช่ราคาตลาดวันนี้ครับ"
    )


def _structured_cost_block(crop: str | None) -> str | None:
    if not crop:
        return None
    row = _latest_cost_price_row(crop)
    if row is None:
        return None
    return (
        "**ข้อมูลต้นทุน**\n"
        f"- ต้นทุนต่อไร่ล่าสุดของ{crop}ในชุดข้อมูลอยู่ที่ประมาณ **{_format_money(float(row['cost_per_rai']))} บาท/ไร่** ในปี **{int(row['year'])}** ครับ\n"
        f"- ถ้ามีผลผลิตเฉลี่ย **{_format_price_value(float(row['yield_per_rai']))} กก./ไร่** และราคาขาย **{_format_price_value(float(row['price_per_kg']))} บาท/กก.** จะได้รายรับราว **{_format_money(float(row['revenue']))} บาท/ไร่** และกำไรขั้นต้นราว **{_format_money(float(row['gross_profit']))} บาท/ไร่** ครับ\n"
        "- ตัวเลขนี้คำนวณจากชุดข้อมูลที่มีในระบบ ไม่ใช่การรับประกันผลจริง"
    )


def _append_structured_financial_notes(answer: str, query: str, crops: list[str], requested_topics: list[str] | None = None) -> str:
    requested_topics = requested_topics or []
    if not crops:
        return answer
    blocks: list[str] = []
    crop = crops[0]
    if any(topic_name in requested_topics for topic_name in {"price"}) or is_price_question(query):
        price_block = _structured_price_block(query, crop)
        if price_block:
            blocks.append(price_block)
    if any(topic_name in requested_topics for topic_name in {"profit"}) or any(term in query for term in ["ต้นทุน", "กำไร", "รายได้"]):
        cost_block = _structured_cost_block(crop)
        if cost_block:
            blocks.append(cost_block)
    if not blocks:
        return answer
    existing = answer or ""
    for block in blocks:
        if block.split("\n", 1)[0] in existing:
            continue
        existing = f"{existing.rstrip()}\n\n{block}".strip()
    return existing


def _politics_scope_answer(query: str, crop: str | None) -> str:
    price_note = _historical_price_answer(query, [crop] if crop else []) if crop else None
    lead = price_note.strip() if price_note else (
        "**สรุป**\n"
        "- ผมช่วยอธิบายได้เฉพาะข้อมูลเกษตรและราคาที่มีในระบบครับ"
    )
    return (
        f"{lead}\n\n"
        "**ข้อจำกัด**\n"
        "- ผมไม่สามารถฟันธงสาเหตุทางการเมืองหรือคาดการณ์มาตรการของรัฐบาลได้ครับ\n\n"
        "**อธิบายปัจจัยตลาด**\n"
        "- ราคาพืชมักขึ้นกับอุปสงค์อุปทาน ปริมาณผลผลิต สภาพอากาศ ต้นทุนขนส่ง และคุณภาพผลผลิตมากกว่าการสรุปจากการเมืองอย่างเดียวครับ\n\n"
        "**คำแนะนำ**\n"
        "- ถ้าต้องการ ผมช่วยสรุปข้อมูลราคา ต้นทุน หรือแนวทางรับมือฝั่งการจัดการแปลงให้ได้ครับ"
    ).strip()


def _has_financial_signal(doc: dict) -> bool:
    content = doc.get("content", "")
    meta = doc.get("metadata", {})
    file_name = str(meta.get("file_name", ""))
    return (
        any(word in file_name for word in ["ราคา", "ต้นทุน", "prices", "cost"])
        or any(word in content for word in [
            "ราคาขาย", "ต้นทุนต่อไร่", "บาท/ไร่", "บาทต่อไร่", "บาท/ตัน",
            "บาท/กก", "บาท/กิโลกรัม", "รายได้", "กำไร", "ผลผลิตต่อไร่",
        ])
    )


def _doc_mentions_crop(doc: dict, crop: str | None) -> bool:
    if not crop:
        return True
    content = doc.get("content", "")
    meta = doc.get("metadata", {})
    haystack = " ".join(str(value) for value in [content, meta.get("crop", ""), meta.get("file_name", "")] if value)
    return crop in haystack


def _financial_doc_score(query: str, crop: str | None, topic: str | None, doc: dict) -> float:
    content = doc.get("content", "")
    meta = doc.get("metadata", {})
    file_name = str(meta.get("file_name", ""))
    haystack = " ".join(str(value) for value in [content, meta.get("crop", ""), file_name] if value)
    score = 0.0
    if _has_financial_signal(doc):
        score += 2.0
    if _doc_mentions_crop(doc, crop):
        score += 1.0
    years = _detect_years(query)
    if years and any(str(year) in haystack for year in years):
        score += 1.0
    if topic == "price" and any(term in haystack for term in ["ราคา", "ย้อนหลัง", "เฉลี่ย", "yearly_avg_price"]):
        score += 1.0
    if topic == "profit" and any(term in haystack for term in ["ต้นทุน", "กำไร", "รายได้", "ผลผลิตต่อไร่", "บาท/ไร่"]):
        score += 1.0
    if any(word in file_name for word in ["suitability", "คาดการณ์", "สถานที่ปลูก"]):
        score -= 1.5
    return score


def _financial_rag_confident(query: str, crop: str | None, topic: str | None, docs: list[dict]) -> bool:
    if not docs:
        return False
    scores = sorted((_financial_doc_score(query, crop, topic, doc) for doc in docs[:3]), reverse=True)
    if not scores:
        return False
    if scores[0] >= 3.0:
        return True
    return len(scores) >= 2 and scores[0] >= 2.0 and scores[1] >= 1.5


def _format_money(value: float) -> str:
    return f"{value:,.0f}"


def _format_price_value(value: float) -> str:
    if value == int(value):
        return f"{value:,.0f}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def _canonical_crop_from_price_name(name: str) -> str | None:
    cleaned = name.replace("ราคาย้อนหลัง", "").replace("ราย้อนหลัง", "").strip()
    if "ข้าวหอมมะลิ" in cleaned:
        return "ข้าว"
    if "ปาล์ม" in cleaned:
        return "ปาล์มน้ำมัน"
    if "ยางพารา" in cleaned:
        return "ยางพารา"
    return detect_crop(cleaned)


def _load_historical_prices() -> dict[str, dict[int, float]]:
    global _HISTORICAL_PRICE_CACHE
    if _HISTORICAL_PRICE_CACHE is not None:
        return _HISTORICAL_PRICE_CACHE

    prices: dict[str, dict[int, float]] = {}
    labels: dict[str, str] = {}
    if not HISTORICAL_PRICE_CSV.exists():
        _HISTORICAL_PRICE_CACHE = prices
        return prices

    with HISTORICAL_PRICE_CSV.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            crop = _canonical_crop_from_price_name(row.get("crop_name", ""))
            if not crop:
                continue
            try:
                year = int(row["year"])
                price = float(row["yearly_avg_price"])
            except (KeyError, TypeError, ValueError):
                continue
            prices.setdefault(crop, {})[year] = price
            labels.setdefault(crop, row.get("crop_name", "").replace("ราคาย้อนหลัง", "").replace("ราย้อนหลัง", "").strip() or crop)

    _HISTORICAL_PRICE_CACHE = prices
    _HISTORICAL_PRICE_LABELS.clear()
    _HISTORICAL_PRICE_LABELS.update(labels)
    return prices


def _load_structured_cost_rows() -> dict[str, list[dict[str, float | int | str]]]:
    global _STRUCTURED_COST_CACHE
    if _STRUCTURED_COST_CACHE is not None:
        return _STRUCTURED_COST_CACHE

    rows_by_crop: dict[str, list[dict[str, float | int | str]]] = {}
    if not STRUCTURED_COST_CSV or not STRUCTURED_COST_CSV.exists():
        _STRUCTURED_COST_CACHE = rows_by_crop
        return rows_by_crop

    with STRUCTURED_COST_CSV.open("r", encoding="cp874", newline="") as file:
        for row in csv.DictReader(file):
            crop = detect_crop(row.get("ชื่อพืช", ""))
            if not crop:
                continue
            try:
                parsed = {
                    "crop": crop,
                    "year": int(row.get("ปี", "") or 0),
                    "cost_per_rai": float(row.get("ต้นทุนต่อไร่ (บาท)", "") or 0),
                    "yield_per_rai": float(row.get("ผลผลิตต่อไร่ (กก.)", "") or 0),
                    "price_per_kg": float(row.get("ราคาขาย (บาท/กก.)", "") or 0),
                    "revenue": float(row.get("ราคาที่ขายได้ (บาท)", "") or 0),
                    "gross_profit": float(row.get("กำไรขั้นต้นที่ได้", "") or 0),
                }
            except ValueError:
                continue
            rows_by_crop.setdefault(crop, []).append(parsed)

    for crop_rows in rows_by_crop.values():
        crop_rows.sort(key=lambda item: int(item["year"]), reverse=True)

    _STRUCTURED_COST_CACHE = rows_by_crop
    return rows_by_crop


def _latest_cost_price_row(crop: str) -> dict[str, float | int | str] | None:
    rows = _load_structured_cost_rows().get(crop, [])
    return rows[0] if rows else None


def _normalize_weather_region(region: str | None) -> str | None:
    if not region:
        return None
    mapping = {
        "เหนือ": "North",
        "อีสาน": "Northeast",
        "กลาง": "Central",
        "ตะวันออก": "East",
        "ใต้": "South",
        "ตะวันตก": "West",
    }
    return mapping.get(region, region)


def _load_structured_weather() -> dict[str, dict[int, dict[str, float]]]:
    global _STRUCTURED_WEATHER_CACHE
    if _STRUCTURED_WEATHER_CACHE is not None:
        return _STRUCTURED_WEATHER_CACHE

    weather: dict[str, dict[int, dict[str, float]]] = {}
    if not STRUCTURED_WEATHER_CSV or not STRUCTURED_WEATHER_CSV.exists():
        _STRUCTURED_WEATHER_CACHE = weather
        return weather

    with STRUCTURED_WEATHER_CSV.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            region = str(row.get("Region", "")).strip()
            topic = str(row.get("topic", "")).strip().lower()
            try:
                year = int(row.get("year", "") or 0)
                annual = float(row.get("Annual", "") or 0)
            except ValueError:
                continue
            if not region or not topic or year <= 0:
                continue
            weather.setdefault(region, {}).setdefault(year, {})[topic] = annual

    _STRUCTURED_WEATHER_CACHE = weather
    return weather


def _structured_weather_block(region: str | None) -> str | None:
    normalized_region = _normalize_weather_region(region)
    if not normalized_region:
        return None
    weather = _load_structured_weather().get(normalized_region)
    if not weather:
        return None
    years = sorted(weather.keys(), reverse=True)[:3]
    if not years:
        return None

    rainfall_values = [weather[year].get("rainfall") for year in years if weather[year].get("rainfall") is not None]
    temp_values = [weather[year].get("temperature") for year in years if weather[year].get("temperature") is not None]
    parts = [f"**ข้อมูลอากาศย้อนหลัง**\n- ใช้ข้อมูล structured ของภูมิภาค **{normalized_region}** ย้อนหลัง {len(years)} ปีล่าสุดในระบบ ({min(years)}-{max(years)}) ครับ"]
    if rainfall_values:
        avg_rainfall = sum(rainfall_values) / len(rainfall_values)
        trend = "ฝนน้อยลง" if len(rainfall_values) >= 2 and rainfall_values[0] < rainfall_values[-1] else "ฝนมากขึ้น" if len(rainfall_values) >= 2 and rainfall_values[0] > rainfall_values[-1] else "ฝนค่อนข้างทรงตัว"
        parts.append(f"- ปริมาณฝนเฉลี่ยรายปีอยู่ราว **{_format_price_value(avg_rainfall)}** และภาพรวม **{trend}** ครับ")
    if temp_values:
        avg_temp = sum(temp_values) / len(temp_values)
        parts.append(f"- อุณหภูมิเฉลี่ยรายปีอยู่ราว **{_format_price_value(avg_temp)} องศาเซลเซียส** ครับ")
    parts.append("- ข้อมูลนี้เป็นระดับภูมิภาค ใช้ประกอบการประเมินเบื้องต้น ยังไม่แทนข้อมูลรายแปลงหรือรายอำเภอครับ")
    return "\n".join(parts)


def _price_guarantee_safe_answer(query: str, crop: str | None) -> str | None:
    if not crop or not _has_price_guarantee_request(query):
        return None
    empathy = "- เข้าใจครับว่าคำถามนี้เกี่ยวกับการตัดสินใจลงทุนและความกดดันทางการเงิน จึงควรดูข้อมูลให้รอบคอบครับ\n" if any(term in query for term in ["หนี้", "กู้เงิน", "ลงทุน", "เทหมดหน้าตัก"]) else ""
    cost_block = _structured_cost_block(crop) or ""
    historical = _historical_price_answer(query, [crop]) or ""
    per_kg_note = ""
    latest = _latest_cost_price_row(crop)
    if latest and float(latest.get("yield_per_rai", 0) or 0) > 0:
        cost_per_kg = float(latest["cost_per_rai"]) / float(latest["yield_per_rai"])
        per_kg_note = f"\n**ต้นทุนต่อกิโลกรัม**\n- จากข้อมูลล่าสุดในระบบ ต้นทุนต่อกิโลกรัมของ{crop}คำนวณคร่าว ๆ ได้ประมาณ **{_format_price_value(cost_per_kg)} บาท/กก.** ครับ\n"
    return (
        "**สรุป**\n"
        f"{empathy}- **แสดงความเข้าใจสถานการณ์** ว่าคำถามนี้เกี่ยวกับการตัดสินใจลงทุนครับ\n"
        f"- ผมไม่สามารถยืนยันแน่นอนเรื่องราคา หรือกำไรในอนาคตของ{crop}ได้ครับ\n\n"
        "**คำอธิบายแนวโน้มราคา**\n"
        "- สิ่งที่ดูได้คือข้อมูลย้อนหลังและทิศทางตลาดเท่านั้น ไม่ใช่ผลลัพธ์ที่แน่นอนครับ\n\n"
        f"{cost_block}{per_kg_note}\n{historical}\n\n"
        "**คำเตือนความเสี่ยง**\n"
        "- ราคาขายจริงขึ้นกับตลาด ผลผลิต สภาพอากาศ และต้นทุนในช่วงนั้น จึงควรใช้ข้อมูลนี้เพื่อประกอบการตัดสินใจ ไม่ใช่ยึดเป็นผลลัพธ์ตายตัวครับ"
    ).strip()


def _detect_years(text: str) -> list[int]:
    years: list[int] = []
    for raw in YEAR_RE.findall(text):
        year = int(raw)
        # Convert CE (20xx) to Thai Buddhist Era; BE years (25xx) are kept as-is
        if 2000 <= year <= 2099:
            year += 543
        if 2500 <= year <= 2699 and year not in years:
            years.append(year)
    for raw in SHORT_YEAR_RE.findall(text):
        short_year = int(raw)
        year = 2500 + short_year
        if 2500 <= year <= 2699 and year not in years:
            years.append(year)
    return years


def _normalize_crop_text(text: str) -> str:
    t = text.lower()
    replacements = {
        "ข้าวโพ้ด": "ข้าวโพด",
        "ข้าวโพดเลี้ยงสัตว์": "ข้าวโพด",
        "โพ้ด": "โพด",
    }
    for wrong, right in replacements.items():
        t = t.replace(wrong, right)
    return t


def _is_historical_price_question(text: str) -> bool:
    t = text.lower()
    has_price = any(term in t for term in ["ราคา", "ตลาด", "ย้อนหลัง", "เฉลี่ย"])
    has_year = bool(_detect_years(t)) or any(term in t for term in ["ล่าสุด", "ปีไหน", "ปีอะไร"])
    has_yearly_compare = bool(_detect_years(t)) and any(term in t for term in ["เทียบ", "เปรียบเทียบ", "ตาราง", "ต่างกัน", "ขึ้น", "ลง"])
    if has_yearly_compare and not any(term in t for term in ["ปลูก", "ดูแล", "โรค", "น้ำ", "ปุ๋ย", "ดิน"]):
        return True
    if has_price and "ย้อนหลัง" in t:
        return True
    return has_price and has_year


def _historical_price_answer(query: str, crops: list[str]) -> str | None:
    if not _is_historical_price_question(query):
        return None

    prices = _load_historical_prices()
    selected_crops = [crop for crop in crops if crop in prices]
    if not selected_crops:
        return None

    rows: list[tuple[str, int, float | None]] = []
    years = _detect_years(query)
    latest_requested = not years
    if latest_requested:
        for crop in selected_crops:
            latest_year = max(prices[crop])
            rows.append((crop, latest_year, prices[crop].get(latest_year)))
    else:
        for crop in selected_crops:
            for year in years:
                rows.append((crop, year, prices[crop].get(year)))

    found_rows = [row for row in rows if row[2] is not None]
    if not found_rows:
        available = sorted(prices[selected_crops[0]])
        return (
            "**สรุป**\n"
            f"- ยังไม่พบราคาย้อนหลังของ{selected_crops[0]}ในปีที่ถามจากไฟล์ข้อมูลครับ\n\n"
            "**ข้อมูลที่มี**\n"
            f"- ปีที่มีในไฟล์: **{available[0]}-{available[-1]}** ครับ\n\n"
            "**คำแนะนำ**\n"
            "- ลองถามปีที่อยู่ในช่วงข้อมูลนี้ หรือระบุพืชให้ชัดขึ้นครับ"
        )

    if len(found_rows) == 1:
        crop, year, price = found_rows[0]
        crop_label = _HISTORICAL_PRICE_LABELS.get(crop, crop)
        available = sorted(prices[crop])
        latest_note = (
            f"- ผู้ใช้ไม่ได้ระบุปี จึงดึงปีล่าสุดที่มีของพืชนี้คือ **{year}** จากช่วงข้อมูล **{available[0]}-{available[-1]}** ครับ\n"
            if latest_requested
            else f"- ช่วงข้อมูลที่มีของพืชนี้ในไฟล์คือ **{available[0]}-{available[-1]}** ครับ\n"
        )
        return (
            "**สรุป**\n"
            f"- ราคาเฉลี่ยย้อนหลังของ **{crop_label}** ปี **{year}** คือ **{_format_price_value(price or 0)}** ตามไฟล์ข้อมูลครับ\n\n"
            "**ข้อมูลที่ใช้**\n"
            f"- แหล่งข้อมูลในระบบ: `prices_yearly_avg_all_crops.csv`\n"
            f"{latest_note}"
            "- เป็นค่าเฉลี่ยรายปีจากข้อมูลที่เตรียมไว้ ไม่ใช่ราคาซื้อขายหน้าสวนวันนี้ครับ\n\n"
            "**ข้อควรระวัง**\n"
            "- หน่วยราคาให้ยึดตามชุดข้อมูลดิบของพืชนั้น และควรเทียบกับพื้นที่/คุณภาพผลผลิตจริงก่อนตัดสินใจครับ"
        )

    table_lines = [
        "| พืช | ปี | ราคาเฉลี่ยย้อนหลัง |",
        "|---|---:|---:|",
    ]
    for crop, year, price in found_rows:
        crop_label = _HISTORICAL_PRICE_LABELS.get(crop, crop)
        table_lines.append(f"| {crop_label} | {year} | {_format_price_value(price or 0)} |")

    summary = ""
    data_ranges = []
    for crop in selected_crops:
        available = sorted(prices[crop])
        crop_label = _HISTORICAL_PRICE_LABELS.get(crop, crop)
        data_ranges.append(f"{crop_label}: {available[0]}-{available[-1]}")
    if len(selected_crops) == 1 and len(found_rows) >= 2:
        first_crop, first_year, first_price = found_rows[0]
        last_crop, last_year, last_price = found_rows[-1]
        if first_crop == last_crop and first_price is not None and last_price is not None:
            diff = last_price - first_price
            direction = "เพิ่มขึ้น" if diff > 0 else "ลดลง" if diff < 0 else "ทรงตัว"
            summary = (
                f"- จากปี **{first_year}** ถึง **{last_year}** ราคา{direction} "
                f"ประมาณ **{_format_price_value(abs(diff))}** ครับ\n"
            )
    elif latest_requested:
        summary = "- ผู้ใช้ไม่ได้ระบุปี จึงดึง **ปีล่าสุดที่มีในไฟล์ของแต่ละพืช** มาให้ครับ\n"

    return (
        "**สรุป**\n"
        f"{summary or '- พบข้อมูลราคาย้อนหลังตามปีที่ถามจากไฟล์ข้อมูลครับ\n'}\n"
        "**ตารางราคา**\n"
        + "\n".join(table_lines)
        + "\n\n**ข้อมูลที่ใช้**\n"
        + f"- ช่วงปีในไฟล์: **{'; '.join(data_ranges)}** ครับ\n"
        + "- แหล่งข้อมูลในระบบ: `prices_yearly_avg_all_crops.csv` ครับ"
        + "\n\n**ข้อควรระวัง**\n"
        "- ตัวเลขนี้เป็นค่าเฉลี่ยรายปีในไฟล์ ไม่ใช่ราคาปัจจุบันหน้าสวนครับ"
    )


def _latest_historical_price_row(crop: str | None) -> tuple[str, int, float, int, int] | None:
    if not crop:
        return None
    prices = _load_historical_prices()
    if crop not in prices or not prices[crop]:
        return None
    available = sorted(prices[crop])
    latest_year = available[-1]
    crop_label = _HISTORICAL_PRICE_LABELS.get(crop, crop)
    return crop_label, latest_year, prices[crop][latest_year], available[0], available[-1]


def _parse_thai_money(raw: str, unit: str | None = None) -> float:
    value = float(raw.replace(",", ""))
    multipliers = {
        "หมื่น": 10_000,
        "แสน": 100_000,
        "ล้าน": 1_000_000,
    }
    return value * multipliers.get(unit or "", 1)


def _financial_missing_answer(query: str, crop: str | None, history: list[dict] | None) -> str:
    area = detect_area_rai(query, history)  # pass history so area from prior turns is not lost
    crop_text = crop or "พืชชนิดนี้"
    area_line = f"- พื้นที่ที่พบในคำถาม/บทสนทนา: **{_format_money(area)} ไร่**\n" if area else ""
    latest_price = _latest_historical_price_row(crop)
    historical_note = ""
    if latest_price and any(term in query for term in ["ราคา", "ราคาขาย", "รายได้", "ขาย"]):
        crop_label, year, price, first_year, last_year = latest_price
        historical_note = (
            "\n**ราคาอ้างอิงย้อนหลังล่าสุด**\n"
            f"- จากไฟล์ `prices_yearly_avg_all_crops.csv` พบราคาเฉลี่ยย้อนหลังของ **{crop_label}** "
            f"ปี **{year}** คือ **{_format_price_value(price)}** ครับ\n"
            f"- ผู้ใช้ไม่ได้ให้ราคาปัจจุบัน จึงใช้ข้อมูลย้อนหลังล่าสุดที่มีในช่วง **{first_year}-{last_year}** "
            "เป็นตัวอ้างอิงเท่านั้น ไม่ใช่ราคาตลาดวันนี้ครับ\n"
        )
    return (
        "**สรุป**\n"
        f"- ยังไม่พบตัวเลขราคา ผลผลิต หรือต้นทุนของ{crop_text}ที่ชัดพอสำหรับคำนวณครับ\n"
        f"{area_line}"
        f"{historical_note}"
        "\n**ต้องใช้ข้อมูลเพิ่ม**\n"
        "- ถ้าถามรายได้: ขอ **ผลผลิตต่อไร่** และ **ราคาขายต่อหน่วย** ครับ\n"
        "- ถ้าถามต้นทุน: ขอ **ต้นทุนต่อไร่** หรือรายการค่าใช้จ่ายหลัก เช่น พันธุ์ ปุ๋ย แรงงาน ครับ\n"
        "\n**ตัวอย่างสูตร**\n"
        "- รายได้รวม = ผลผลิตต่อไร่ × ราคาขายต่อหน่วย × จำนวนไร่ครับ\n"
        "- ต้นทุนรวม = ต้นทุนต่อไร่ × จำนวนไร่ครับ"
    )


def _detect_labeled_amount(pattern: re.Pattern[str], text: str) -> float | None:
    match = pattern.search(text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _compare_financial_missing_answer(crops: list[str]) -> str:
    crop_a = crops[0] if len(crops) >= 1 else "พืชที่ 1"
    crop_b = crops[1] if len(crops) >= 2 else "พืชที่ 2"
    return (
        "**สรุป**\n"
        "- ยังไม่ควรสรุปว่าพืชไหนต้นทุนต่ำกว่าหรือคุ้มกว่า ถ้ายังไม่มีตัวเลขชุดเดียวกันครับ\n\n"
        "| รายการที่ต้องเทียบ | "
        f"{crop_a} | {crop_b} |\n"
        "|---|---|---|\n"
        "| ต้นทุนต่อไร่ | ต้องมีข้อมูล | ต้องมีข้อมูล |\n"
        "| ผลผลิตต่อไร่ | ต้องมีข้อมูล | ต้องมีข้อมูล |\n"
        "| ราคาขายต่อหน่วย | ต้องมีข้อมูล | ต้องมีข้อมูล |\n"
        "| ความเสี่ยงหลัก | โรค น้ำ แรงงาน ตลาด | โรค น้ำ แรงงาน ตลาด |\n\n"
        "**เลือกแบบไหนดี**\n"
        "- ถ้ามีตัวเลขทั้งสองพืชในปีและพื้นที่เดียวกัน ผมจะช่วยคำนวณเทียบให้เป็นตารางได้ครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- อย่าใช้ราคาคนละปีหรือคนละจังหวัดมาเทียบตรง ๆ เพราะอาจทำให้ตัดสินใจผิดครับ"
    )


# ---------------------------------------------------------------------------
# Compare knowledge data — module-level to avoid rebuilding on every call
# ---------------------------------------------------------------------------

CROP_COMPARE_DATA: dict[tuple[str, str], dict[str, tuple]] = {
    ("ข้าว", "ข้าวโพด"): {
        "water": (
            ("คุมระดับน้ำในนา ต้องมีน้ำขังช่วงแตกกอ", "ทนแล้งได้บ้าง แต่ช่วงออกฝักต้องการน้ำสม่ำเสมอ"),
            ("น้ำน้อยหรือน้ำขังนานทำให้รากเน่า", "น้ำขังทำให้รากเน่าและฝักลีบ"),
            ("เหมาะพื้นที่ลุ่ม มีแหล่งน้ำชลประทาน", "เหมาะพื้นที่ดอน ระบายน้ำดี"),
        ),
        "default": (
            ("90–120 วัน ขึ้นกับพันธุ์", "70–75 วัน เก็บได้เร็วกว่า"),
            ("ต้องการน้ำมาก ดูแลวัชพืช ปุ๋ย และโรค", "ดูแลหนอนกระทู้ วัชพืชช่วงต้น และน้ำช่วงออกฝัก"),
            ("น้ำ โรคไหม้ เพลี้ยกระโดด", "หนอนกระทู้ข้าวโพด ราน้ำค้าง"),
        ),
    },
    ("ข้าว", "มันสำปะหลัง"): {
        "default": (
            ("90–120 วัน", "8–12 เดือน รายได้ช้ากว่า"),
            ("ต้องการน้ำมาก เหมาะพื้นที่ลุ่ม", "ทนแล้งดี เหมาะดินร่วนปนทราย"),
            ("น้ำ โรคไหม้ เพลี้ยกระโดด", "เพลี้ยแป้ง ไรแดง หัวเน่าจากน้ำขัง"),
        ),
    },
    ("ข้าว", "อ้อย"): {
        "default": (
            ("90–120 วัน หมุนรอบปลูกได้เร็ว", "10–12 เดือน แต่ตอแตกได้หลายปี"),
            ("ต้องการน้ำมาก ใช้แรงงานช่วงเก็บ", "ต้องการน้ำช่วงตั้งตัว ใช้เครื่องจักรเก็บได้"),
            ("น้ำ โรคไหม้ ราคาผันผวน", "ราคาผูกกับโรงงาน โรคใบไหม้ หนอนกอ"),
        ),
    },
    ("ข้าวโพด", "มันสำปะหลัง"): {
        "default": (
            ("70–75 วัน", "8–12 เดือน"),
            ("ต้องดูหนอน วัชพืช และน้ำช่วงออกฝัก", "ทนแล้ง ดูแลน้อยกว่า แต่รอนาน"),
            ("หนอนกระทู้ ราน้ำค้าง ราคาผันผวน", "เพลี้ยแป้ง ไรแดง หัวเน่าถ้าน้ำขัง"),
        ),
    },
    ("ข้าวโพด", "อ้อย"): {
        "default": (
            ("70–75 วัน หมุนรอบเร็ว", "10–12 เดือน ตอแตกหลายปี"),
            ("ใช้ต้นทุนปานกลาง ราคาขึ้นลงตามตลาด", "ต้นทุนสูงรอบแรก แต่ตอลดต้นทุนปีถัดไป"),
            ("หนอนกระทู้ ราน้ำค้าง", "หนอนกอ โรคใบไหม้ ราคาผูกโรงงาน"),
        ),
    },
    ("มันสำปะหลัง", "อ้อย"): {
        "default": (
            ("8–12 เดือน ทนแล้งดี", "10–12 เดือน ตอแตกได้หลายรอบ"),
            ("ต้นทุนต่ำ ดูแลง่าย แต่ราคาผันผวน", "ต้นทุนสูงรอบแรก ราคาค่อนข้างแน่นอนกว่า"),
            ("เพลี้ยแป้ง ไรแดง หัวเน่า", "หนอนกอ โรคใบไหม้ ต้องการน้ำมากกว่า"),
        ),
    },
    ("ยางพารา", "ปาล์มน้ำมัน"): {
        "default": (
            ("เริ่มกรีดได้ที่ 6–7 ปี รายได้ระยะยาว", "ให้ผลผลิตที่ 3–4 ปี เร็วกว่า"),
            ("ต้องการแรงงานกรีดทุกวัน บริหารจัดการสูง", "เก็บทะลายทุก 10–15 วัน ใช้เครื่องจักรช่วยได้"),
            ("ราคายางผันผวนมาก โรคราใบยาง", "ราคาปาล์มผูกน้ำมัน โรครากเน่า"),
        ),
    },
}


def _compare_knowledge_answer(crops: list[str], topic: str | None) -> str:
    crop_a = crops[0] if len(crops) >= 1 else "พืชที่ 1"
    crop_b = crops[1] if len(crops) >= 2 else "พืชที่ 2"

    # หาข้อมูลจาก lookup ทั้งสองทิศทาง
    key = (crop_a, crop_b)
    key_rev = (crop_b, crop_a)
    compare_entry = CROP_COMPARE_DATA.get(key) or CROP_COMPARE_DATA.get(key_rev)
    reversed_order = key not in CROP_COMPARE_DATA and key_rev in CROP_COMPARE_DATA

    if compare_entry:
        data = compare_entry.get("water" if topic == "water" else "default",
                                 compare_entry.get("default"))
        if data:
            row_a, row_b, row_c = data
            left_a, right_a = (row_a[1], row_a[0]) if reversed_order else (row_a[0], row_a[1])
            left_b, right_b = (row_b[1], row_b[0]) if reversed_order else (row_b[0], row_b[1])
            left_c, right_c = (row_c[1], row_c[0]) if reversed_order else (row_c[0], row_c[1])
            if topic == "water":
                row_names = ["การให้น้ำ", "จุดเสี่ยงน้ำ", "เหมาะพื้นที่"]
            else:
                row_names = ["อายุเก็บเกี่ยว", "การดูแลหลัก", "จุดเสี่ยง"]
            rows = [
                (row_names[0], left_a, right_a),
                (row_names[1], left_b, right_b),
                (row_names[2], left_c, right_c),
            ]
        else:
            rows = _generic_compare_rows(crop_a, crop_b, topic)
    else:
        rows = _generic_compare_rows(crop_a, crop_b, topic)

    table = [
        f"| รายการ | {crop_a} | {crop_b} |",
        "|---|---|---|",
    ]
    table.extend(f"| {name} | {left} | {right} |" for name, left, right in rows)
    return (
        "**สรุป**\n"
        f"- เทียบ {crop_a} กับ {crop_b} ควรดูเงื่อนไขแปลงจริงก่อนตัดสินใจครับ\n\n"
        "**ตารางเปรียบเทียบ**\n"
        + "\n".join(table)
        + "\n\n**คำแนะนำ**\n"
        "- ถ้าบอกจังหวัด ดิน แหล่งน้ำ และช่วงปลูก ผมจะช่วยสรุปให้เหมาะกับแปลงมากขึ้นครับ"
    )


def _extract_first_metric(text: str, metric: str) -> float | None:
    pattern = METRIC_PATTERNS.get(metric)
    if not pattern:
        return None
    match = pattern.search(text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_metric_with_hints(text: str, metric: str) -> float | None:
    cleaned = text.replace(",", "")
    for hint in METRIC_HINTS.get(metric, []):
        hint_pattern = re.compile(rf"{re.escape(hint)}[^0-9-]{{0,30}}(-?{NUMBER_RE})", re.IGNORECASE)
        match = hint_pattern.search(cleaned)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return _extract_first_metric(cleaned, metric)


def _metric_matches_source(metric: str, source_type: str) -> bool:
    source_type = source_type.lower()
    if metric in {"cost_per_rai", "profit_per_rai", "revenue_per_rai"}:
        return any(term in source_type for term in ["cost", "profit", "economic", "socio", "financial", "profitability"])
    if metric == "price":
        return "price" in source_type
    return True


def _collect_crop_metrics(crop: str, docs: list[dict]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for doc in docs:
        if not _doc_mentions_crop(doc, crop):
            continue
        content = doc.get("content", "")
        source_type = str(doc.get("metadata", {}).get("source_type", ""))
        for metric in ["cost_per_rai", "profit_per_rai", "revenue_per_rai", "yield_per_rai", "price"]:
            if metric in metrics:
                continue
            if source_type and not _metric_matches_source(metric, source_type):
                continue
            value = _extract_metric_with_hints(content, metric)
            if value is not None:
                metrics[metric] = value
    return metrics


def _compare_query_context_lines(query: str) -> list[str]:
    lines: list[str] = []
    q = query.lower()
    if "ดินทราย" in q:
        lines.append("- ผู้ใช้ระบุว่าดินค่อนข้างเป็นดินทรายครับ")
    if any(term in q for term in ["ฝนไม่ค่อยตก", "ฝนน้อย", "ฝนทิ้งช่วง", "แล้ง", "2-3 ปี"]):
        lines.append("- ผู้ใช้ระบุว่าฝนน้อยหรือมีความเสี่ยงแล้งครับ")
    area = detect_area_rai(query)
    if area:
        lines.append(f"- พื้นที่ที่ถามประมาณ **{_format_money(area)} ไร่** ครับ")
    return lines


def _compare_structured_financial_answer(query: str, crops: list[str], docs: list[dict]) -> str | None:
    if len(crops) < 2:
        return None
    left, right = crops[0], crops[1]
    left_metrics = _collect_crop_metrics(left, docs)
    right_metrics = _collect_crop_metrics(right, docs)
    context_lines = _compare_query_context_lines(query)
    left_row = _latest_cost_price_row(left)
    right_row = _latest_cost_price_row(right)

    # For compare queries with structured economic data available, prefer filling from
    # structured rows first so both crops are represented symmetrically.
    if left_row:
        left_metrics.setdefault("cost_per_rai", float(left_row["cost_per_rai"]))
        left_metrics.setdefault("profit_per_rai", float(left_row["gross_profit"]))
        left_metrics.setdefault("revenue_per_rai", float(left_row["revenue"]))
        left_metrics.setdefault("yield_per_rai", float(left_row["yield_per_rai"]))
        left_metrics.setdefault("price", float(left_row["price_per_kg"]))
    if right_row:
        right_metrics.setdefault("cost_per_rai", float(right_row["cost_per_rai"]))
        right_metrics.setdefault("profit_per_rai", float(right_row["gross_profit"]))
        right_metrics.setdefault("revenue_per_rai", float(right_row["revenue"]))
        right_metrics.setdefault("yield_per_rai", float(right_row["yield_per_rai"]))
        right_metrics.setdefault("price", float(right_row["price_per_kg"]))

    if not left_metrics and not right_metrics:
        return None

    rows: list[tuple[str, str, str]] = []
    metric_labels = [
        ("ต้นทุนต่อไร่", "cost_per_rai", "บาท"),
        ("ประมาณกำไร", "profit_per_rai", "บาท"),
        ("รายได้ต่อไร่", "revenue_per_rai", "บาท"),
        ("ผลผลิตต่อไร่", "yield_per_rai", "หน่วย"),
        ("ราคา", "price", "บาท"),
    ]
    for label, key, unit in metric_labels:
        lval = left_metrics.get(key)
        rval = right_metrics.get(key)
        if lval is None and rval is None:
            continue
        left_text = f"{_format_money(lval)} {unit}" if lval is not None else "-"
        right_text = f"{_format_money(rval)} {unit}" if rval is not None else "-"
        rows.append((label, left_text, right_text))

    if not rows:
        return None

    recommendation = None
    caution = "- ตัวเลขที่พบอาจมาจากคนละเอกสารหรือคนละเงื่อนไขแปลง ควรใช้เทียบแบบคร่าว ๆ ก่อนครับ"
    if "profit_per_rai" in left_metrics and "profit_per_rai" in right_metrics:
        recommendation = left if left_metrics["profit_per_rai"] >= right_metrics["profit_per_rai"] else right
    elif "cost_per_rai" in left_metrics and "cost_per_rai" in right_metrics:
        recommendation = left if left_metrics["cost_per_rai"] <= right_metrics["cost_per_rai"] else right

    table = [
        f"| รายการ | {left} | {right} |",
        "|---|---:|---:|",
    ]
    table.extend(f"| {label} | {ltext} | {rtext} |" for label, ltext, rtext in rows)

    summary_line = (
        f"- ถ้าดูจากตัวเลขที่ดึงได้ในระบบ ตอนนี้ **{recommendation}** ดูได้เปรียบกว่าแบบคร่าว ๆ ครับ"
        if recommendation
        else "- พบตัวเลขบางส่วนสำหรับเทียบคร่าว ๆ แต่ยังไม่พอจะฟันธงว่าพืชไหนดีกว่ากันครับ"
    )
    if _has_price_guarantee_request(query):
        caution = "- ผมไม่สามารถฟันธงราคาหรือผลตอบแทนในอนาคตได้ ควรใช้เป็นข้อมูลประกอบการตัดสินใจเท่านั้นครับ"

    heading = f"**เปรียบเทียบ{left} vs {right}**" if {left, right} == {"มันสำปะหลัง", "ข้าวโพด"} else "**เปรียบเทียบ**"
    field_analysis = []
    if "ดินทราย" in query:
        field_analysis.append("- วิเคราะห์ดินทราย: ดินทรายอุ้มน้ำน้อย จึงเหมาะกับพืชที่ทนแล้งและตั้งตัวในดินโปร่งได้ดีกว่าครับ")
    if any(term in query for term in ["ฝนน้อย", "แล้ง", "ฝนทิ้งช่วง", "ฝนไม่ค่อยตก", "2-3 ปี"]):
        field_analysis.append("- วิเคราะห์สภาพฝนน้อย: ถ้าฝนน้อยต่อเนื่อง 2-3 ปี พืชที่ทนแล้งได้ดีกว่าจะเสี่ยงน้อยกว่าครับ")
    recommendation_line = (
        f"- สรุปพืชที่เหมาะกว่า: ถ้ามองทั้งดินทราย ฝนน้อย ต้นทุนต่อไร่ และกำไรคร่าว ๆ ตอนนี้เอนเอียงไปทาง **{recommendation}** ครับ"
        if recommendation
        else "- สรุปพืชที่เหมาะกว่า: ตอนนี้ข้อมูลยังไม่พอจะฟันธงครับ"
    )
    return (
        "**สรุป**\n"
        f"{summary_line}\n\n"
        + ("**วิเคราะห์เงื่อนไขแปลง**\n" + "\n".join(field_analysis or context_lines) + "\n\n" if (field_analysis or context_lines) else "")
        + heading
        + "\n"
        + "\n".join(table)
        + "\n\n**สรุปพืชที่เหมาะกว่า**\n"
        + recommendation_line
        + "\n\n**ข้อควรระวัง**\n"
        + caution
        + "\n- ตัวเลขนี้คำนวณจากชุดข้อมูลที่มีในระบบ ไม่ใช่การรับประกันผลจริง"
    )


def _generic_compare_rows(crop_a: str, crop_b: str, topic: str | None) -> list[tuple[str, str, str]]:
    """Fallback rows when no specific data is available for the crop pair."""
    if topic == "water":
        return [
            ("การให้น้ำ", f"ต้องดูความชื้นและน้ำตามระยะปลูก{crop_a}", f"ต้องดูความชื้นและน้ำตามระยะปลูก{crop_b}"),
            ("จุดเสี่ยงน้ำ", f"น้ำขังหรือแล้งจัดทำให้{crop_a}เสียหาย", f"น้ำขังหรือแล้งจัดทำให้{crop_b}เสียหาย"),
            ("เหมาะพื้นที่", "ต้องเช็กแหล่งน้ำก่อนปลูก", "ต้องเช็กแหล่งน้ำก่อนปลูก"),
        ]
    return [
        ("การดูแล", f"ดูน้ำ ปุ๋ย วัชพืช โรค ตามระยะ{crop_a}", f"ดูน้ำ ปุ๋ย วัชพืช โรค ตามระยะ{crop_b}"),
        ("แรงงาน", "ขึ้นกับขนาดแปลงและช่วงเก็บเกี่ยว", "ขึ้นกับขนาดแปลงและช่วงเก็บเกี่ยว"),
        ("จุดเสี่ยง", f"โรค แมลง น้ำ สภาพอากาศ ราคา{crop_a}", f"โรค แมลง น้ำ สภาพอากาศ ราคา{crop_b}"),
    ]


KNOWLEDGE_FOCUS_TERMS = [
    "ฝน", "น้ำ", "ปลูก", "ใบ", "ปุ๋ย", "โรค", "ระบาย", "ความชื้น",
    "ฝัก", "แมลง", "วัชพืช", "แปลง", "ช่วงต้น", "ท่อนพันธุ์", "ดิน",
    "ตอ", "หน่อ", "หนอน", "เพลี้ย", "ศัตรูพืช", "ดินทราย", "ใบเหลือง", "ร่องน้ำ", "น้ำขัง",
    "กรีด", "เปลือก", "หยุด", "ใบร่วง", "แล้ง", "ทะลาย", "รากเน่า",
    "ใบอ่อน", "ดอก", "ผลอ่อน", "อาหาร", "หลังเก็บเกี่ยว", "ผล",
    "ราก", "โคน", "หลังนา", "ระยะ", "แถว", "หลุม",
]


def _focus_terms_from_query(query: str) -> list[str]:
    terms = [term for term in KNOWLEDGE_FOCUS_TERMS if term in query]
    # Compound symptom terms that map to base focus terms
    if "ใบซีด" in query and "ใบ" not in terms:
        terms.append("ใบ")
    if "ใบด่าง" in query:
        if "ใบ" not in terms:
            terms.append("ใบ")
        if "โรค" not in terms:
            terms.append("โรค")
    if "ใบไหม้" in query:
        if "ใบ" not in terms:
            terms.append("ใบ")
        if "โรค" not in terms:
            terms.append("โรค")
    if "โคนเน่า" in query or "รากเน่า" in query:
        if "โรค" not in terms:
            terms.append("โรค")
        if "ราก" not in terms:
            terms.append("ราก")
    if "ต้นแคระ" in query and "โรค" not in terms:
        terms.append("โรค")
    if "ออกดอก" in query and "ดอก" not in terms:
        terms.append("ดอก")
    if "ติดผล" in query and "ผล" not in terms:
        terms.append("ผล")
    if "แตกยอด" in query or "ยอดไหม้" in query:
        if "ใบ" not in terms:
            terms.append("ใบ")
    return terms[:5]


def _generic_crop_knowledge_answer(query: str, crop: str, topic: str | None) -> str:
    terms = _focus_terms_from_query(query)
    focus_text = " ".join(terms) if terms else "ดิน น้ำ ปุ๋ย โรค และสภาพแปลง"
    action_lines: list[str] = []

    if any(term in terms for term in ["น้ำ", "ฝน", "ความชื้น", "ระบาย", "ร่องน้ำ", "น้ำขัง", "แล้ง"]):
        action_lines.append(f"ตรวจน้ำ ความชื้น และทางระบายน้ำของแปลง{crop}ก่อนครับ")
    if any(term in terms for term in ["ใบ", "ใบเหลือง", "ใบอ่อน", "ใบร่วง"]):
        action_lines.append(f"ดูอาการใบของ{crop} เช่น สีใบ ใบซีด ใบร่วง หรือใบอ่อนผิดปกติครับ")
    if any(term in terms for term in ["ปุ๋ย", "ดิน", "ดินทราย", "อาหาร"]):
        action_lines.append(f"เช็กดินและปุ๋ยของ{crop} ว่าดินแน่น แห้ง หรือธาตุอาหารไม่พอหรือไม่ครับ")
    if any(term in terms for term in ["โรค", "แมลง", "หนอน", "เพลี้ย", "ศัตรูพืช", "รากเน่า"]):
        action_lines.append(f"สำรวจโรคและแมลงของ{crop} โดยดูใบ โคนต้น ราก และรอยทำลายในแปลงครับ")
    if any(term in terms for term in ["วัชพืช", "ช่วงต้น"]):
        action_lines.append(f"จัดการวัชพืชในแปลง{crop}ตั้งแต่ช่วงต้น อย่าให้แย่งน้ำและปุ๋ยครับ")
    if any(term in terms for term in ["ระยะ", "แถว", "หลุม"]):
        action_lines.append(f"กำหนดระยะปลูก ระยะแถว และระยะหลุมของ{crop}ให้เหมาะกับพันธุ์และเครื่องมือในแปลงครับ")
    if any(term in terms for term in ["ท่อนพันธุ์", "ตอ", "หน่อ"]):
        action_lines.append(f"ดูท่อนพันธุ์ ตอ และหน่อของ{crop} ว่ายังสด แข็งแรง และแตกหน่อสม่ำเสมอหรือไม่ครับ")
    if any(term in terms for term in ["ฝัก", "ดอก", "ผล", "ผลอ่อน", "ทะลาย"]):
        action_lines.append(f"ช่วงสร้างฝัก ดอก ผล หรือทะลายของ{crop} ต้องคุมทั้งน้ำ ปุ๋ย และแมลงให้สม่ำเสมอครับ")
    if any(term in terms for term in ["กรีด", "เปลือก", "หยุด"]):
        action_lines.append(f"ถ้าเกี่ยวกับการกรีด ให้ดูเปลือก ลำต้น และหยุดกรีดต้นที่ผิดปกติก่อนครับ")
    if not action_lines:
        action_lines.append(f"เริ่มจากดูสภาพแปลง{crop}จริง ทั้งดิน น้ำ ปุ๋ย โรค และอายุพืชครับ")

    action_lines = action_lines[:3]
    bullets = "\n".join(f"- {line}" for line in action_lines)
    # Choose a context-appropriate caution line
    if topic in ("disease", "water", "fertilizer"):
        caution = f"อย่ารีบใช้สารโดยไม่ดูอาการจริงในแปลง{crop} และปรึกษาเจ้าหน้าที่เกษตรถ้าอาการรุนแรงครับ"
    elif topic == "planting_method":
        caution = f"ระยะปลูกและวิธีเตรียมดินควรปรับตามพันธุ์และสภาพดินจริงในแปลง{crop}ครับ"
    else:
        caution = f"อย่ารีบสรุปจากอาการเดียวของ{crop} ให้ดูดิน น้ำ โรค และสภาพอากาศร่วมกันครับ"
    return (
        "**สรุป**\n"
        f"- สำหรับ{crop} คำถามนี้ควรไล่ดูเรื่อง **{focus_text}** เป็นหลักครับ\n\n"
        "**วิธีทำ**\n"
        f"{bullets}\n\n"
        "**ข้อควรระวัง**\n"
        f"- {caution}"
    )


def _broad_crop_planning_answer() -> str:
    return (
        "**สรุป**\n"
        "- ถ้ายังไม่เลือกพืชเศรษฐกิจ ควรถามต่อโดยบอกข้อมูลแปลงก่อนครับ\n\n"
        "**ข้อมูลที่ควรบอก**\n"
        "- พื้นที่ปลูกกี่ไร่ จังหวัดหรือภาค ดินเป็นแบบไหน และมีน้ำพอไหมครับ\n"
        "- อยากเน้นขายเร็ว ลดต้นทุน หรือดูแลง่ายครับ\n\n"
        "**คำแนะนำ**\n"
        "- เมื่อมีข้อมูลพื้นที่และน้ำ ผมจะช่วยคัดพืชในขอบเขตของ DrKaset ให้เหมาะขึ้นครับ"
    )


def _detect_location_text(query: str, history: list[dict] | None = None) -> str | None:
    haystack = query
    if history:
        history_text = " ".join(
            str(message.get("content", ""))
            for message in history[-6:]
            if message.get("role") == "user"
        )
        haystack = f"{query} {history_text}"
    known_locations = [
        "กรุงเทพ", "กรุงเทพฯ", "ปทุมธานี", "นนทบุรี", "อยุธยา", "นครปฐม",
        "เชียงใหม่", "เชียงราย", "ขอนแก่น", "นครราชสีมา", "โคราช",
        "อุบล", "สุราษฎร์", "นครศรีธรรมราช", "จันทบุรี", "ระยอง",
    ]
    for location in known_locations:
        if location in haystack:
            return location
    region = detect_region_from_text(haystack)
    return f"ภาค{region}" if region else None


def _is_crop_planning_question(query: str) -> bool:
    planning_terms = [
        "อยากลองปลูก", "อยากปลูก", "วางแผน", "เตรียมอะไร", "ต้องเตรียม",
        "เริ่มปลูก", "จะปลูก", "ปลูกในจังหวัด", "แหล่งน้ำ",
        "จะเริ่มปลูก", "สนใจปลูก", "ปลูกครั้งแรก", "ปลูกใหม่",
    ]
    return any(term in query for term in planning_terms)


def _crop_planting_plan_answer(query: str, crop: str, history: list[dict] | None = None) -> str:
    area = detect_area_rai(query, history)
    location = _detect_location_text(query, history)
    area_text = f" พื้นที่ประมาณ **{_format_money(area)} ไร่**" if area else ""
    location_text = f" ใน **{location}**" if location else ""

    if crop == "ข้าว":
        local_note = ""
        if location and "กรุงเทพ" in location:
            local_note = (
                "- กรุงเทพเป็นพื้นที่เมืองและที่ลุ่ม ต้องเช็กแหล่งน้ำ การระบายน้ำ "
                "ข้อจำกัดพื้นที่ และความเสี่ยงน้ำท่วม/น้ำเสียก่อนลงมือครับ\n"
            )
        return (
            "**สรุป**\n"
            f"- ถ้าจะปลูก **ข้าว**{area_text}{location_text} ควรเริ่มจากเช็กแปลง น้ำ ดิน พันธุ์ และแรงงานครับ\n\n"
            "**ต้องเตรียม**\n"
            "- แปลงนา: ปรับพื้นที่ให้เรียบ ทำคันนา และทำทางระบายน้ำเข้าออกได้ครับ\n"
            "- น้ำ: ต้องมีน้ำพอช่วงเตรียมดิน แตกกอ และตั้งท้อง โดยเฉพาะถ้าฝนไม่สม่ำเสมอครับ\n"
            "- ดินและพันธุ์: ตรวจสภาพดิน เลือกพันธุ์ข้าวให้เหมาะกับพื้นที่และฤดูปลูกครับ\n"
            "- แรงงาน/เครื่องมือ: เตรียมรถไถ เมล็ดพันธุ์ ปุ๋ย การจัดการหญ้า และแผนเก็บเกี่ยวครับ\n\n"
            "**คำแนะนำสำหรับพื้นที่**\n"
            f"{local_note or '- ถ้าบอกตำบล/อำเภอและแหล่งน้ำ ผมจะช่วยปรับแผนให้ตรงพื้นที่มากขึ้นครับ'}"
            "\n\n**ข้อควรระวัง**\n"
            "- อย่าเริ่มจากซื้อเมล็ดพันธุ์ก่อนเช็กน้ำและการระบายน้ำ เพราะถ้าน้ำไม่พร้อม ต้นทุนจะบานได้ครับ"
        )

    if crop == "อ้อย":
        return (
            "**สรุป**\n"
            f"- ถ้าจะปลูก **อ้อย**{area_text}{location_text} ให้เริ่มจากเลือกท่อนพันธุ์ให้ดีก่อนเลยครับ\n\n"
            "**การเลือกท่อนพันธุ์**\n"
            "- เลือกท่อนพันธุ์จากต้นอายุ 8–10 เดือน ตาสมบูรณ์ ไม่มีโรค ตัดสดๆ ก่อนปลูกครับ\n"
            "- ท่อนดีควรมี 2–3 ตา ยาวประมาณ 30–40 ซม. ครับ\n"
            "- หลีกเลี่ยงท่อนจากแปลงที่มีโรคใบขาว หรือหนอนกอระบาดครับ\n\n"
            "**ต้องเตรียมเพิ่ม**\n"
            "- ไถดินลึก 30–40 ซม. ร่องปลูกห่างกัน 1–1.2 เมตรครับ\n"
            "- เช็กน้ำให้มีพอช่วงตั้งตัว 1–2 เดือนแรกครับ\n\n"
            "**ข้อควรระวัง**\n"
            "- อย่าใช้ท่อนพันธุ์แก่หรือจากแปลงเป็นโรค เพราะตั้งตัวช้าและแพร่โรคข้ามแปลงได้ครับ"
        )

    if crop == "มันสำปะหลัง":
        return (
            "**สรุป**\n"
            f"- ถ้าจะปลูก **มันสำปะหลัง**{area_text}{location_text} ให้เริ่มจากท่อนพันธุ์และเตรียมดินครับ\n\n"
            "**ต้องเตรียม**\n"
            "- ดิน: ไถลึก 30 ซม. ดินร่วนระบายน้ำดี อย่าปลูกในที่ลุ่มน้ำขังครับ\n"
            "- ท่อนพันธุ์: ใช้ลำต้นอายุ 8–12 เดือน ตัดยาว 20–25 ซม. แข็งแรง ไม่มีแมลงครับ\n"
            "- ฤดูปลูก: ต้นฝน (พ.ค.–มิ.ย.) ดีที่สุด เพราะดินชื้นช่วยตั้งตัวครับ\n\n"
            "**ข้อควรระวัง**\n"
            "- อย่าปลูกท่อนที่มีเพลี้ยแป้งหรือโรคใบด่าง เพราะแพร่เชื้อทั้งแปลงได้ครับ"
        )

    if crop == "ปาล์มน้ำมัน":
        return (
            "**สรุป**\n"
            f"- ถ้าจะปลูก **ปาล์มน้ำมัน**{area_text}{location_text} ต้องเตรียมพื้นที่ระยะยาวครับ\n\n"
            "**ต้องเตรียม**\n"
            "- เลือกพันธุ์ลูกผสม Tenera ที่รับรองแล้ว อย่าซื้อพันธุ์ไม่ได้มาตรฐานครับ\n"
            "- ระยะปลูก 9×9 เมตร หรือ 8×9 เมตร ปลูกเป็นแถวสามเหลี่ยมครับ\n"
            "- ต้องการน้ำสม่ำเสมอโดยเฉพาะ 3 ปีแรก ถ้าแล้งต้องมีระบบน้ำช่วยครับ\n\n"
            "**ข้อควรระวัง**\n"
            "- ปาล์มให้ผลช้า 3–4 ปี ต้องวางแผนเงินทุนหมุนเวียนรองรับด้วยครับ"
        )

    if crop == "ยางพารา":
        return (
            "**สรุป**\n"
            f"- ถ้าจะปลูก **ยางพารา**{area_text}{location_text} ต้องเตรียมใจรอและวางแผนระยะยาวครับ\n\n"
            "**ต้องเตรียม**\n"
            "- เลือกพันธุ์ที่เหมาะพื้นที่ เช่น RRIT 251 หรือ RRIM 600 ครับ\n"
            "- ระยะปลูก 3×7 เมตร หรือ 2.5×8 เมตร วางแถวรับแสงให้ดีครับ\n"
            "- ต้องการฝนกระจายดีตลอดปี ไม่เหมาะพื้นที่แล้งหรือน้ำขังครับ\n\n"
            "**ข้อควรระวัง**\n"
            "- ยางพาราเริ่มกรีดได้เมื่ออายุ 6–7 ปี ต้องมีทุนหมุนเวียนระยะยาวครับ"
        )

    return (
        "**สรุป**\n"
        f"- ถ้าจะปลูก **{crop}**{area_text}{location_text} ให้เริ่มจากตรวจแปลง น้ำ ดิน พันธุ์ และตลาดก่อนครับ\n\n"
        "**ต้องเตรียม**\n"
        "- แปลงและดิน: ดูการระบายน้ำ ความลาดเอียง และความเหมาะสมของดินครับ\n"
        "- น้ำและฤดู: เช็กว่ามีน้ำพอช่วงตั้งตัวและช่วงวิกฤตของพืชหรือไม่ครับ\n"
        "- ต้นทุนและแรงงาน: เตรียมพันธุ์ ปุ๋ย เครื่องมือ แรงงาน และแผนขายครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- ถ้ายังไม่รู้แหล่งน้ำและสภาพดิน อย่าเพิ่งสรุปว่าปลูกแล้วคุ้มครับ"
    )


def _calculation_flow(*steps: str) -> str:
    return " → ".join(f"**{step}**" for step in steps)


def _direct_financial_answer(query: str, crop: str | None, docs: list[dict], history: list[dict] | None) -> str | None:
    if any(term in query for term in ["ไม่รู้", "ไม่มีตัวเลข", "ยังไม่มี", "ไม่มีราคา"]):
        return _financial_missing_answer(query, crop, history)

    area = detect_area_rai(query, history)

    if crop:
        structured_row = _latest_cost_price_row(crop)
        if structured_row is not None:
            if is_price_question(query):
                block = _structured_price_block(query, crop)
                if block:
                    return f"**สรุป**\n- นี่คือราคาอ้างอิงล่าสุดในชุดข้อมูลของ **{crop}** ครับ\n\n{block}"
            if area and any(term in query for term in ["ต้นทุน", "ใช้ทุน", "ลงทุน", "ทุน"]):
                total_cost = float(structured_row["cost_per_rai"]) * area
                return (
                    "**สรุป**\n"
                    f"- ถ้าปลูก **{crop}** บนพื้นที่ **{_format_money(area)} ไร่** และอ้างอิงต้นทุนล่าสุด "
                    f"**{_format_money(float(structured_row['cost_per_rai']))} บาท/ไร่** จะใช้ทุนรวมประมาณ "
                    f"**{_format_money(total_cost)} บาท** ครับ\n\n"
                    "**ข้อมูลต้นทุน**\n"
                    f"- ต้นทุนต่อไร่ล่าสุดในชุดข้อมูลอยู่ที่ประมาณ **{_format_money(float(structured_row['cost_per_rai']))} บาท/ไร่** "
                    f"ในปี **{int(structured_row['year'])}** ครับ\n"
                    f"- คำนวณรวมแบบง่าย: **{_format_money(float(structured_row['cost_per_rai']))} × {_format_money(area)} = {_format_money(total_cost)} บาท**\n"
                    "- ตัวเลขนี้คำนวณจากชุดข้อมูลที่มีในระบบ ไม่ใช่การรับประกันผลจริง"
                )
            if area and any(term in query for term in ["กำไร", "รายได้", "ขายได้", "ขาย"]):
                total_revenue = float(structured_row["revenue"]) * area
                total_profit = float(structured_row["gross_profit"]) * area
                return (
                    "**สรุป**\n"
                    f"- ถ้าอ้างอิงตัวเลขล่าสุดของ **{crop}** บนพื้นที่ **{_format_money(area)} ไร่** "
                    f"จะมีรายรับรวมประมาณ **{_format_money(total_revenue)} บาท** และกำไรขั้นต้นรวมประมาณ "
                    f"**{_format_money(total_profit)} บาท** ครับ\n\n"
                    "**ข้อมูลอ้างอิงต่อไร่**\n"
                    f"- ต้นทุนต่อไร่ประมาณ **{_format_money(float(structured_row['cost_per_rai']))} บาท/ไร่**\n"
                    f"- รายรับต่อไร่ประมาณ **{_format_money(float(structured_row['revenue']))} บาท/ไร่**\n"
                    f"- กำไรขั้นต้นต่อไร่ประมาณ **{_format_money(float(structured_row['gross_profit']))} บาท/ไร่**\n"
                    f"- คิดรวม {_format_money(area)} ไร่ จากชุดข้อมูลปี **{int(structured_row['year'])}**\n"
                    "- ตัวเลขนี้คำนวณจากชุดข้อมูลที่มีในระบบ ไม่ใช่การรับประกันผลจริง"
                )
            if _has_cost_per_kg_request(query):
                cost_per_kg = float(structured_row["cost_per_rai"]) / max(float(structured_row["yield_per_rai"]), 1.0)
                return (
                    "**สรุป**\n"
                    f"- จากชุดข้อมูลที่มีอยู่ ต้นทุนต่อกิโลกรัมของ **{crop}** คำนวณคร่าว ๆ ได้ประมาณ **{_format_price_value(cost_per_kg)} บาท/กก.** ครับ\n\n"
                    "**ข้อมูลอ้างอิง**\n"
                    f"- ต้นทุนต่อไร่ประมาณ **{_format_money(float(structured_row['cost_per_rai']))} บาท/ไร่**\n"
                    f"- ผลผลิตเฉลี่ยประมาณ **{_format_price_value(float(structured_row['yield_per_rai']))} กก./ไร่**\n"
                    "- ตัวเลขนี้คำนวณจากชุดข้อมูลที่มีในระบบ ไม่ใช่การรับประกันผลจริง"
                )
            if any(term in query for term in ["ต้นทุน", "รายได้", "กำไร", "ขาดทุน", "เหลือ"]):
                block = _structured_cost_block(crop)
                if block:
                    return f"**สรุป**\n- นี่คือตัวเลขต้นทุนและผลตอบแทนคร่าว ๆ ของ **{crop}** จากชุดข้อมูลที่มีในระบบครับ\n\n{block}"

    amounts = detect_money_amounts(query)
    labeled_revenue = _detect_labeled_amount(TOTAL_REVENUE_RE, query)
    labeled_cost = _detect_labeled_amount(TOTAL_COST_RE, query)
    if any(term in query for term in ["กำไร", "เหลือ"]) and labeled_revenue is not None and labeled_cost is not None:
        profit = labeled_revenue - labeled_cost
        return (
            "**สรุป**\n"
            f"- รายได้รวม **{_format_money(labeled_revenue)} บาท** หักต้นทุนรวม "
            f"**{_format_money(labeled_cost)} บาท** จะเหลือกำไรประมาณ **{_format_money(profit)} บาท** ครับ\n\n"
            "**วิธีคำนวณ**\n"
            f"- {_format_money(labeled_revenue)} - {_format_money(labeled_cost)} = **{_format_money(profit)} บาท** ครับ\n\n"
            "**แผนภาพคำนวณ**\n"
            f"- {_calculation_flow('รายได้รวม', 'หักต้นทุนรวม', 'กำไรสุทธิ')}\n\n"
            "**ข้อควรระวัง**\n"
            "- ตัวเลขนี้คำนวณจากข้อมูลที่ผู้ใช้ให้ ยังไม่รวมค่าใช้จ่ายอื่นที่อาจมีเพิ่มครับ"
        )

    baht_per_rai_values = detect_baht_per_rai_values(query)
    if "กำไร" in query and area and len(baht_per_rai_values) >= 2:
        revenue_per_rai, cost_per_rai = baht_per_rai_values[0], baht_per_rai_values[1]
        profit = (revenue_per_rai - cost_per_rai) * area
        return (
            "**สรุป**\n"
            f"- รายได้ **{_format_money(revenue_per_rai)} บาท/ไร่** หักต้นทุน "
            f"**{_format_money(cost_per_rai)} บาท/ไร่** บนพื้นที่ **{_format_money(area)} ไร่** "
            f"จะได้กำไรประมาณ **{_format_money(profit)} บาท** ครับ\n\n"
            "**วิธีคำนวณ**\n"
            f"- ({_format_money(revenue_per_rai)} - {_format_money(cost_per_rai)}) × {_format_money(area)} "
            f"= **{_format_money(profit)} บาท** ครับ\n\n"
            "**แผนภาพคำนวณ**\n"
            f"- {_calculation_flow('รายได้/ไร่', 'หักต้นทุน/ไร่', 'คูณจำนวนไร่', 'กำไรรวม')}\n\n"
            "**ข้อควรระวัง**\n"
            "- ตัวเลขนี้เป็นกำไรจากข้อมูลที่ผู้ใช้ให้ ยังไม่รวมค่าใช้จ่ายอื่นที่อาจเกิดเพิ่มครับ"
        )

    total_cost = labeled_cost
    if "กำไร" in query and area and baht_per_rai_values and (amounts or total_cost is not None):
        revenue_per_rai = baht_per_rai_values[0]
        total_revenue = revenue_per_rai * area
        cost = total_cost if total_cost is not None else amounts[-1]
        profit = total_revenue - cost
        return (
            "**สรุป**\n"
            f"- รายได้รวม **{_format_money(total_revenue)} บาท** หักต้นทุนรวม "
            f"**{_format_money(cost)} บาท** จะเหลือกำไรประมาณ **{_format_money(profit)} บาท** ครับ\n\n"
            "**วิธีคำนวณ**\n"
            f"- ({_format_money(revenue_per_rai)} × {_format_money(area)}) - {_format_money(cost)} "
            f"= **{_format_money(profit)} บาท** ครับ\n\n"
            "**แผนภาพคำนวณ**\n"
            f"- {_calculation_flow('รายได้/ไร่', 'คูณจำนวนไร่', 'หักต้นทุนรวม', 'กำไรสุทธิ')}\n\n"
            "**ข้อควรระวัง**\n"
            "- ถ้าต้นทุนรวมยังไม่ครบ เช่น ค่าแรงหรือค่าขนส่ง กำไรจริงอาจลดลงครับ"
        )

    if any(term in query for term in ["กำไร", "เหลือ"]) and len(amounts) >= 2:
        revenue, cost = amounts[0], amounts[1]
        profit = revenue - cost
        return (
            "**สรุป**\n"
            f"- รายได้ **{_format_money(revenue)} บาท** หักต้นทุน **{_format_money(cost)} บาท** "
            f"จะเหลือกำไรประมาณ **{_format_money(profit)} บาท** ครับ\n\n"
            "**วิธีคำนวณ**\n"
            f"- {_format_money(revenue)} - {_format_money(cost)} = **{_format_money(profit)} บาท** ครับ\n\n"
            "**แผนภาพคำนวณ**\n"
            f"- {_calculation_flow('รายได้', 'หักต้นทุน', 'กำไรสุทธิ')}\n\n"
            "**ข้อควรระวัง**\n"
            "- ตัวเลขนี้ยังไม่รวมค่าใช้จ่ายอื่นที่อาจมี เช่น ขนส่ง ดอกเบี้ย หรือค่าเช่าที่ครับ"
        )

    baht_per_rai = detect_baht_per_rai(query, history)
    if area and baht_per_rai:
        total = area * baht_per_rai
        crop_phrase = f"สำหรับ **{crop}** " if crop else ""
        return (
            "**สรุป**\n"
            f"- {crop_phrase}ถ้าใช้ตัวเลข **{_format_money(baht_per_rai)} บาท/ไร่** กับพื้นที่ **{_format_money(area)} ไร่** "
            f"จะได้ประมาณ **{_format_money(total)} บาท** ครับ\n\n"
            "**วิธีคำนวณ**\n"
            f"- {_format_money(baht_per_rai)} × {_format_money(area)} = **{_format_money(total)} บาท** ครับ\n\n"
            "**แผนภาพคำนวณ**\n"
            f"- {_calculation_flow('บาท/ไร่', 'จำนวนไร่', 'เงินรวม')}\n\n"
            "**ข้อควรระวัง**\n"
            "- ตัวเลขนี้เป็นการคำนวณจากข้อมูลที่ผู้ใช้ให้ ไม่ใช่ราคาตลาดยืนยันครับ\n"
            "- ถ้าต้องการกำไรสุทธิ ต้องหักต้นทุนรวมออกก่อนครับ"
        )

    if not docs or not any(_has_financial_signal(doc) for doc in docs):
        return _financial_missing_answer(query, crop, history)

    return None


def _has_direct_financial_calculation(query: str, history: list[dict] | None) -> bool:
    if any(term in query for term in ["ไม่รู้", "ไม่มีตัวเลข", "ยังไม่มี", "ไม่มีราคา"]):
        return False
    amounts = detect_money_amounts(query)
    if _detect_labeled_amount(TOTAL_REVENUE_RE, query) is not None and _detect_labeled_amount(TOTAL_COST_RE, query) is not None:
        return True
    if any(term in query for term in ["กำไร", "เหลือ"]) and len(amounts) >= 2:
        return True
    if detect_area_rai(query) and detect_baht_per_rai_values(query):
        return True
    continuation_terms = ["แล้ว", "ถ้าเป็น", "เพิ่ม", "รวม", "ล่ะ", "ละ"]
    return any(term in query for term in continuation_terms) and bool(
        detect_area_rai(query, history) and detect_baht_per_rai(query, history)
    )


def _early_stage_care_answer(query: str, crop: str | None, history: list[dict] | None = None) -> str | None:
    if crop != "ข้าว":
        return None
    if not any(term in query for term in ["หลังปลูก", "ช่วงแรก", "ระยะแรก", "ดูแลช่วงแรก"]):
        return None
    return (
        "**สรุป**\n"
        "- หลังปลูกข้าวช่วงแรก ควรโฟกัสเรื่องน้ำ การตั้งตัวของต้นกล้า และการคุมวัชพืชก่อนครับ\n\n"
        "**ดูแลช่วงแรก**\n"
        "- รักษาความชื้นในแปลงให้สม่ำเสมอ อย่าให้ดินแห้งสลับเปียกแรงเกินไปครับ\n"
        "- เดินดูการงอกและการตั้งตัวของต้นข้าว ถ้ามีจุดที่ขึ้นไม่สม่ำเสมอให้รีบเช็กน้ำ ดิน และเมล็ดพันธุ์ครับ\n"
        "- คุมวัชพืชตั้งแต่ระยะแรก เพราะถ้าปล่อยให้แย่งน้ำและอาหาร จะกระทบการแตกกอครับ\n"
        "- สำรวจอาการแมลงหรือโรคเบื้องต้น เช่น ใบถูกกัด ใบม้วน หรือใบเหลืองผิดปกติ เพื่อจัดการได้เร็วครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- ช่วงแรกยังไม่ควรเร่งปุ๋ยหรือเร่งน้ำมากเกินไปจนต้นข้าวเครียดครับ\n"
        "- ถ้าต้องการ ผมช่วยต่อเรื่องปุ๋ยหรือการดูแลระยะถัดไปให้ตามช่วงอายุข้าวได้ครับ"
    )


def _direct_answer(query: str, crop: str | None, topic: str | None, docs: list[dict], history: list[dict] | None = None) -> str | None:
    if not crop:
        return None

    requested_topics = _detect_requested_topics(query)

    early_stage = _early_stage_care_answer(query, crop, history)
    if early_stage:
        return early_stage

    # ใช้ template planting plan เฉพาะเมื่อ RAG ไม่มี docs เท่านั้น
    if _is_crop_planning_question(query) and not is_financial_question(query) and not docs:
        return _crop_planting_plan_answer(query, crop, history)

    area = detect_area_rai(query)
    planning_terms = ["ดูแล", "ดูแปลง", "เตรียม", "วางแผน", "เริ่มดู", "หลังตัด", "ไว้ตอ"]
    if area and not is_financial_question(query) and not topic and not docs and not any(term in query for term in planning_terms):
        return (
            "**สรุป**\n"
            f"- พบว่าคุณถามเรื่อง **{crop}** พื้นที่ประมาณ **{_format_money(area)} ไร่** ครับ\n\n"
            "**คำแนะนำ**\n"
            "- ถ้าต้องการวางแผนปลูก ให้บอกจังหวัด ดิน แหล่งน้ำ และช่วงที่จะปลูกครับ\n"
            "- ถ้าต้องการคำนวณเงิน ให้บอกราคาขาย ผลผลิตต่อไร่ หรือต้นทุนต่อไร่เพิ่มครับ\n\n"
            "**ข้อควรระวัง**\n"
            "- บอกแค่จำนวนไร่ยังไม่พอสำหรับสรุปรายได้ ต้นทุน หรือกำไรครับ"
        )

    if (
        not docs
        and (topic == "harvest_duration" or any(word in query for word in ["เก็บเกี่ยว", "อายุเก็บ", "กี่วัน", "กี่เดือน", "เก็บตอน", "ใช้เวลา", "นานแค่ไหน", "กว่าจะได้", "กว่าจะตัด"]))
        and crop in HARVEST_FACTS
    ):
        direct_money_terms = ["ได้เงิน", "กี่บาท", "รายได้", "ต้นทุน", "กำไร"]
        info_request_terms = ["ต้องบอก", "ต้องใช้ข้อมูล", "ใช้อะไร", "บอกอะไร"]
        if any(term in query for term in direct_money_terms) and not any(term in query for term in info_request_terms):
            return _financial_missing_answer(query, crop, history)

        money_tip = ""
        if is_financial_question(query):
            money_tip = "\n- ถ้าจะคิดเงินต่อ ให้บอกจำนวนไร่ ผลผลิตต่อไร่ ราคาขาย และต้นทุนครับ"
        return (
            "**สรุป**\n"
            f"- {HARVEST_FACTS[crop]}\n\n"
            "**คำแนะนำ**\n"
            "- ใช้พันธุ์และสภาพแปลงจริงประกอบการตัดสินใจวันเก็บเกี่ยวครับ"
            f"{money_tip}"
        )

    if crop == "ยางพารา" and any(term in query for term in ["กรีดได้", "เริ่มกรีด", "กี่ปีกว่าจะกรีด", "กี่ปี", "พืชแซม", "ปลูกแซม"]):
        return (
            "**สรุป**\n"
            "- ยางพาราปลูกใหม่โดยทั่วไปต้องรอประมาณ **6-7 ปี** จึงเริ่มกรีดได้ครับ\n\n"
            "**วิธีวางแผนช่วงรอ**\n"
            "- ช่วงแรกต้องเน้นดูแลวัชพืช น้ำ และปุ๋ยให้ต้นยางตั้งตัวดีครับ\n"
            "- ถ้าจะปลูกพืชแซม ควรเลือกพืชอายุสั้นในระบบ เช่น **ข้าวโพดเลี้ยงสัตว์**, **ถั่วเขียว** หรือ **สับปะรด** ตามสภาพแปลงและน้ำครับ\n"
            "- อย่าปลูกพืชแซมหนาแน่นจนแย่งแสง น้ำ และปุ๋ยกับต้นยางครับ\n\n"
            "**ข้อควรระวัง**\n"
            "- ต้นทุนช่วงรอเปิดกรีดขึ้นกับแรงงาน น้ำ ปุ๋ย และการคุมหญ้า ถ้าจะคำนวณละเอียดควรมีข้อมูลต่อไร่ของแปลงจริงครับ"
        )

    if crop == "มะพร้าว" and any(term in query for term in ["ลูกร่วง", "ร่วงก่อนแก่", "ทะลายเล็ก", "ลูกทะลายเล็ก"]):
        return (
            "**สรุป**\n"
            "- มะพร้าวลูกร่วงก่อนแก่และทะลายเล็ก อาจเกี่ยวกับทั้ง **ขาดน้ำ** และ **แมลงเข้าทำลาย** ได้ครับ\n\n"
            "**วิธีทำ**\n"
            "- เริ่มเช็กน้ำก่อน โดยดูว่าดินแห้งเร็ว ต้นโทรม หรือใบลู่ผิดปกติหรือไม่ครับ\n"
            "- สำรวจยอด ทางใบ และทะลาย ว่ามีรอยกัด หนอน หรือด้วงเข้าทำลายหรือไม่ครับ\n"
            "- บำรุงต้นด้วยน้ำให้สม่ำเสมอและดูความสมบูรณ์ของธาตุอาหาร อย่าเร่งปุ๋ยหนักทันทีถ้าต้นกำลังเครียดครับ\n\n"
            "**ข้อควรระวัง**\n"
            "- ถ้าอาการลามเร็วหรือมีแมลงในยอด ควรรีบให้เจ้าหน้าที่เกษตรช่วยดูหน้างานครับ"
        )

    if crop == "ปาล์มน้ำมัน" and any(term in query for term in ["ฝนตกหนัก", "น้ำท่วม", "น้ำท่วมขัง", "ฝนชุก"]):
        return (
            "**สรุป**\n"
            "- ฝนตกหนักและน้ำท่วมขังทำให้ปาล์มน้ำมันรากขาดอากาศ เก็บเกี่ยวลำบาก และผลผลิตลดลงได้ครับ\n\n"
            "**ผลกระทบที่ควรดู**\n"
            "- ทะลายอาจเล็กลง คุณภาพผลลด และแปลงเข้าเก็บเกี่ยวได้ยากขึ้นครับ\n"
            "- ถ้าน้ำขังนาน รากอ่อนแอและต้นฟื้นตัวช้าหลังฝนครับ\n\n"
            "**ข้อควรระวัง**\n"
            "- ถ้าจะโยงกับราคา ควรใช้ราคาย้อนหลังเป็นข้อมูลอ้างอิง ไม่ควรสรุปเหตุผลด้านราคาจากอากาศอย่างเดียวครับ"
        )

    if crop == "ลำไย" and any(term in query for term in ["แล้ง", "ร้อน", "ดินร่วนปนเหนียว"]):
        return (
            "**สรุป**\n"
            "- ถ้าเทียบกับพืชนอกระบบอย่างเงาะ ตอนนี้ระบบยังช่วยวิเคราะห์เชิงลึกได้เฉพาะ **ลำไย** ครับ และลำไยพอรับสภาพร้อนแล้งได้ดีกว่าพืชที่ชอบความชื้นมาก\n\n"
            "**วิธีดูความเหมาะสม**\n"
            "- ดินร่วนปนเหนียวปลูกได้ถ้าระบายน้ำดีและไม่ปล่อยให้แฉะช่วงฝนครับ\n"
            "- ช่วงแล้งควรดูน้ำสำรองและการคลุมโคนเพื่อลดการสูญเสียน้ำครับ\n\n"
            "**ข้อควรระวัง**\n"
            "- ถ้าจะเทียบกับเงาะโดยตรง ตอนนี้ DrKaset ยังไม่มีข้อมูลเงาะในระบบ จึงไม่ควรฟันธงเทียบข้ามพืชครับ"
        )

    if crop == "ข้าว" and any(term in query for term in ["แมลง", "ศัตรูพืช"]) and any(term in query for term in ["ปุ๋ย", "สูตรไหน"]):
        return (
            "**สรุป**\n"
            "- ถ้าข้าวหอมมะลิมีแมลงลง ให้เริ่มจากการสำรวจชนิดแมลงและระดับการระบาดก่อน แล้วค่อยจัดการร่วมกับการใส่ปุ๋ยให้พอดีครับ\n\n"
            "**วิธีจัดการแมลง**\n"
            "- สำรวจใต้ใบ กอข้าว และคันนา เพื่อดูว่าเป็นเพลี้ย หนอน หรือแมลงดูดกินชนิดใดครับ\n"
            "- ถ้าระบาดยังไม่มาก ให้ลดวัชพืชและเก็บส่วนที่เสียหาย พร้อมติดตามอาการต่อเนื่องครับ\n"
            "- ถ้าระบาดมาก ควรใช้วิธีป้องกันกำจัดที่เหมาะกับชนิดแมลงและทำตามคำแนะนำเจ้าหน้าที่เกษตรครับ\n\n"
            "**แนวทางป้องกัน**\n"
            "- อย่าใส่ปุ๋ยไนโตรเจนมากเกินไป เพราะจะกระตุ้นใบอ่อนและทำให้แมลงเข้าระบาดง่ายขึ้นครับ\n"
            "- รักษาระดับน้ำและความสะอาดแปลงเพื่อลดแหล่งสะสมแมลงครับ\n\n"
            "**สูตรปุ๋ย**\n"
            "- ช่วงนี้ให้เลือกสูตรปุ๋ยตามระยะข้าวในแปลง และเน้นใส่พอดี ไม่เร่งไนโตรเจนเกินครับ\n"
            "- คำแนะนำนี้ **อ้างอิงข้าวหอมมะลิ** และข้อมูลการปลูกข้าวในระบบเป็นหลักครับ"
        )

    if crop == "ยางพารา" and any(term in query for term in ["น้ำยางออกน้อย", "น้ำยางน้อย"]):
        return (
            "**สรุป**\n"
            "- น้ำยางออกน้อยอาจเกิดได้จากทั้งสภาพอากาศ ดิน การบำรุงต้น และความสมบูรณ์ของต้นยางครับ\n\n"
            "**เชื่อมโยงอากาศหรือดิน**\n"
            "- ต้องเช็กทั้งสภาพอากาศและดินร่วมกัน ไม่ควรดูแค่มิติเดียวครับ\n\n"
            "**วิเคราะห์สาเหตุ**\n"
            "- ถ้าช่วงนี้แล้งจัด ดินแห้ง หรือฝนทิ้งช่วง ต้นยางจะเครียดและให้น้ำยางลดลงได้ครับ\n"
            "- ถ้าดินเสื่อม ขาดธาตุอาหาร หรือระบายน้ำไม่ดี ก็ทำให้ต้นยางอ่อนแรงและกรีดได้น้ำยางน้อยลงครับ\n\n"
            "**วิธีบำรุงต้น**\n"
            "- รักษาความชื้นดินให้เหมาะสม และอย่าปล่อยให้ต้นขาดน้ำต่อเนื่องครับ\n"
            "- ใส่ปุ๋ยบำรุงตามสภาพต้นและดิน ไม่เร่งมากเกินไป และคุมวัชพืชรอบโคนต้นครับ\n"
            "- ตรวจอาการโรคที่หน้ายาง โคนต้น และใบประกอบกันก่อนปรับแผนกรีดครับ\n\n"
            "**คำแนะนำเชิงปฏิบัติ**\n"
            "- ถ้าต้นโทรมมาก ควรลดความถี่กรีดชั่วคราวและฟื้นต้นก่อนครับ"
        )

    if crop == "ทุเรียน" and any(term in query for term in ["จันทบุรี", "ทุนตั้งต้น", "เตรียมดิน"]):
        cost_block = _structured_cost_block(crop) or ""
        weather_block = _structured_weather_block("ตะวันออก") or ""
        return (
            "**สรุป**\n"
            "- ทุเรียนในจันทบุรีโดยภาพรวมยังถือว่าเหมาะ แต่ถ้าจะประเมินอากาศย้อนหลังต้องใช้ข้อมูลภูมิอากาศประกอบอย่างระวังครับ\n\n"
            "**วิเคราะห์อากาศย้อนหลัง**\n"
            "- ให้ดูแนวโน้มฝน ความชื้น และอุณหภูมิย้อนหลัง 3 ปีประกอบ เพราะทุเรียนไวต่อทั้งน้ำขังและความแล้งครับ\n\n"
            "**แนวทางเตรียมดิน**\n"
            "- ดินควรระบายน้ำดี ยกร่องหรือยกโคกถ้าพื้นที่เสี่ยงน้ำขัง และเติมอินทรียวัตถุเพื่อช่วยโครงสร้างดินครับ\n"
            "- อย่าปลูกในแอ่งน้ำหรือจุดที่ระบายน้ำช้า เพราะเสี่ยงรากเน่าโคนเน่าครับ\n\n"
            "**สรุปความเหมาะสม**\n"
            "- ถ้าจัดการดินและน้ำได้ดี จันทบุรีก็ยังเป็นพื้นที่ที่เหมาะกับทุเรียนครับ\n\n"
            f"{cost_block}\n\n{weather_block}".strip()
        )

    if crop == "สับปะรด" and any(term in query for term in ["แล้ง", "ฝนทิ้งช่วง", "สภาพอากาศแบบนี้ยังไหวไหม"]):
        price_block = _structured_price_block(query, crop) or ""
        weather_block = _structured_weather_block("ใต้") or ""
        return (
            "**สรุป**\n"
            "- สับปะรดเป็นพืชที่พอทนแล้งได้ระดับหนึ่ง แต่ถ้าแล้งจัดต่อเนื่องและฝนทิ้งช่วงนาน ก็ทำให้ผลเล็กและคุณภาพลดลงได้ครับ\n\n"
            "**วิเคราะห์สภาพอากาศ**\n"
            "- ถ้าช่วง 3 ปีหลังฝนทิ้งช่วงบ่อย ต้องวางแผนน้ำสำรองและการคลุมดินให้ดีครับ\n"
            "- ความทนแล้งของสับปะรดดีกว่าพืชหลายชนิด แต่ก็ไม่ควรปล่อยให้ขาดน้ำยาวครับ\n\n"
            "**สรุปความเหมาะสม**\n"
            "- ถ้ามีน้ำเสริมและดินระบายน้ำดี ยังปลูกสับปะรดส่งโรงงานได้ครับ แต่ความเสี่ยงจะสูงขึ้นถ้าไม่มีน้ำช่วยช่วงแล้ง\n\n"
            "**ราคาอ้างอิงล่าสุดในชุดข้อมูล**\n"
            "- ถ้าหมายถึง **ราคาปัจจุบัน** แบบตลาดเรียลไทม์ ตอนนี้ระบบยังไม่ได้ดึงแบบนั้นครับ และด้านล่างคือราคาอ้างอิงล่าสุดในชุดข้อมูล\n\n"
            f"{price_block}\n\n{weather_block}".strip()
        )

    if crop == "ปาล์มน้ำมัน" and any(term in query for term in ["ทะลายเล็ก", "ลีบมาก", "หน้าแล้ง"]):
        cost_block = _structured_cost_block(crop) or ""
        return (
            "**สรุป**\n"
            "- ปาล์มน้ำมันทะลายเล็กและลีบมากในหน้าแล้ง มักเกี่ยวกับน้ำไม่พอและการบำรุงธาตุอาหารไม่สมดุลครับ\n\n"
            "**วิเคราะห์ปัญหา**\n"
            "- ช่วงแล้งถ้าดินแห้งนาน รากดูดธาตุอาหารได้น้อยลง ทำให้ทะลายเล็กและผลไม่เต็มครับ\n"
            "- ควรเช็กทั้งน้ำ ความชื้นดิน และอาการขาดธาตุอาหารจากใบพร้อมกันครับ\n\n"
            "**วิธีใส่ปุ๋ย**\n"
            "- ใส่ปุ๋ยตอนดินยังมีความชื้นพอ และแบ่งใส่เป็นรอบแทนการใส่หนักครั้งเดียวครับ\n"
            "- เสริมอินทรียวัตถุหรือคลุมโคนเพื่อช่วยรักษาความชื้นในหน้าแล้งครับ\n\n"
            f"{cost_block}".strip()
        )

    if any(keyword in query.lower() for keyword in COMPARE_KEYWORDS):
        return None

    if is_financial_question(query):
        financial = _direct_financial_answer(query, crop, docs, history)
        if financial:
            return financial

    if topic == "price":
        if docs and any(_has_financial_signal(doc) for doc in docs):
            return None
        price_lines = []
        for doc in docs:
            content = doc.get("content", "")
            meta = doc.get("metadata", {})
            file_name = str(meta.get("file_name", ""))
            if _has_financial_signal(doc):
                price_lines.append(content[:350])
        if price_lines:
            return (
                "**สรุป**\n"
                f"- พบข้อมูลราคาหรือความคุ้มค่าของ{crop}ในฐานข้อมูล แต่ควรอ่านเป็นรายปีหรือรายพื้นที่ครับ\n\n"
                "**ข้อมูลที่พบ**\n"
                f"- {price_lines[0]}\n\n"
                "**คำแนะนำ**\n"
                "- ถ้าต้องการความแม่นยำ ให้ระบุปีหรือจังหวัดที่ต้องการดูครับ"
            )
        return (
            "**สรุป**\n"
            f"- ฐานข้อมูลพบข้อมูลของ{crop} แต่ยังไม่พบราคาย้อนหลังที่ชัดเจนในเอกสารที่ดึงได้ครับ\n\n"
            "**คำแนะนำ**\n"
            "- ถ้าระบุปีหรือจังหวัด ผมจะช่วยไล่ดูข้อมูลราคาให้แม่นขึ้นครับ"
        )

    # กลุ่ม 2-11: ถ้ามี docs จาก RAG ให้ LLM ตอบจากเอกสารจริง
    # template เหล่านี้เป็น fallback เฉพาะกรณีไม่มี docs เท่านั้น

    if not docs:
        if any(term in query for term in ["พ่นสารก่อนฝน", "พ่นยาก่อนฝน", "ฉีดสารก่อนฝน", "ฉีดยาก่อนฝน", "พ่นสารก่อนฝนตั้งเค้า"]) or (
            any(term in query for term in ["พ่นสาร", "พ่นยา", "ฉีดสาร", "ฉีดยา"]) and any(term in query for term in ["ฝน", "ตั้งเค้า", "ควรรอ"])
        ):
            return _spray_before_rain_answer(crop)

        if "ใบด่าง" in query and crop == "มันสำปะหลัง":
            return _cassava_leaf_mosaic_answer()

        if topic == "water" and crop == "ถั่วเขียว":
            return (
                "**สรุป**\n"
                "- ถั่วเขียวควรให้ดินชื้นพอดี ไม่แฉะ และต้องระบายน้ำดีครับ\n\n"
                "**วิธีทำ**\n"
                "- ให้น้ำเมื่อหน้าดินเริ่มแห้ง แต่อย่าให้น้ำขังครับ\n"
                "- ถ้าฝนตกต่อเนื่อง ให้เน้นเปิดทางระบายน้ำในแปลงครับ\n\n"
                "**ข้อควรระวัง**\n"
                "- น้ำขังทำให้รากเสียและเสี่ยงโรคโคนเน่าได้ครับ"
            )

        if topic == "water" and crop == "ข้าว" and any(term in query for term in ["น้ำเยอะ", "น้ำขัง", "น้ำมาก"]):
            return (
                "**สรุป**\n"
                "- ถ้านาข้าวน้ำเยอะเกินไป ให้รีบจัดระดับน้ำและเปิดทางระบายออกจากแปลงครับ\n\n"
                "**วิธีทำ**\n"
                "- เปิดร่องหรือคันระบายน้ำให้น้ำส่วนเกินไหลออกครับ\n"
                "- ตรวจต้นข้าวว่ารากขาดอากาศ ใบเหลือง หรือแปลงเริ่มมีกลิ่นเน่าหรือไม่ครับ\n"
                "- หลังน้ำลด ค่อยประเมินปุ๋ยและโรคพืช อย่าใส่ปุ๋ยทันทีตอนน้ำยังท่วมครับ\n\n"
                "**ข้อควรระวัง**\n"
                "- น้ำขังนานทำให้รากอ่อนแอและเสี่ยงโรคได้ครับ"
            )

        if topic == "fertilizer" and crop == "สับปะรด":
            return (
                "**สรุป**\n"
                "- สับปะรดควรใส่ปุ๋ยตามระยะการเจริญเติบโต และปรับตามสภาพดินครับ\n\n"
                "**วิธีทำ**\n"
                "- ช่วงต้นให้เน้นบำรุงต้นและใบด้วยไนโตรเจนพอเหมาะครับ\n"
                "- หลังต้นตั้งตัว ให้เสริมโพแทสเซียมเพื่อช่วยคุณภาพผลครับ\n\n"
                "**ข้อควรระวัง**\n"
                "- อย่าใส่ปุ๋ยเข้มเกินไปในช่วงแล้ง ควรมีความชื้นพอให้ปุ๋ยละลายครับ"
            )

        if topic == "fertilizer" and crop == "ปาล์มน้ำมัน":
            return (
                "**สรุป**\n"
                "- ปาล์มน้ำมันใส่ปุ๋ยควรดูผลวิเคราะห์ดิน อาการทางใบ และอายุของต้นครับ\n\n"
                "**วิธีทำ**\n"
                "- เช็กสีใบและความสมบูรณ์ของทะลายก่อนปรับสูตรปุ๋ยครับ\n"
                "- ใส่ปุ๋ยตอนดินมีความชื้นพอ ไม่ใส่ชิดโคนเกินไปครับ\n"
                "- แบ่งใส่ตามรอบการเจริญเติบโตแทนการใส่หนักครั้งเดียวครับ\n\n"
                "**ข้อควรระวัง**\n"
                "- ปุ๋ยมากเกินไปทำให้ต้นเครียดและต้นทุนสูงโดยไม่จำเป็นครับ"
            )

        if topic == "planting_season" and crop == "สับปะรด":
            return (
                "**สรุป**\n"
                "- สับปะรดปลูกช่วงฝนได้ถ้าแปลงระบายน้ำดี และไม่มีน้ำขังครับ\n\n"
                "**วิธีทำ**\n"
                "- ยกร่องหรือทำทางระบายน้ำก่อนปลูกครับ\n"
                "- เลือกหน่อพันธุ์แข็งแรง และอย่าปลูกลึกจนยอดชื้นแฉะครับ\n\n"
                "**ข้อควรระวัง**\n"
                "- ฝนตกหนักต่อเนื่องทำให้รากเน่าและต้นตั้งตัวช้าได้ครับ"
            )

        if crop == "อ้อย" and any(term in query for term in ["ร้อน", "แล้ง", "ฝนทิ้งช่วง"]):
            return (
                "**สรุป**\n"
                "- ปลูกอ้อยช่วงร้อนจัดต้องระวังน้ำไม่พอ ดินแห้ง และท่อนพันธุ์ตั้งตัวช้าครับ\n\n"
                "**วิธีทำ**\n"
                "- เตรียมดินให้เก็บความชื้น และปลูกเมื่อมีน้ำหรือฝนช่วยพอครับ\n"
                "- ใช้ท่อนพันธุ์สมบูรณ์ ไม่แห้ง ไม่เป็นโรคครับ\n"
                "- คลุมดินหรือจัดการเศษใบอ้อยเพื่อลดการสูญเสียน้ำถ้าทำได้ครับ\n\n"
                "**ข้อควรระวัง**\n"
                "- ถ้าฝนทิ้งช่วงนาน อ้อยงอกไม่สม่ำเสมอและต้องซ่อมปลูกเพิ่มครับ"
            )

        if crop == "มันสำปะหลัง" and any(term in query for term in ["เดือนแรก", "หลังปลูก"]):
            return (
                "**สรุป**\n"
                "- เดือนแรกหลังปลูกมันสำปะหลัง ให้เน้นท่อนพันธุ์ตั้งตัวดี ดินไม่แฉะ และคุมหญ้าครับ\n\n"
                "**วิธีทำ**\n"
                "- เช็กท่อนพันธุ์ที่ไม่แตกยอดหรือแห้งตาย แล้วซ่อมปลูกให้ทันครับ\n"
                "- กำจัดหญ้าอย่าให้แย่งน้ำและปุ๋ย โดยเฉพาะช่วงต้นยังเล็กครับ\n"
                "- ถ้าฝนทิ้งช่วง ให้รักษาความชื้นในดิน แต่อย่าให้น้ำขังครับ\n\n"
                "**ข้อควรระวัง**\n"
                "- น้ำขังช่วงต้นทำให้ท่อนพันธุ์เน่าและแปลงเสียหายได้ครับ"
            )

        if crop == "ทุเรียน" and any(term in query for term in ["รากเน่า", "โคนเน่า"]):
            return (
                "**สรุป**\n"
                "- รากเน่าโคนเน่าในทุเรียนมักเกี่ยวกับน้ำขัง ความชื้นสูง และดินระบายไม่ดีครับ\n\n"
                "**วิธีทำ**\n"
                "- เปิดทางระบายน้ำ ไม่ให้โคนต้นแฉะหรือน้ำขังครับ\n"
                "- เก็บเศษพืชป่วยออกจากโคนต้น และเลี่ยงทำแผลที่โคนครับ\n"
                "- สำรวจโคน รากฝอย และใบเหี่ยวผิดปกติให้เร็วครับ\n\n"
                "**ข้อควรระวัง**\n"
                "- ถ้าโคนเริ่มเน่าแล้วควรให้เจ้าหน้าที่เกษตรช่วยดูอาการจริงก่อนใช้สารใด ๆ ครับ"
            )

        if crop == "มะพร้าว" and any(term in query for term in ["ด้วง", "แมลง"]):
            return (
                "**สรุป**\n"
                "- มะพร้าวโดนด้วงหรือแมลง ให้เริ่มเช็กยอดอ่อน ทางใบ และรอยเจาะก่อนครับ\n\n"
                "**วิธีทำ**\n"
                "- สำรวจยอดว่ามีรอยกัด รูเจาะ หรือใบยอดแหว่งหรือไม่ครับ\n"
                "- ดูโคนทางใบและซอกใบว่ามีตัวด้วง หนอน หรือเศษขุยหรือไม่ครับ\n"
                "- ตัดส่วนเสียหายรุนแรงออกและทำความสะอาดแปลงเพื่อลดแหล่งหลบซ่อนครับ\n\n"
                "**ข้อควรระวัง**\n"
                "- ถ้ายอดถูกทำลายมาก ต้นมะพร้าวอาจเสียหายหนัก ควรรีบให้เจ้าหน้าที่เกษตรช่วยดูครับ"
            )

        if crop == "ยางพารา" and "กรีด" in query:
            return (
                "**สรุป**\n"
                "- ก่อนเปิดกรีดยางพารา ให้ดูอายุและขนาดลำต้นเป็นหลัก อย่ารีบกรีดต้นที่ยังเล็กครับ\n\n"
                "**วิธีทำ**\n"
                "- เช็กอายุต้นและความสมบูรณ์ของทรงพุ่มครับ\n"
                "- วัดขนาดลำต้นให้ได้ตามเกณฑ์ที่พื้นที่แนะนำก่อนเปิดกรีดครับ\n"
                "- เปิดกรีดเฉพาะต้นแข็งแรง เปลือกพร้อม และไม่มีโรคที่โคนหรือลำต้นครับ\n\n"
                "**ข้อควรระวัง**\n"
                "- กรีดเร็วเกินไปทำให้ต้นช้ำ โตช้า และน้ำยางระยะยาวลดลงได้ครับ"
            )

        # generic fallback เมื่อไม่มี docs และไม่ match case ข้างต้น
        if "ใบด่าง" in query and crop == "มันสำปะหลัง":
            return (
                "**สรุป**\n"
                "- ใบด่างมันสำปะหลังเกิดจากไวรัส ถ้าพบต้นที่มีอาการให้แยกออกจากแปลงทันทีครับ\n\n"
                "**วิธีทำ**\n"
                "- สังเกตใบที่มีสีเหลืองสลับเขียว ใบหยักหรือบิดเบี้ยวผิดปกติครับ\n"
                "- ถอนต้นที่เป็นโรคออกและเผาทำลาย ห้ามนำท่อนพันธุ์จากต้นป่วยไปปลูกต่อครับ\n"
                "- ควบคุมแมลงพาหะ โดยเฉพาะแมลงหวี่ขาว ที่แพร่เชื้อไวรัสในแปลงครับ\n\n"
                "**ข้อควรระวัง**\n"
                "- ไวรัสใบด่างไม่มียารักษา การป้องกันไม่ให้แพร่กระจายสำคัญกว่าการรักษาครับ"
            )

        if topic != "price" and not is_financial_question(query):
            return _generic_crop_knowledge_answer(query, crop, topic)

    # กลุ่ม 12: topic == "price" — ให้ LLM สรุปจาก docs แทนการตัด raw content
    if topic == "price":
        if not docs or not any(_has_financial_signal(doc) for doc in docs):
            return (
                "**สรุป**\n"
                f"- ยังไม่พบข้อมูลราคาของ{crop}ในฐานข้อมูลที่ชัดเจนครับ\n\n"
                "**คำแนะนำ**\n"
                "- ถ้าระบุปีหรือจังหวัด ผมจะช่วยไล่ดูข้อมูลราคาให้แม่นขึ้นครับ"
            )
        # มี docs + financial signal → ให้ LLM สรุปผ่าน build_knowledge_prompt (return None)
        return None

    return None


# ---------------------------------------------------------------------------
# Date & Thai agricultural season helpers
# ---------------------------------------------------------------------------

def _get_thai_season(month: int) -> str:
    """Return the Thai agricultural season name for a given month (1–12)."""
    if 5 <= month <= 10:
        return "ฤดูฝน (พฤษภาคม–ตุลาคม)"
    elif month in (11, 12) or month <= 2:
        return "ฤดูหนาว (พฤศจิกายน–กุมภาพันธ์)"
    else:  # March–April
        return "ฤดูร้อน (มีนาคม–เมษายน)"


def _build_system_base() -> str:
    """Build SYSTEM_BASE with current date (Thai Buddhist Era) and season injected."""
    now = datetime.now()
    be_year = now.year + 543  # Convert CE to Thai Buddhist Era
    thai_months = [
        "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
        "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
    ]
    date_str = f"{now.day} {thai_months[now.month - 1]} พ.ศ. {be_year}"
    season = _get_thai_season(now.month)
    weather_summary = get_weather_summary_for_prompt()
    weather_instruction = (
        f"ข้อมูลอากาศล่าสุด: {weather_summary} ให้ใช้ประกอบคำแนะนำเรื่องน้ำ ฝน ความชื้น โรคพืช และช่วงปลูก "
        if weather_summary else ""
    )

    return (
        "คุณคือ ดร.เกษตร ผู้ช่วยด้านการเกษตรชาย สำหรับเกษตรกรไทย "
        "พูดจาเป็นมิตร ตรงไปตรงมา ใช้คำง่ายๆ เหมือนพี่ชายที่รู้เรื่องเกษตร "
        "ตอบสั้น กระชับ ได้ใจความ "
        f"{MARKDOWN_FORMAT_INSTRUCTION}"
        f"{_thai_only_instruction()}"
        f"วันนี้คือ {date_str} อยู่ในช่วง{season} "
        f"{weather_instruction}"
        "ให้คำนึงถึงฤดูกาลนี้ในการแนะนำการปลูก การดูแล และความเสี่ยงตามฤดูกาล "
        "ถ้ามีข้อมูลอ้างอิง ให้ใช้ข้อมูลอ้างอิงเป็นหลัก "
        "ถ้าไม่มีข้อมูลอ้างอิง แต่คำถามยังเกี่ยวกับการเกษตร ให้ตอบจากความรู้ทั่วไป "
        "และแจ้งให้ชัดว่าไม่พบข้อมูลในฐานข้อมูลของระบบ"
    )


# ---------------------------------------------------------------------------
# Static prompts & keyword lists
# ---------------------------------------------------------------------------

OUT_OF_SCOPE_REPLY = (
    "**สรุป**\n"
    "- คำถามนี้อยู่นอกขอบเขตของ DrKaset ครับ\n\n"
    "**ขอบเขตที่รองรับ**\n"
    "- กรุณาถามเกี่ยวกับพืชเศรษฐกิจ การปลูก โรคพืช แมลงศัตรูพืช ปุ๋ย ดิน น้ำ หรือการจัดการแปลงครับ"
)

SUPPORTED_CROP_REPLY = (
    "**สรุป**\n"
    "- ตอนนี้ DrKaset รองรับคำถามเฉพาะพืชเศรษฐกิจในระบบครับ\n\n"
    "**พืชที่รองรับ**\n"
    "- {crops} ครับ\n\n"
    "**คำแนะนำ**\n"
    "- บอกชื่อพืชและพื้นที่ปลูกมาได้เลย เช่น อ้อย 20 ไร่ หรือข้าว 10 ไร่ครับ"
)

SPECIFIC_CROP_PATTERNS = [
    "อยากปลูก",
    "จะปลูก",
    "ปลูก",
    "วิธีปลูก",
    "ดูแล",
    "โรค",
    "แมลง",
    "ใส่ปุ๋ย",
    "เก็บเกี่ยว",
    "ต้นทุน",
    "กำไร",
    "ราคา",
]

GREETING_KEYWORDS = [
    "สวัสดี", "หวัดดี", "สบายดี", "เป็นยังไงบ้าง", "เป็นไงบ้าง",
    "ขอบคุณ", "ขอบใจ", "โอเค", "ok", "hello", "hi", "hey",
    "how are you", "good morning", "good afternoon", "good evening",
    "ดีจัง", "เยี่ยมเลย", "ได้เลย",
    # คำถามเกี่ยวกับความสามารถของระบบ
    "ช่วยอะไรได้บ้าง", "ทำอะไรได้บ้าง", "มีอะไรบ้าง", "ใช้ทำอะไร",
    "คุณคือใคร", "นายคือใคร", "แกคือใคร", "เธอคือใคร",
    "คุณทำอะไรได้", "นายทำอะไรได้", "ระบบนี้คืออะไร",
]

PROFIT_KEYWORDS = [
    "กำไร", "ต้นทุน", "รายได้", "ผลตอบแทน", "คุ้มไหม", "คุ้มค่า",
    "เงิน", "บาท", "ได้เงิน", "หน้าไร่", "กี่บาท", "ราคาขาย", "ขายได้",
    "profit", "cost", "return", "revenue",
]
COMPARE_KEYWORDS = [
    "เปรียบเทียบ", "เทียบ", "ดีกว่า", "ต่างกัน", "แตกต่าง",
    "ง่ายกว่า", "เสี่ยงน้อยกว่า", "มากกว่า", "น้อยกว่า", "กว่า",
    "แบบไหน", "พืชไหน", "ชนิดไหน", "อะไรดูแล", "vs", "versus", "compare",
]
KNOWLEDGE_KEYWORDS = [
    "วิธี", "ปลูก", "เก็บเกี่ยว", "โรค", "แมลง", "ดูแล", "ใส่ปุ๋ย",
    "how to", "plant", "harvest", "disease", "pest", "fertilize",
]
AGRICULTURE_KEYWORDS = [
    "เกษตร", "พืช", "สวน", "ไร่", "นา", "แปลง", "ดิน", "น้ำ", "ปุ๋ย",
    "อินทรีย์", "ออร์แกนิก", "สารชีวภัณฑ์", "เพาะ", "เมล็ด", "ต้นกล้า",
    "ศัตรูพืช", "agriculture", "farm", "crop", "soil", "fertilizer", "organic",
]

TOPIC_KEYWORDS = {
    "profit": ["กำไร", "ต้นทุน", "รายได้", "คุ้ม", "คุ้มทุน", "เงิน", "บาท", "ได้เงิน", "หน้าไร่", "กี่บาท", "ขายได้", "ผลตอบแทน", "ประเมิน"],
    "harvest_duration": ["เก็บเกี่ยว", "เก็บตอน", "เกี่ยว", "อายุเก็บ", "กี่วัน", "กี่เดือน", "ใช้เวลา", "นานแค่ไหน", "กว่าจะได้ผลผลิต", "กว่าจะตัด", "harvest"],
    "fertilizer": ["ปุ๋ย", "ใส่ปุ๋ย", "ธาตุอาหาร", "บำรุง", "สูตร"],
    "price": ["ราคา", "ตลาด", "ย้อนหลัง", "เฉลี่ย"],
    "disease": [
        "โรค", "แมลง", "ศัตรูพืช", "เพลี้ย", "หนอน", "ใบด่าง", "ใบเหลือง", "ใบไหม้",
        "รากเน่า", "โคนเน่า", "เชื้อรา", "ราแป้ง", "ราสนิม", "สนิม", "ใบขาว", "แส้ดำ", "แส้", "เส้นดำ", "ใบร่วง", "รากขาว",
        "หน้ายางแห้ง", "หน้ากรีดแห้ง", "ทะลายเน่า", "ใบจุด", "ไหม้คอรวง",
        "แผล", "จุด", "ด่าง", "เหลือง", "แห้ง", "ลีบ", "หงิก", "แคระ", "ช้ำ",
        "เปื่อย", "ผุ", "กลิ่น", "มูลหนอน", "ขุย", "เส้นใย", "ยอดแห้ง", "ลำต้นมีรู",
        "รากผุ", "รากเปื่อย", "รวง", "ฝักมีรู", "ผงขาว", "ต้นแตกกอน้อย",
        "ถูกกัด", "โดนกัด", "กัดยอด", "คราบขาว", "ใบอ่อนถูกทำลาย", "เปลือก", "โทรม",
    ],
    "planting_season": ["ฤดู", "ช่วงปลูก", "ปลูกช่วง", "เดือนไหน", "ต้นฝน", "ปลายฝน", "หลังฝนแรก", "ก่อนฝน", "หน้าแล้ง", "ช่วงฝน", "ช่วงแล้ง"],
    "water": ["น้ำ", "ให้น้ำ", "ขาดน้ำ", "จัดการน้ำ", "ความชื้น"],
    "planting_method": [
        "วิธีปลูก", "เตรียมดิน", "ระยะปลูก", "ระยะห่าง", "ท่อนพันธุ์", "พื้นที่",
        "เตรียมแปลง", "ปรับแปลง", "เริ่มปลูก", "หัวข้อ", "เก็บข้อมูลแปลง",
        "ปลูกหลังนา", "เหมาะกับดิน", "ดินเหนียว", "ดินระบายน้ำ", "นาหว่าน", "นาดำ",
        "ยกร่อง", "พื้นราบ", "ร่อง", "หลุม",
    ],
}


# ---------------------------------------------------------------------------
# Intent & entity detection
# ---------------------------------------------------------------------------

def detect_topic_from_history(history: list[dict] | None) -> str | None:
    """Carry topic context from previous turns for short follow-up queries."""
    if not history:
        return None
    for message in reversed(history[-6:]):
        if message.get("role") != "user":
            continue
        content = str(message.get("content", ""))
        topic = detect_topic(content)
        if topic:
            return topic
    return None


def is_price_question(text: str) -> bool:
    t = text.lower()
    if any(term in t for term in ["ต้นทุน", "กำไร", "คุ้มทุน"]):
        return False
    if any(term in t for term in ["โรค", "แมลง", "ปุ๋ย", "ให้น้ำ", "ดูแล", "เตรียมดิน", "สภาพอากาศ", "ฝน", "แล้ง", "หน้าแล้ง"]):
        return False
    price_terms = ["ราคา", "ราคาย้อนหลัง", "ย้อนหลัง", "ราคาเฉลี่ย", "แนวโน้มราคา", "ราคาตลาด", "ปีไหน", "ปีอะไร", "ล่าสุด"]
    return any(term in t for term in price_terms)


def _is_compare_question(text: str, crops: list[str]) -> bool:
    t = text.lower()
    if len(crops) < 2:
        return False
    strong_markers = ["เปรียบเทียบ", "เทียบ", "ดีกว่า", "ต่างกัน", "แตกต่าง", "มากกว่า", "น้อยกว่า", "vs", "versus", "compare", "เลือกระหว่าง", "อันไหนดี"]
    soft_markers = ["ง่ายกว่า", "เสี่ยงน้อยกว่า", "แบบไหน", "พืชไหน", "ชนิดไหน", "อะไรดูแล"]
    return any(marker in t for marker in strong_markers + soft_markers)


def _should_carry_topic_from_history(query: str, query_crops: list[str]) -> bool:
    t = query.lower().strip()
    if query_crops and any(
        term in t
        for term in ["ใบ", "ดิน", "น้ำ", "ปุ๋ย", "ปลูก", "ดูแล", "โรค", "แมลง", "ช่วง", "ควร", "หลังปลูก"]
    ):
        return False
    return len(t) <= 40 or any(term in t for term in ["แล้ว", "ล่ะ", "ต่อ", "แบบนี้", "อีก", "ขั้นตอน", "อันนี้", "อันนั้น"])


def _detect_requested_topics(text: str) -> list[str]:
    t = text.lower()
    requested: list[str] = []
    has_fertilizer = any(keyword in t for keyword in TOPIC_KEYWORDS["fertilizer"])
    has_disease = _has_disease_intent(t)
    has_water = _has_water_intent(t) or any(term in t for term in ["ฝน", "แล้ง", "สภาพอากาศ", "อากาศ"])
    has_planting = any(keyword in t for keyword in TOPIC_KEYWORDS["planting_method"])
    checks = [
        ("price", is_price_question(t) or any(term in t for term in ["แนวโน้มราคา"])),
        ("profit", is_financial_question(t) or any(term in t for term in ["ต้นทุน", "กำไร", "คุ้มทุน", "ลงทุน", "ทุนตั้งต้น"])),
        ("disease", has_disease),
        ("fertilizer", has_fertilizer),
        ("water", has_water),
        ("planting_method", has_planting),
        ("planting_season", any(keyword in t for keyword in TOPIC_KEYWORDS["planting_season"])),
        ("harvest_duration", any(keyword in t for keyword in TOPIC_KEYWORDS["harvest_duration"])),
    ]
    for topic, matched in checks:
        if matched and topic not in requested:
            requested.append(topic)
    return requested


def detect_intent(text: str) -> str:
    t = text.lower()
    crops = detect_crop_in_text(text)
    requested_topics = _detect_requested_topics(text)
    if any(keyword in t for keyword in GREETING_KEYWORDS):
        return "greeting"
    if _is_compare_question(t, crops):
        return "compare"
    if _has_chemical_exposure_medical_request(text):
        return "knowledge"
    if len(requested_topics) >= 2:
        if "profit" in requested_topics and len(requested_topics) == 1:
            return "profit"
        return "knowledge"
    if is_price_question(t):
        return "price"
    if is_financial_question(t):
        return "profit"
    if any(keyword in t for keyword in PROFIT_KEYWORDS):
        return "profit"
    if any(keyword in t for keyword in KNOWLEDGE_KEYWORDS):
        return "knowledge"
    return "knowledge"


def _has_water_intent(text: str) -> bool:
    t = text.lower()
    water_context_terms = [
        "ให้น้ำ", "ขาดน้ำ", "จัดการน้ำ", "น้ำเยอะ", "น้ำมาก", "น้ำขัง", "ระบายน้ำ",
        "ความชื้น", "แล้ง", "หน้าแล้ง", "ฝนเยอะ", "ฝนตก", "ฝนน้อย", "ฝนทิ้งช่วง", "ฝนไม่สม่ำเสมอ",
    ]
    if any(term in t for term in water_context_terms):
        return True
    cleaned = t.replace("ปาล์มน้ำมัน", "").replace("น้ำมัน", "").replace("สีน้ำตาล", "").replace("น้ำยาง", "")
    return "น้ำ" in cleaned


def _has_disease_intent(text: str) -> bool:
    t = text.lower()
    return any(keyword in t for keyword in TOPIC_KEYWORDS["disease"])


def detect_topic(text: str) -> str | None:
    t = text.lower()
    requested_topics = _detect_requested_topics(text)
    has_disease = _has_disease_intent(t)
    has_fertilizer = any(keyword in t for keyword in TOPIC_KEYWORDS["fertilizer"])
    has_water = _has_water_intent(t)
    if _has_chemical_exposure_medical_request(text):
        return "disease"
    if len(requested_topics) >= 2:
        for preferred in ["disease", "fertilizer", "water", "planting_method", "profit", "price"]:
            if preferred in requested_topics:
                return preferred
    harvest_terms = TOPIC_KEYWORDS["harvest_duration"]
    if any(keyword in t for keyword in harvest_terms) or ("เก็บ" in t and any(term in t for term in ["พร้อม", "เร็ว", "ฝัก"])):
        return "harvest_duration"
    if is_price_question(t) or any(term in t for term in ["ราคาย้อนหลัง", "ตลาด", "ราคาเฉลี่ย", "แนวโน้มราคา"]) or ("ราคา" in t and any(term in t for term in ["ย้อนหลัง", "เฉลี่ย"])):
        return "price"
    if is_financial_question(t) or any(keyword in t for keyword in TOPIC_KEYWORDS["profit"]):
        return "profit"
    if any(keyword in t for keyword in TOPIC_KEYWORDS["price"]):
        return "price"
    if has_disease and has_fertilizer:
        return "disease"
    if "น้ำยาง" in t and any(term in t for term in ["ออกน้อย", "น้อยมาก", "กรีด"]):
        return "water" if has_water else "planting_method"
    if has_disease and not has_water:
        return "disease"
    if any(keyword in t for keyword in TOPIC_KEYWORDS["fertilizer"]):
        return "fertilizer"
    if any(term in t for term in ["ดินระบายน้ำ", "เหมาะกับดิน", "ดินเหนียว", "ปรับแปลง", "เตรียมแปลง", "เก็บข้อมูลแปลง"]):
        return "planting_method"
    if any(keyword in t for keyword in TOPIC_KEYWORDS["planting_season"]) and any(term in t for term in ["ปลูก", "ฤดู", "เดือนไหน"]):
        return "planting_season"
    if has_water:
        return "water"
    if any(keyword in t for keyword in TOPIC_KEYWORDS["planting_season"]):
        return "planting_season"
    if any(keyword in t for keyword in TOPIC_KEYWORDS["planting_method"]):
        return "planting_method"
    if has_disease:
        return "disease"
    # Summary/planning keywords after specific topics, so "วางแผนขาย" still routes to price.
    if any(kw in t for kw in ["สรุปแผน", "วางหัวข้อ", "ติดตาม", "แผนการดูแล", "ขั้นตอนต่อไป"]):
        return "planting_method"
    priority_topics = ["price", "profit", "fertilizer", "planting_season", "water", "planting_method", "disease"]
    for topic in priority_topics:
        keywords = TOPIC_KEYWORDS[topic]
        if any(keyword in t for keyword in keywords):
            return topic
    if is_financial_question(t):
        return "profit"
    return None


def is_financial_question(text: str) -> bool:
    t = text.lower()
    if is_out_of_domain_question(t):
        return False
    if is_price_question(t):
        return False
    if any(term in t for term in ["อย่าตอบเรื่องเงิน", "ไม่ต้องตอบเรื่องเงิน", "ไม่ถามเรื่องเงิน", "ไม่เอาเรื่องเงิน"]):
        return False
    explicit_money_terms = [
        "กำไร", "ต้นทุน", "รายได้", "ผลตอบแทน", "คุ้ม", "เงิน", "บาท",
        "ได้เงิน", "หน้าไร่", "กี่บาท", "ราคาขาย", "ขายได้", "ราคา", "ย้อนหลัง", "เฉลี่ย",
    ]
    if any(term in t for term in TOPIC_KEYWORDS["harvest_duration"]) and not any(term in t for term in explicit_money_terms):
        return False
    money_terms = [
        "กำไร", "ต้นทุน", "รายได้", "ผลตอบแทน", "คุ้ม", "เงิน", "บาท",
        "ได้เงิน", "หน้าไร่", "กี่บาท", "ราคาขาย", "ขายได้",
        "ราคา", "ย้อนหลัง", "เฉลี่ย",
    ]
    if any(term in t for term in money_terms):
        return True
    if "รวม" in t:
        return bool(detect_area_rai(t) or detect_baht_per_rai_values(t) or detect_money_amounts(t))
    if "เหลือ" in t:
        return any(term in t for term in ["เงิน", "บาท", "กำไร", "รายได้", "ต้นทุน", "ขาย"])
    if any(term in t for term in ["ล่ะ", "ละ"]):
        return bool(detect_area_rai(t) or detect_baht_per_rai_values(t) or any(term in t for term in ["ถ้าเป็น", "รวม"]))
    return False


def _is_monthly_price_trend_question(text: str) -> bool:
    t = text.lower()
    return any(term in t for term in ["ขึ้นหรือลง", "ขึ้นไหม", "ลงไหม", "แนวโน้ม", "จะขึ้น", "จะลง"]) and any(
        term in t for term in ["เดือนนี้", "ช่วงเดือนนี้", "ตอนนี้", "ช่วงนี้", "ราคา"]
    )


def _is_harvest_money_info_request(text: str) -> bool:
    t = text.lower()
    return any(term in t for term in TOPIC_KEYWORDS["harvest_duration"]) and any(
        term in t for term in ["ต้องบอก", "ต้องใช้ข้อมูล", "ใช้อะไร", "บอกอะไร", "อยากคิดเงิน", "คิดเงินต้อง"]
    )


def is_out_of_domain_question(text: str) -> bool:
    t = text.lower()
    out_of_domain_terms = [
        "คริปโต", "crypto", "หุ้น", "หวย", "พนัน", "ไฟฟ้า",
        "บิตคอยน์", "bitcoin", "btc", "รถไถ", "เครื่องจักร", "ซ่อมรถ", "ซ่อมเครื่อง",
        "เลี้ยงไก่", "ไก่ไข่", "กลอนรัก", "เขียนกลอน", "เมนูอาหาร", "อาหารเย็น",
        "สูตรอาหาร", "ตำรับ", "ทำอาหาร", "ร้านอาหาร", "ท่องเที่ยว", "โรงแรม",
        "ดูดวง", "โหราศาสตร์", "ไพ่ยิปซี", "ฮวงจุ้ย", "สีมงคล", "ดวงชะตา", "ราศี",
        "เสื้อผ้า", "ใส่เสื้อ", "แต่งตัว", "รองเท้า", 
        "สร้างบ้าน", "ผู้รับเหมา", "เทปูน", "ก่ออิฐ", "สร้างอาคาร",
        "ตำรวจ", "ทหาร", "ชายแดน", "ด่านตรวจ", "จับกุม",
        "คอมพิวเตอร์", "หน้าจอฟ้า", "เปิดไม่ติด", "มือถือ", "โทรศัพท์", "ไอที", "โปรแกรม", "ซอฟต์แวร์"
    ]
    if _contains_any(t, out_of_domain_terms):
        return True

    animal_terms = ["ไก่", "หมู", "วัว", "ควาย", "ปลา", "กุ้ง", "เป็ด", "ห่าน", "แพะ", "แกะ", "สุนัข", "หมา", "แมว"]
    agriculture_guard = ["ปุ๋ย", "ดิน", "แปลง", "ปลูก", "พืช", "ข้าว", "อ้อย", "มัน", "ยาง", "ปาล์ม", "ไล่"]
    
    if _contains_any(t, animal_terms) and not _contains_any(t, agriculture_guard):
        return True

    return False


def detect_non_scope_crop(text: str) -> str | None:
    t = text.replace("ํา", "ำ").lower()
    extra_non_scope = ["โคเคน", "cocaine"]
    for hint in extra_non_scope:
        if hint in t:
            return "โคเคน"
    for hint in sorted(NON_SCOPE_CROP_HINTS, key=len, reverse=True):
        if hint.lower() in t:
            return hint
    return None


def detect_crop(text: str) -> str | None:
    t = _normalize_crop_text(text.replace("??", "?"))
    for alias, canonical in sorted(CROP_ALIAS_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in t:
            return canonical
    return None


def detect_crop_in_text(text: str) -> list[str]:
    t = _normalize_crop_text(text.replace("??", "?"))
    matches: list[tuple[int, int, str]] = []
    for alias, canonical in sorted(CROP_ALIAS_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        index = t.find(alias)
        if index >= 0:
            matches.append((index, -len(alias), canonical))
    found: list[str] = []
    for _, _, canonical in sorted(matches):
        if canonical not in found:
            found.append(canonical)
    if "ข้าวโพด" in found and "ข้าว" in found and not re.search(r"ข้าว(?!โพด)", t):
        found.remove("ข้าว")
    if "ปาล์มน้ำมัน" in found and "มันสำปะหลัง" in found and "มันสำปะหลัง" not in t:
        found.remove("มันสำปะหลัง")
    return found


def detect_crop_in_history(history: list[dict] | None) -> list[str]:
    if not history:
        return []
    found: list[str] = []
    # Scan recent user turns only so assistant hallucinations do not become new context.
    for message in reversed(history[-12:]):
        if message.get("role") != "user":
            continue
        crops = detect_crop_in_text(str(message.get("content", "")))
        for crop in reversed(crops):
            if crop not in found:
                found.append(crop)
        if len(found) >= 4:
            break
    return list(reversed(found))

def detect_area_rai(text: str, history: list[dict] | None = None) -> float | None:
    half_matches = RAI_HALF_RE.findall(text.replace(",", ""))
    if half_matches:
        try:
            return float(half_matches[-1]) + 0.5
        except ValueError:
            return None

    current_matches = RAI_RE.findall(text.replace(",", ""))
    if current_matches:
        try:
            return float(current_matches[-1])
        except ValueError:
            return None

    continuation_terms = ["แล้ว", "ล่ะ", "ละ", "งั้น", "ถ้า", "รวม", "คำนวณ", "ต้นทุน", "กำไร", "รายได้", "ขาย"]
    if not any(term in text for term in continuation_terms):
        return None

    haystack = ""
    if history:
        haystack = " ".join(
            str(message.get("content", ""))
            for message in history[-6:]
            if message.get("role") == "user"
        )
    matches = RAI_RE.findall(haystack.replace(",", ""))
    if not matches:
        return None
    try:
        return float(matches[-1])
    except ValueError:
        return None


def detect_baht_per_rai(text: str, history: list[dict] | None = None) -> float | None:
    current_values = detect_baht_per_rai_values(text)
    if current_values:
        return current_values[-1]

    continuation_terms = ["แล้ว", "ถ้าเป็น", "เพิ่ม", "เท่าไร", "รวม"]
    if not any(term in text for term in continuation_terms):
        return None

    haystack = ""
    if history:
        haystack = " ".join(
            str(message.get("content", ""))
            for message in history[-6:]
            if message.get("role") == "user"
        )
    history_values = detect_baht_per_rai_values(haystack)
    if not history_values:
        return None
    return history_values[-1]


def detect_baht_per_rai_values(text: str) -> list[float]:
    values: list[float] = []
    cleaned = text.replace(",", "")
    for pattern in [BAHT_PER_RAI_RE, RAI_LA_BAHT_RE, NUMBER_PER_RAI_RE, PLAIN_PER_RAI_RE]:
        for raw, unit in pattern.findall(cleaned):
            try:
                values.append(_parse_thai_money(raw, unit))
            except ValueError:
                continue
    return values


def detect_money_amounts(text: str) -> list[float]:
    matches: list[tuple[int, float]] = []
    cleaned = text.replace(",", "")
    for match in BAHT_AMOUNT_RE.finditer(cleaned):
        raw, unit = match.groups()
        try:
            matches.append((match.start(), _parse_thai_money(raw, unit)))
        except ValueError:
            continue
    for match in THAI_UNIT_AMOUNT_RE.finditer(cleaned):
        raw, unit = match.groups()
        if not unit:
            continue
        try:
            matches.append((match.start(), _parse_thai_money(raw, unit)))
        except ValueError:
            continue
    matches.sort(key=lambda item: item[0])
    amounts: list[float] = []
    seen_positions: set[int] = set()
    for position, value in matches:
        if position in seen_positions:
            continue
        seen_positions.add(position)
        amounts.append(value)
    return amounts


def is_specific_crop_question(text: str) -> bool:
    t = text.lower()
    if detect_crop_in_text(t):
        return True
    if not any(pattern in t for pattern in SPECIFIC_CROP_PATTERNS):
        return False

    broad_terms = ["พืช", "อะไร", "ชนิดไหน", "แบบไหน", "ไหน", "เศรษฐกิจ"]
    return not any(term in t for term in broad_terms)


def detect_region_from_text(text: str) -> str | None:
    t = text.lower()
    for region, keywords in REGION_KEYWORDS.items():
        if any(keyword in t for keyword in keywords):
            return region
    return None


def is_agriculture_question(text: str) -> bool:
    t = text.lower()
    if any(keyword in t for keyword in AGRICULTURE_KEYWORDS):
        return True
    if detect_crop_in_text(text):
        return True
    if any(keyword in t for keyword in KNOWLEDGE_KEYWORDS + PROFIT_KEYWORDS + COMPARE_KEYWORDS):
        return True
    return False


def is_greeting(text: str) -> bool:
    t = text.lower()
    return any(keyword in t for keyword in GREETING_KEYWORDS)


def is_capability_question(text: str) -> bool:
    t = text.lower()
    capability_terms = [
        "ช่วยอะไรได้บ้าง", "ทำอะไรได้บ้าง", "ทำไรได้", "มีอะไรบ้าง",
        "ใช้ทำอะไร", "คุณทำอะไรได้", "นายทำอะไรได้", "ระบบนี้คืออะไร",
    ]
    return any(term in t for term in capability_terms)


def is_general_agriculture_help_question(text: str) -> bool:
    t = text.lower()
    return any(term in t for term in ["ช่วยแนะนำ", "แนะนำเรื่อง", "ถามเรื่องเกษตร", "เรื่องพืชเศรษฐกิจ"]) and any(
        term in t for term in ["พืช", "เกษตร", "แปลง", "ปลูก"]
    )


def is_comparison_question_guidance(text: str) -> bool:
    t = text.lower()
    return any(term in t for term in ["ถามแบบไหน", "ถามยังไง", "ควรถาม"]) and any(
        term in t for term in ["เปรียบเทียบ", "เทียบ", "สองชนิด", "2 ชนิด"]
    )


def is_current_market_price_question(text: str) -> bool:
    t = text.lower()
    return any(term in t for term in ["ราคาตลาดวันนี้", "ราคาตลาดตอนนี้", "ราคาปัจจุบัน", "ราคาวันนี้"]) or (
        "วันนี้" in t and "ราคา" in t
    )


def _capability_answer() -> str:
    crops = _target_crop_list()
    return (
        "**สรุป**\n"
        f"- ผม Dr.Kaset ยินดีช่วยเหลือครับ! ตอนนี้ระบบของผมรองรับพืชเศรษฐกิจหลักๆ คือ: **{crops}** ครับผม\n\n"
        "**เรื่องที่ผมช่วยได้**\n"
        "- 🌾 **การเพาะปลูก:** แนะนำวิธีเตรียมดิน ให้น้ำ ใส่ปุ๋ย และรับมือโรค/แมลง\n"
        "- 💰 **การเงิน:** ช่วยประเมินรายได้ ต้นทุน และกำไรต่อไร่ (อ้างอิงสถิติย้อนหลัง)\n"
        "- 📊 **เปรียบเทียบพืช:** วิเคราะห์เปรียบเทียบพืช 2 ชนิด ว่าตัวไหนเหมาะกับพื้นที่ ดิน และสภาพอากาศของคุณมากกว่ากันครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- สำหรับข้อมูลราคา ผมจะใช้สถิติย้อนหลังในระบบเป็นหลัก ยังไม่สามารถเช็กราคารายวันหน้าลานได้แบบเรียลไทม์นะครับ\n"
        "- วันนี้พี่มีพื้นที่ปลูกอยู่ที่ไหน และสนใจให้ผมช่วยวิเคราะห์พืชตัวไหนเป็นพิเศษไหมครับ?"
    )


def _is_thanks_only(text: str) -> bool:
    t = text.strip().lower()
    return t in {"ขอบคุณ", "ขอบคุณครับ", "ขอบใจ", "ขอบใจครับ", "โอเค", "โอเคครับ", "ok", "thanks", "thank you"}


def _thanks_answer(crop: str | None = None) -> str:
    next_tip = (
        f"- ถ้ามีข้อมูลพื้นที่ ราคา ผลผลิต หรืออาการของ{crop}เพิ่มเติม ผมช่วยคำนวณหรือไล่เช็กต่อได้ครับ"
        if crop
        else "- ถ้ามีข้อมูลพื้นที่ ราคา ผลผลิต หรืออาการพืชเพิ่มเติม ผมช่วยคำนวณหรือไล่เช็กต่อได้ครับ"
    )
    return (
        "**สรุป**\n"
        "- ยินดีครับ\n\n"
        "**ช่วยต่อได้**\n"
        f"{next_tip}"
    )


def _spray_before_rain_answer(crop: str | None = None) -> str:
    crop_note = f"สำหรับ **{crop}** " if crop else ""
    return (
        "**สรุป**\n"
        f"- {crop_note}โดยทั่วไป **ไม่ควรพ่นสารก่อนฝนตก** เพราะฝนอาจชะล้างสารออก ทำให้ประสิทธิภาพลดลงครับ\n\n"
        "**คำแนะนำ**\n"
        "- ควรพ่นเมื่อฝนหยุดแล้ว ใบไม่เปียก และคาดว่าจะไม่มีฝนซ้ำในช่วงหลังพ่นครับ\n"
        "- ถ้าจำเป็นต้องพ่น ให้ดูฉลากสารว่าต้องการเวลากี่ชั่วโมงก่อนเจอฝนครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- อย่าพ่นตอนลมแรงหรือฝนตั้งเค้า เพราะสารอาจปลิวหรือถูกชะล้างจนต้องพ่นซ้ำครับ"
    )


def _current_market_price_scope_answer(crop: str | None = None) -> str:
    crop_text = f"ของ **{crop}** " if crop else ""
    return (
        "**สรุป**\n"
        f"- ตอนนี้ระบบยังไม่มีราคาตลาดวันนี้{crop_text}แบบรายวันหรือหน้าสวนครับ\n\n"
        "**ข้อมูลที่มีในระบบ**\n"
        "- มีข้อมูลราคาเฉลี่ยย้อนหลังรายปีจากไฟล์ `prices_yearly_avg_all_crops.csv` ใช้เป็นข้อมูลอ้างอิงได้ครับ\n"
        "- ข้อมูลนี้เป็นราคาอ้างอิงย้อนหลัง ไม่ใช่ราคาตลาดวันนี้ครับ\n"
        "- ถ้าระบุชื่อพืชหรือปี ผมจะดึงราคาย้อนหลังตามที่มีในระบบให้ครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- อย่าใช้ราคาเฉลี่ยย้อนหลังแทนราคาซื้อขายวันนี้โดยตรง เพราะราคาจริงขึ้นกับพื้นที่ คุณภาพ และช่วงขายครับ"
    )


def _comparison_question_guidance_answer() -> str:
    return (
        "**สรุป**\n"
        "- ถ้าจะเปรียบเทียบพืชสองชนิด ให้บอกชื่อพืช ประเด็นที่อยากเทียบ และข้อมูลพื้นที่ให้ชัดครับ\n\n"
        "**วิธีถาม**\n"
        "- ระบุพืชทั้งสองชนิด เช่น ข้าวกับอ้อย หรือมันสำปะหลังกับยางพาราครับ\n"
        "- บอกว่าจะเทียบเรื่องอะไร เช่น น้ำ ดิน โรค ต้นทุน รายได้ หรือระยะเก็บเกี่ยวครับ\n"
        "- ถ้ามีพื้นที่ จังหวัด ดิน และแหล่งน้ำ ให้ใส่มาด้วยเพื่อให้คำตอบตรงแปลงมากขึ้นครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- ถ้าเทียบเรื่องเงิน ต้องมีผลผลิต ราคาขาย และต้นทุนของทั้งสองพืชก่อน ไม่ควรเดาตัวเลขครับ"
    )


def _historical_price_usage_answer() -> str:
    return (
        "**สรุป**\n"
        "- ข้อมูลราคาย้อนหลังควรใช้เป็น **ข้อมูลอ้างอิง** เพื่อดูภาพรวม ไม่ใช่ราคาตลาดวันนี้ครับ\n\n"
        "**วิธีใช้**\n"
        "- ดูแนวโน้มหลายปีของพืชชนิดเดียวกันก่อนตัดสินใจครับ\n"
        "- เทียบกับราคาซื้อขายจริงในพื้นที่ คุณภาพผลผลิต และช่วงเก็บเกี่ยวล่าสุดครับ\n"
        "- ถ้าจะคำนวณรายได้ ให้ใช้ราคาขายจริงหรือราคาที่คาดว่าจะขายได้ พร้อมผลผลิตต่อไร่ครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- อย่าใช้ราคาเฉลี่ยย้อนหลังรายปีแทนราคาหน้าสวนหรือราคาตลาดวันนี้โดยตรงครับ"
    )


def _short_bullet_ack_answer() -> str:
    return (
        "**สรุป**\n"
        "- ได้ครับ\n\n"
        "**วิธีตอบ**\n"
        "- ผมจะตอบเป็น bullet สั้น ๆ ให้ครับ\n"
        "- ถ้าถามเรื่องเงินแต่ข้อมูลไม่พอ ผมจะถามข้อมูลเพิ่มแทนการเดาครับ"
    )


def _cassava_leaf_mosaic_answer() -> str:
    return (
        "**สรุป**\n"
        "- ถ้าเจอ **ใบด่างมันสำปะหลัง** ให้สงสัยโรคใบด่างไว้ก่อน และแยกต้นที่มีอาการออกจากต้นปกติครับ\n\n"
        "**วิธีทำ**\n"
        "- สำรวจใบที่เหลืองสลับเขียว ใบหยัก บิดเบี้ยว หรือต้นแคระครับ\n"
        "- แยกหรือทำลายต้นที่เป็นโรค และอย่านำท่อนพันธุ์จากต้นป่วยไปปลูกต่อครับ\n"
        "- เฝ้าระวังแมลงพาหะ โดยเฉพาะแมลงหวี่ขาว และรีบสำรวจต้นรอบข้างครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- โรคใบด่างจากไวรัสไม่มียารักษาโดยตรง จึงต้องเน้นป้องกันการแพร่กระจายครับ"
    )


def _corn_ear_stage_answer(crop: str = "ข้าวโพด") -> str:
    return (
        "**สรุป**\n"
        f"- ช่วงติดฝักของ **{crop}** ต้องระวังน้ำไม่พอ แมลงเข้าทำลาย และโรคที่มากับความชื้นครับ\n\n"
        "**วิธีทำ**\n"
        "- รักษาความชื้นให้สม่ำเสมอ อย่าให้แปลงแห้งจัดหรือแฉะเกินไปครับ\n"
        "- สำรวจฝัก ใบ และยอดว่ามีหนอนหรือแมลงกัดกินหรือไม่ครับ\n"
        "- ถ้าฝนต่อเนื่อง ให้ดูโรคใบและการระบายน้ำในแปลงครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- อย่ารีบใช้สารโดยไม่เห็นอาการจริง และควรดูฉลากสารก่อนใช้ทุกครั้งครับ"
    )


def _orchard_inspection_answer(crops: list[str] | None = None) -> str:
    crop_text = ", ".join(crops or [])
    prefix = f"สำหรับสวนที่คุยกันเรื่อง **{crop_text}** " if crop_text else "สำหรับสวนนี้ "
    return (
        "**สรุป**\n"
        f"- {prefix}ให้เริ่มตรวจน้ำ ใบ ยอด และแมลงก่อนครับ\n\n"
        "**วิธีทำ**\n"
        "- น้ำและดิน: ดูน้ำขัง ดินแฉะ หรือดินแห้งเกินไปครับ\n"
        "- ใบและยอด: ดูใบเหลือง ใบร่วง ยอดผิดรูป หรือยอดถูกกัดครับ\n"
        "- แมลงและโรค: สำรวจเพลี้ย หนอน ด้วง รอยเจาะ และอาการเน่าเป็นจุดครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- ถ้าอาการลามเร็ว ควรถ่ายรูปและให้เจ้าหน้าที่เกษตรในพื้นที่ช่วยดูครับ"
    )


def _yellow_leaf_patch_answer(crop: str) -> str:
    return (
        "**สรุป**\n"
        f"- ถ้า **{crop}** มีใบหรือกล้าเหลืองเป็นหย่อม ๆ ให้เริ่มจากเช็กน้ำ ดิน ราก และโรค/แมลงในจุดที่เป็นก่อนครับ\n\n"
        "**วิธีทำ**\n"
        "- ดูว่าน้ำขัง แห้งจัด หรือแปลงระบายน้ำไม่สม่ำเสมอหรือไม่ครับ\n"
        "- ถอนต้นที่เป็นบางจุดมาดูราก ว่ารากดำ รากเน่า หรือมีแมลงกัดกินหรือไม่ครับ\n"
        "- เทียบใบที่เหลืองกับใบปกติ เพื่อดูว่าคล้ายขาดธาตุอาหารหรือเป็นโรคเฉพาะจุดครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- อย่ารีบใส่ปุ๋ยหรือพ่นสารทั้งแปลงทันที ควรยืนยันสาเหตุจากจุดที่เป็นก่อนครับ"
    )


def _rubber_tapping_answer() -> str:
    return (
        "**สรุป**\n"
        "- ก่อนเปิดกรีด **ยางพารา** ให้ดูอายุ ขนาดลำต้น สุขภาพต้น และสภาพอากาศก่อนครับ\n\n"
        "**วิธีทำ**\n"
        "- เปิดกรีดเมื่อต้นพร้อมจริง โดยดูขนาดลำต้นและความสมบูรณ์ของเปลือกเป็นหลักครับ\n"
        "- ตรวจว่าไม่มีอาการเปลือกแห้ง โรคเปลือก หรือแผลกรีดเก่าที่เสียหายครับ\n"
        "- เลี่ยงกรีดช่วงฝนตก ฝนตั้งเค้า หรือเปลือกเปียก เพราะน้ำยางไหลไม่ดีและเสี่ยงโรคครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- อย่าเปิดกรีดต้นที่ยังเล็กหรือโทรม เพราะกระทบผลผลิตและอายุการให้ผลระยะยาวครับ"
    )


def _multi_crop_risk_table_answer(crops: list[str]) -> str:
    unique_crops: list[str] = []
    for crop in crops:
        if crop and crop not in unique_crops:
            unique_crops.append(crop)
    if not unique_crops:
        unique_crops = ["พืชในแปลง"]

    rows = "\n".join(
        f"| {crop} | เช็กน้ำขัง/ขาดน้ำตามช่วงอายุพืช | สำรวจใบ ยอด ลำต้น และแมลงผิดปกติ | ใช้ราคาย้อนหลังเป็นข้อมูลอ้างอิง ไม่แทนราคาวันนี้ |"
        for crop in unique_crops[:4]
    )
    return (
        "**สรุป**\n"
        "- ตารางนี้สรุปข้อควรระวังจากพืชที่คุยกัน โดยไม่เดาราคา ตลาด หรือผลตอบแทนเพิ่มครับ\n\n"
        "| พืช | น้ำ | โรค/แมลง | ตลาด/ราคา |\n"
        "|---|---|---|---|\n"
        f"{rows}\n\n"
        "**ข้อควรระวัง**\n"
        "- ถ้าต้องตัดสินใจขายหรือคำนวณกำไร ควรมีราคาซื้อขายจริง ผลผลิตต่อไร่ และต้นทุนก่อนครับ"
    )


def _monthly_price_trend_answer(crop: str | None) -> str:
    latest_price = _latest_historical_price_row(crop)
    crop_text = crop or "พืชชนิดนี้"
    reference = ""
    if latest_price:
        crop_label, year, price, first_year, last_year = latest_price
        reference = (
            "\n**ราคาอ้างอิงย้อนหลังล่าสุด**\n"
            f"- ในไฟล์ `prices_yearly_avg_all_crops.csv` มีราคาเฉลี่ยย้อนหลังของ **{crop_label}** "
            f"ปี **{year}** คือ **{_format_price_value(price)}** ครับ\n"
            f"- ช่วงข้อมูลที่มีคือ **{first_year}-{last_year}** ครับ\n"
        )
    return (
        "**สรุป**\n"
        f"- ผมยังไม่ควรฟันธงว่า{crop_text}เดือนนี้ราคาจะขึ้นหรือลง เพราะระบบมีข้อมูลย้อนหลังรายปี ไม่ใช่ราคาตลาดรายวันหรือรายเดือนครับ\n"
        f"{reference}"
        "\n**คำแนะนำ**\n"
        "- ใช้ราคาอ้างอิงย้อนหลังเพื่อดูภาพกว้างได้ แต่ก่อนขายควรเช็กราคาลานรับซื้อหรือโรงงานในพื้นที่อีกครั้งครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- อย่าใช้ราคาเฉลี่ยรายปีแทนราคาซื้อขายวันนี้โดยตรง เพราะราคาอาจเปลี่ยนตามพื้นที่ คุณภาพ และช่วงเก็บเกี่ยวครับ"
    )


def is_in_scope(text: str) -> bool:
    """Return True for agriculture questions AND greetings/small talk."""
    return is_greeting(text) or is_agriculture_question(text)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _context_block(docs: list[dict]) -> str:
    if not docs:
        return "(ไม่พบข้อมูลที่เกี่ยวข้องในฐานข้อมูล)"

    parts = []
    for i, doc in enumerate(docs, 1):
        meta = doc.get("metadata", {})
        label = " | ".join(
            filter(None, [meta.get("crop", ""), meta.get("region", ""), meta.get("source_type", "")])
        )
        content = str(doc.get("content", "")).strip()
        excerpt = content[:520].strip()
        if len(content) > len(excerpt):
            excerpt += " ..."
        parts.append(f"[{i}] {label}\n{excerpt}")
    return "\n\n".join(parts)


def _target_crop_list() -> str:
    return ", ".join(TARGET_CROPS.keys())


def build_greeting_prompt(query: str) -> tuple[str, str]:
    target_crops = _target_crop_list()
    system = (
        "คุณคือ ดร.เกษตร ผู้ช่วยด้านการเกษตรชาย สำหรับเกษตรกรไทย "
        f"{_thai_only_instruction()}"
        "ทักทายด้วยความเป็นมิตรแบบพี่ชาย กระชับ ไม่เกิน 3 ประโยค "
        f"{MARKDOWN_FORMAT_INSTRUCTION}"
        "ถ้าผู้ใช้ถามว่าช่วยอะไรได้บ้างหรือถามเกี่ยวกับความสามารถของระบบ "
        "ให้แนะนำตัวสั้นๆ และบอกว่าช่วยได้เรื่องพืชเศรษฐกิจเหล่านี้: "
        f"{target_crops} "
        "เช่น การปลูก การดูแล โรคพืช แมลง ปุ๋ย และการเปรียบเทียบผลตอบแทน"
    )
    user = query
    return system, user


def build_profit_prompt(
    query: str,
    docs: list[dict],
    crop: str | None,
    requested_topics: list[str] | None = None,
    guardrail_note: str | None = None,
) -> tuple[str, str]:
    system = _build_system_base()
    context = _context_block(docs)
    requested_topics = requested_topics or ["profit"]
    topic_line = ", ".join(requested_topics)
    guard_line = f"{guardrail_note} " if guardrail_note else ""
    user = (
        f"คำถาม: {query}\n\n"
        f"ข้อมูลอ้างอิง:\n{context}\n\n"
        f"โจทย์ที่ต้องตอบมีประเด็นเหล่านี้: {topic_line}\n"
        f"{guard_line}"
        "กรุณาวิเคราะห์ความคุ้มค่า ต้นทุน กำไร หรือราคาตามที่ถามโดยอ้างอิงข้อมูลด้านบน "
        "ให้มีหัวข้อ **สรุป**, **ตัวเลขสำคัญ**, **คำแนะนำ**, **ข้อควรระวัง** "
        "ห้ามเรียกตัวเลขรายได้ว่าเป็นต้นทุน และห้ามคำนวณจากตัวเลขที่ไม่ได้อยู่ในคำถามหรือข้อมูลอ้างอิง "
        "ถ้าข้อมูลไม่พอ ให้บอกข้อมูลที่ต้องใช้เพิ่มแทนการเดาตัวเลข"
    )
    return system, user


def build_compare_prompt(
    query: str,
    docs: list[dict],
    crops: list[str],
    requested_topics: list[str] | None = None,
    guardrail_note: str | None = None,
) -> tuple[str, str]:
    system = _build_system_base()
    context = _context_block(docs)
    crop_str = " และ ".join(crops) if crops else "พืชที่ถามถึง"
    requested_topics = requested_topics or []
    focus = ", ".join(requested_topics) if requested_topics else "ประเด็นที่ถาม"
    context_focus = "\n".join(_compare_query_context_lines(query))
    guard_line = f"{guardrail_note} " if guardrail_note else ""
    user = (
        f"คำถาม: {query}\n\n"
        f"ข้อมูลอ้างอิง:\n{context}\n\n"
        f"{('เงื่อนไขแปลงจากคำถาม:\n' + context_focus + '\n\n') if context_focus else ''}"
        f"{guard_line}"
        f"กรุณาเปรียบเทียบ {crop_str} เฉพาะในประเด็นที่ผู้ใช้ถาม "
        f"โดยเน้นประเด็น {focus} "
        "ให้ใช้หัวข้อ **สรุป**, **เปรียบเทียบ**, **เลือกแบบไหนดี**, **ข้อควรระวัง** "
        "ห้ามคัดลอกคำว่า ข้อมูลอ้างอิง ห้ามแสดงเลขลำดับเอกสาร [1] [2] "
        "ห้ามแต่งตารางถ้าข้อมูลในเอกสารไม่พอ และห้ามเปรียบเทียบสิ่งที่ไม่ได้อยู่ในเอกสาร "
        "ถ้าผู้ใช้ถามหลายมิติ ให้ตอบเป็นข้อย่อยตามมิตินั้น ไม่ต้องวกไปเรื่องที่ไม่ได้ถาม"
    )
    return system, user


def build_knowledge_prompt(
    query: str,
    docs: list[dict],
    topic: str | None = None,
    crop: str | None = None,
    history_context: str | None = None,
    requested_topics: list[str] | None = None,
    guardrail_note: str | None = None,
) -> tuple[str, str]:
    system = _build_system_base()
    context = _context_block(docs)
    requested_topics = requested_topics or ([topic] if topic else [])
    topic_instruction = _topic_instruction_bundle(requested_topics, topic)
    crop_instruction = f"พืชที่กำลังตอบคือ {crop} ห้ามเปลี่ยนไปตอบพืชอื่น " if crop else ""
    history_note = f"บริบทจากบทสนทนาก่อนหน้า: {history_context} " if history_context else ""
    requested_line = f"ผู้ใช้ถามหลายประเด็น: {', '.join(requested_topics)} " if len(requested_topics) >= 2 else ""
    guard_line = f"{guardrail_note} " if guardrail_note else ""
    heading_guide = _heading_guide_for_topics(requested_topics, topic)
    focus_terms = _focus_terms_from_query(query)
    focus_line = f"คำสำคัญที่ควรยึดตอนตอบ: {', '.join(focus_terms)} " if focus_terms else ""
    user = (
        f"คำถาม: {query}\n\n"
        f"{history_note}"
        f"ข้อมูลอ้างอิง:\n{context}\n\n"
        f"{crop_instruction}"
        f"{requested_line}"
        f"{focus_line}"
        f"{guard_line}"
        f"โจทย์เฉพาะ: {topic_instruction} "
        f"{heading_guide}"
        "ห้ามเขียนประโยคซ้ำ ห้ามขึ้นต้นด้วยคำขอโทษถ้าข้อมูลอ้างอิงมีเนื้อหาที่เกี่ยวข้อง "
        "กรุณาตอบคำถามโดยอ้างอิงข้อมูลด้านบนเท่านั้น "
        "ถ้าข้อมูลอ้างอิงไม่ครอบคลุมประเด็นที่ถาม ให้บอกว่าข้อมูลอ้างอิงยังไม่พอและขอข้อมูลเพิ่ม "
        "ห้ามแต่งตัวเลขหรือข้อสรุปที่ไม่มีในข้อมูลอ้างอิง "
        "ห้ามใช้คำอังกฤษหรือคำทับศัพท์ถ้ามีคำไทยที่เข้าใจง่ายแทนได้ "
        "ถ้าผู้ใช้ถามหลายประเด็น ให้ตอบทุกประเด็นตามลำดับคำถาม ห้ามทิ้งประเด็นใดประเด็นหนึ่งไป"
    )
    return system, user


def build_fallback_prompt(query: str) -> tuple[str, str]:
    now = datetime.now()
    be_year = now.year + 543
    season = _get_thai_season(now.month)
    weather_summary = get_weather_summary_for_prompt()
    weather_instruction = (
        f"ข้อมูลอากาศล่าสุด: {weather_summary} ให้ใช้ประกอบคำแนะนำเรื่องน้ำ ฝน ความชื้น โรคพืช และช่วงปลูก "
        if weather_summary else ""
    )
    target_crops = _target_crop_list()
    system = (
        "คุณคือ ดร.เกษตร ผู้ช่วยด้านการเกษตรชาย สำหรับเกษตรกรไทย "
        "พูดจาเป็นมิตร ตรงไปตรงมา ใช้คำง่ายๆ เหมือนพี่ชายที่รู้เรื่องเกษตร "
        "ตอบสั้น กระชับ "
        f"{MARKDOWN_FORMAT_INSTRUCTION}"
        f"{_thai_only_instruction()}"
        "ขอบเขตของระบบคือพืชเศรษฐกิจในรายการนี้เท่านั้น: "
        f"{target_crops} "
        "ห้ามแนะนำหรือยกตัวอย่างพืชนอกเหนือจากรายการนี้ เช่น ผักสวนครัว เห็ด ดอกไม้ สมุนไพร หรือไม้ประดับ "
        "ห้ามตอบเรื่องการเมือง นโยบายรัฐบาล การกระทำผิดกฎหมาย หรือการใช้สารเคมีแบบไม่ปลอดภัย "
        f"ปัจจุบันอยู่ในช่วง{season} (พ.ศ. {be_year}) "
        f"{weather_instruction}"
        "ให้คำนึงถึงฤดูกาลนี้ในคำแนะนำ "
        "หากไม่มีข้อมูลอ้างอิงจากฐานข้อมูล ให้ตอบจากความรู้ทั่วไปเฉพาะพืชเศรษฐกิจในขอบเขต "
        "โดยไม่ต้องกล่าวว่าไม่พบข้อมูลในฐานข้อมูล เว้นแต่ผู้ใช้ถามหาแหล่งอ้างอิง "
        "หลีกเลี่ยงการอ้างว่ามาจากฐานข้อมูลหรือเอกสารอ้างอิง "
        "ถ้าคำถามถามกว้าง ๆ ให้เลือกตอบเฉพาะพืชเศรษฐกิจจากรายการขอบเขต "
        "ถ้าผู้ใช้ถามถึงพืชนอกขอบเขต ให้บอกว่ายังรองรับเฉพาะพืชเศรษฐกิจในรายการ แล้วแนะนำให้เลือกพืชในขอบเขต"
    )
    user = (
        f"คำถาม: {query}\n\n"
        "กรุณาตอบจากความรู้ทั่วไปเฉพาะพืชเศรษฐกิจในขอบเขตเท่านั้น "
        "ถ้าต้องยกตัวอย่าง ให้ใช้เฉพาะพืชในรายการขอบเขต ห้ามใส่พืชอื่น"
    )
    return system, user


# ---------------------------------------------------------------------------
# Core streaming entry point
# ---------------------------------------------------------------------------

def _build_messages(system: str, user: str, history: list[dict] | None = None) -> list[dict]:
    """Build message list with optional conversation history."""
    messages = [{"role": "system", "content": system}]
    if history:
        for turn in history[-8:]:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user})
    return messages


def _history_for_generation(
    query: str,
    history: list[dict] | None,
    query_crops: list[str],
    intent: str,
    topic: str | None,
) -> list[dict] | None:
    if not history:
        return None
    filtered: list[dict] = []
    for turn in history[-8:]:
        content = str(turn.get("content", ""))
        role = turn.get("role")
        if not content or role not in {"user", "assistant"}:
            continue
        if role == "user" and (detect_non_scope_crop(content) or is_out_of_domain_question(content) or _is_weather_question(content)):
            continue
        if role == "assistant" and any(
            marker in content
            for marker in [
                "ยังไม่รองรับคำถามเกี่ยวกับ",
                "คำถามนี้อยู่นอกขอบเขต",
                "รองรับคำถามเฉพาะพืชเศรษฐกิจในระบบ",
                "ระบบยังไม่มีพยากรณ์อากาศ",
            ]
        ):
            continue
        filtered.append(turn)
    if not filtered:
        return None
    if query_crops or is_price_question(query):
        return filtered[-2:]
    if intent in {"profit", "price"}:
        return [turn for turn in filtered[-4:] if turn.get("role") == "user"][-2:]
    if _should_carry_topic_from_history(query, query_crops):
        return filtered[-4:]
    return filtered[-2:]


def _is_weather_question(text: str) -> bool:
    t = text.lower()
    weather_terms = ["ฝน", "อากาศ", "พยากรณ์", "ฝนตก", "ฝนจะตก", "อุณหภูมิ", "แดด", "ลมแรง"]
    time_terms = ["วันนี้", "พรุ่งนี้", "วันพรุ่งนี้", "คืนนี้", "พรุ้งนี้", "สัปดาห์นี้", "พยากรณ์"]
    return any(term in t for term in weather_terms) and any(term in t for term in time_terms)


def _weather_scope_answer(location: str | None = None) -> str:
    location_text = f"ของ **{location}** " if location else ""
    return (
        "**สรุป**\n"
        f"- ตอนนี้ DrKaset ยังไม่มีพยากรณ์อากาศรายวัน{location_text}แบบเรียลไทม์ครับ\n\n"
        "**ช่วยได้ตอนนี้**\n"
        "- ผมช่วยแนะนำเรื่องการปลูก การให้น้ำ การระบายน้ำ และการรับมือฝนตามหลักเกษตรได้ครับ\n"
        "- ถ้าบอกชื่อพืชกับสภาพแปลง ผมช่วยวางแผนเผื่อฝนหรือแล้งให้ได้ครับ\n\n"
        "**ข้อควรระวัง**\n"
        "- ถ้าต้องการเช็กว่าพรุ่งนี้ฝนตกไหมจริง ๆ ควรดูจากบริการพยากรณ์อากาศโดยตรงก่อนตัดสินใจครับ"
    )


def stream_response(query: str, history: list[dict] | None = None):
    # query_crops = detect_crop_in_text(query)
    # non_scope_crop = detect_non_scope_crop(query)

    # if non_scope_crop and (_is_unsafe_chemical_request(query) or _has_price_guarantee_request(query)):
    #     yield _combined_scope_safety_guarantee_answer(non_scope_crop)
    #     return

    # if _is_illegal_agri_request(query):
    #     yield _illegal_activity_refusal()
    #     return

    # if _is_unsafe_chemical_request(query):
    #     if _has_chemical_exposure_medical_request(query):
    #         yield _combined_unsafe_medical_refusal()
    #         return
    #     yield _unsafe_chemical_refusal()
    #     return

    # if _has_chemical_exposure_medical_request(query):
    #     yield _chemical_exposure_medical_refusal()
    #     return

    # if _has_political_request(query):
    #     yield _politics_scope_answer(query, query_crops[0] if query_crops else None)
    #     return

    # guarantee_answer = _price_guarantee_safe_answer(query, query_crops[0] if query_crops else None)
    # if guarantee_answer:
    #     yield _sanitize_answer(guarantee_answer)
    #     return

    # if is_out_of_domain_question(query):
    #     yield OUT_OF_SCOPE_REPLY
    #     return

    # if _is_weather_question(query):
    #     yield _weather_scope_answer(_detect_location_text(query))
    #     return

    # if is_capability_question(query):
    #     yield _capability_answer()
    #     return

    # if any(term in query for term in ["ยังไม่เลือกพืช", "แนะนำถามต่อ", "เลือกพืช"]):
    #     yield _broad_crop_planning_answer()
    #     return

    # if non_scope_crop:
    #     # Check if query also mentions in-scope crops — give mixed-scope reply
    #     in_scope_in_query = detect_crop_in_text(query)
    #     if in_scope_in_query:
    #         yield _mixed_scope_crop_answer(non_scope_crop, in_scope_in_query, query)
    #     elif _is_unsafe_chemical_request(query) or _has_price_guarantee_request(query):
    #         yield _non_scope_with_safety_answer(non_scope_crop)
    #     else:
    #         yield (
    #             "**สรุป**\n"
    #             f"- ขออภัย ปัจจุบัน DrKaset **ยังไม่มีข้อมูลในระบบ** สำหรับ **{non_scope_crop}** ครับ\n"
    #             "- ผมขอ **แจ้งว่าไม่มีข้อมูลในระบบ** สำหรับพืชชนิดนี้ครับ\n\n"
    #             "**พืชที่รองรับ**\n"
    #             f"- {_target_crop_list()} ครับ\n\n"
    #             "**คำแนะนำ**\n"
    #             "- ลองถามเรื่องราคา ต้นทุน โรคพืช หรือการปลูกของพืชในรายการด้านบนได้เลยครับ"
    #         )
    #     return

    # history_crops = detect_crop_in_history(history)
    # effective_crops = query_crops or history_crops
    # effective_crop = query_crops[0] if query_crops else (history_crops[-1] if history_crops else None)
    # requested_topics = _detect_requested_topics(query)
    # guardrail_note = (
    #     "ถ้าผู้ใช้ขอให้ฟันธงหรือการันตีราคาในอนาคต ให้ปฏิเสธส่วนนั้นอย่างชัดเจน และให้ตอบได้เพียงแนวโน้มหรือความเสี่ยงเท่านั้น"
    #     if _has_price_guarantee_request(query)
    #     else None
    # )

    # if is_current_market_price_question(query):
    #     yield _current_market_price_scope_answer(effective_crop)
    #     return

    # if is_comparison_question_guidance(query):
    #     yield _comparison_question_guidance_answer()
    #     return

    # if "ราคาย้อนหลัง" in query and any(term in query for term in ["ใช้ตัดสินใจ", "ใช้ยังไง", "เอาไปใช้"]):
    #     yield _historical_price_usage_answer()
    #     return

    # if "bullet" in query.lower() and any(term in query for term in ["สั้น", "ตอบ"]):
    #     yield _short_bullet_ack_answer()
    #     return

    # if is_general_agriculture_help_question(query):
    #     yield _capability_answer()
    #     return

    # if (
    #     "ตาราง" in query
    #     and any(term in query for term in ["ข้อควรระวัง", "น้ำ", "โรค", "ตลาด"])
    #     and effective_crops
    # ):
    #     yield _sanitize_answer(_multi_crop_risk_table_answer(effective_crops))
    #     return

    # # Carry topic from history for short follow-up queries (e.g. "แล้วอ้อยหละ")
    # _query_topic = detect_topic(query)
    # _history_topic = (
    #     detect_topic_from_history(history)
    #     if not _query_topic and _should_carry_topic_from_history(query, query_crops)
    #     else None
    # )
    # _effective_topic_early = _query_topic or _history_topic

    # if _is_thanks_only(query):
    #     yield _thanks_answer(effective_crop)
    #     return

    # if _is_monthly_price_trend_question(query):
    #     yield _monthly_price_trend_answer(effective_crop)
    #     return

    # # --- Greeting / small talk: respond friendly, skip RAG ---
    # if is_greeting(query) and not is_agriculture_question(query):
    #     system, user = build_greeting_prompt(query)
    #     stream = ollama_client.chat(
    #         model=_model_for_response(query, intent="greeting"),
    #         messages=_build_messages(system, user, history),
    #         options={"temperature": TEMPERATURE, "num_ctx": 1024, "num_predict": 160},
    #         stream=True,
    #     )
    #     yield from _yield_sanitized_stream(stream)
    #     return

    # if is_specific_crop_question(query) and not effective_crops:
    #     yield SUPPORTED_CROP_REPLY.format(crops=_target_crop_list())
    #     return

    # if is_financial_question(query) and effective_crop and len(effective_crops) == 1 and not _is_compare_question(query, effective_crops):
    #     financial = _direct_financial_answer(query, effective_crop, [], history)
    #     if financial:
    #         yield _sanitize_answer(financial)
    #         return

    # # --- If scope detection misses, still answer through the safe general fallback.
    # # This avoids blocking benign greetings or agricultural wording variants.
    # if not is_in_scope(query):
    #     system, user = build_fallback_prompt(query)
    #     stream = ollama_client.chat(
    #         model=_model_for_response(query, intent="knowledge", requested_topics=requested_topics),
    #         messages=_build_messages(system, user, history),
    #         options={"temperature": TEMPERATURE, "num_ctx": 2048, "num_predict": 320},
    #         stream=True,
    #     )
    #     yield from _yield_sanitized_stream(stream)
    #     return

    # # --- Agriculture question: always retrieve, always respond ---
    # intent = detect_intent(query)
    # topic = detect_topic(query)
    # compare_cues = ["ระหว่าง", "ดีกว่า", "เหมาะกว่า", "เปรียบเทียบ", "ควรปลูกอะไร", "พืชไหน"]
    # if len(query_crops) >= 2 and any(term in query for term in compare_cues):
    #     intent = "compare"
    # if not topic and requested_topics:
    #     topic = requested_topics[0]
    # if not topic and _should_carry_topic_from_history(query, query_crops):
    #     topic = detect_topic_from_history(history)
    # crop = effective_crop
    # region = detect_region_from_text(query)
    # crops = effective_crops
    # llm_history = _history_for_generation(query, history, query_crops, intent, topic)
    # --- STEP 1: LLM Router ด่านหน้า ---
    guardrail_note = None
    
    # --- 1. LLM Router ด่านหน้า ---
    router_intent = get_llm_intent(query)
    print(f"🎯 [LLM Router] Detected Intent: {router_intent}")

    # --- 2. จัดการกลุ่ม Refusal & Safety (ดักจับเด็ดขาด) ---
    if router_intent == "safety_violation":
        if _is_illegal_agri_request(query):
            yield _illegal_activity_refusal()
        elif _has_chemical_exposure_medical_request(query):
            yield _chemical_exposure_medical_refusal()
        else:
            yield _unsafe_chemical_refusal()
        return

    if router_intent == "out_of_domain":
        yield OUT_OF_SCOPE_REPLY
        return

    # --- 3. จัดการพืชนอกขอบเขต (Non-scope) ---
    non_scope_crop = detect_non_scope_crop(query)
    if non_scope_crop:
        in_scope_in_query = detect_crop_in_text(query)
        if in_scope_in_query:
            yield _mixed_scope_crop_answer(non_scope_crop, in_scope_in_query, query)
        else:
            yield (
                "**สรุป**\n"
                f"- ขออภัย ปัจจุบัน DrKaset **ยังไม่มีข้อมูลในระบบ** สำหรับ **{non_scope_crop}** ครับ\n"
                "- ผมขอ **แจ้งว่าไม่มีข้อมูลในระบบ** สำหรับพืชชนิดนี้ครับ\n\n"
                "**พืชที่รองรับ**\n"
                f"- {_target_crop_list()} ครับ\n\n"
                "**คำแนะนำ**\n"
                "- ลองถามเรื่องราคา ต้นทุน โรคพืช หรือการปลูกของพืชในรายการด้านบนได้เลยครับ"
            )
        return

    if router_intent == "greeting" or is_capability_question(query):
        # ถ้าพูดขอบคุณเฉยๆ
        if _is_thanks_only(query):
            yield _thanks_answer(detect_crop_in_text(query)[0] if detect_crop_in_text(query) else None)
        # ถ้าทักทาย หรือถามความสามารถ ให้แนะนำตัวเต็มรูปแบบเสมอ
        else:
            yield _capability_answer()
        return
    
    # --- 4. จัดการกลุ่ม Greetings & Capabilities ---
    # if router_intent == "greeting" or is_capability_question(query):
    #     if is_capability_question(query) or is_general_agriculture_help_question(query):
    #         yield _capability_answer()
    #     elif _is_thanks_only(query):
    #         yield _thanks_answer(detect_crop_in_text(query)[0] if detect_crop_in_text(query) else None)
    #     else:
    #         system, user = build_greeting_prompt(query)
    #         stream = ollama_client.chat(
    #             model=_model_for_response(query, intent="greeting"),
    #             messages=_build_messages(system, user, history),
    #             options={"temperature": TEMPERATURE, "num_ctx": 1024, "num_predict": 160},
    #             stream=True,
    #         )
    #         yield from _yield_sanitized_stream(stream)
    #     return

    # --- 5. ตรวจสอบเงื่อนไขเฉพาะ (Weather, Planning) ---
    if _is_weather_question(query):
        yield _weather_scope_answer(_detect_location_text(query))
        return

    if any(term in query for term in ["ยังไม่เลือกพืช", "แนะนำถามต่อ", "เลือกพืช"]):
        yield _broad_crop_planning_answer()
        return

    # --- 6. เตรียมข้อมูลพืชและ Topics เพื่อเข้า RAG ---
    query_crops = detect_crop_in_text(query)
    history_crops = detect_crop_in_history(history)
    effective_crops = query_crops or history_crops
    effective_crop = query_crops[0] if query_crops else (history_crops[-1] if history_crops else None)
    requested_topics = _detect_requested_topics(query)
    
    # กำหนดค่า Guardrail (ถ้าเป็นเรื่องเงิน หรือถูกดักด้วย Router)
    guardrail_note = (
        "ถ้าผู้ใช้ขอให้ฟันธงหรือการันตีราคาในอนาคต ให้ปฏิเสธส่วนนั้นอย่างชัดเจน และให้ตอบได้เพียงแนวโน้มหรือความเสี่ยงเท่านั้น"
        if _has_price_guarantee_request(query) or router_intent == "financial"
        else None
    )

    if is_specific_crop_question(query) and not effective_crops:
        yield SUPPORTED_CROP_REPLY.format(crops=_target_crop_list())
        return

    if is_current_market_price_question(query):
        yield _current_market_price_scope_answer(effective_crop)
        return

    if is_comparison_question_guidance(query):
        yield _comparison_question_guidance_answer()
        return

    if "ราคาย้อนหลัง" in query and any(term in query for term in ["ใช้ตัดสินใจ", "ใช้ยังไง", "เอาไปใช้"]):
        yield _historical_price_usage_answer()
        return

    if "bullet" in query.lower() and any(term in query for term in ["สั้น", "ตอบ"]):
        yield _short_bullet_ack_answer()
        return

    if ("ตาราง" in query and any(term in query for term in ["ข้อควรระวัง", "น้ำ", "โรค", "ตลาด"]) and effective_crops):
        yield _sanitize_answer(_multi_crop_risk_table_answer(effective_crops))
        return

    if _is_monthly_price_trend_question(query):
        yield _monthly_price_trend_answer(effective_crop)
        return

    # --- 7. ผสาน Intent จาก Router เข้ากับระบบเก่า ---
    if router_intent == "financial":
        intent = "profit" if is_financial_question(query) else "price"
        
        guarantee_answer = _price_guarantee_safe_answer(query, effective_crop)
        if guarantee_answer:
            yield _sanitize_answer(guarantee_answer)
            return
            
    elif router_intent == "compare":
        intent = "compare"
    else:
        intent = "knowledge"

    topic = detect_topic(query)
    compare_cues = ["ระหว่าง", "ดีกว่า", "เหมาะกว่า", "เปรียบเทียบ", "ควรปลูกอะไร", "พืชไหน"]
    if len(query_crops) >= 2 and any(term in query for term in compare_cues):
        intent = "compare"

    if not topic and requested_topics:
        topic = requested_topics[0]
    if not topic and _should_carry_topic_from_history(query, query_crops):
        topic = detect_topic_from_history(history)

    crop = effective_crop
    region = detect_region_from_text(query)
    crops = effective_crops
    llm_history = _history_for_generation(query, history, query_crops, intent, topic)

    if intent == "profit" and not crop:
        yield (
            "**สรุป**\n"
            "- ผมยังไม่รู้ว่าต้องคำนวณให้พืชชนิดไหนครับ\n\n"
            "**ขอข้อมูลเพิ่ม**\n"
            "- ระบุชื่อพืช เช่น อ้อย ข้าว มันสำปะหลัง หรือข้าวโพดครับ\n"
            "- ถ้าต้องการคำนวณรายได้ ให้บอกจำนวนไร่ ผลผลิตต่อไร่ และราคาขายด้วยครับ\n\n"
            "**ตัวอย่างคำถาม**\n"
            "- ปลูกอ้อย 40 ไร่ ถ้าได้ 29,000 บาทต่อไร่ รวมเป็นเงินเท่าไรครับ"
        )
        return

    k = TOP_K_COMPARE if intent == "compare" else TOP_K
    retrieval_source_types = ["pdf"] if intent == "knowledge" or (intent == "compare" and not is_financial_question(query)) else None

    # ดึง docs จาก RAG ก่อนเสมอ
    retrieval_query = query if query_crops else f"{query} {' '.join(history_crops)}".strip()
    if intent == "compare" and len(effective_crops) >= 2:
        docs = []
        seen_doc_keys: set[tuple[str, str]] = set()
        per_crop_k = 1
        compare_topics = requested_topics[:2] or ([topic] if topic else [None])
        for compare_crop in effective_crops:
            for compare_topic in compare_topics:
                for doc in retrieve(retrieval_query, crop=compare_crop, region=region, topic=compare_topic, k=per_crop_k, source_types=retrieval_source_types):
                    key = (str(doc.get("metadata", {}).get("file_name", "")), doc.get("content", "")[:80])
                    if key in seen_doc_keys:
                        continue
                    seen_doc_keys.add(key)
                    docs.append(doc)
                    if len(docs) >= k:
                        break
                if len(docs) >= k:
                    break
            if len(docs) >= k:
                break
    else:
        docs = []
        if effective_crops:
            seen_doc_keys: set[tuple[str, str]] = set()
            topic_candidates = requested_topics[:2] or ([topic] if topic else [None])
            per_topic_k = 1
            for topic_candidate in topic_candidates:
                for doc in retrieve(retrieval_query, crop=crop, region=region, topic=topic_candidate, k=per_topic_k, source_types=retrieval_source_types):
                    key = (str(doc.get("metadata", {}).get("file_name", "")), doc.get("content", "")[:80])
                    if key in seen_doc_keys:
                        continue
                    seen_doc_keys.add(key)
                    docs.append(doc)
                    if len(docs) >= min(2, max(1, len(topic_candidates))):
                        break
                if len(docs) >= min(2, max(1, len(topic_candidates))):
                    break

    docs = _trim_docs_for_prompt(docs, intent, topic, requested_topics)

    financial_confident = _financial_rag_confident(query, crop, topic, docs) if topic in {"price", "profit"} or intent in {"price", "profit"} else False

    if topic == "price" and not financial_confident:
        structured_price = _structured_price_block(query, crop)
        if structured_price:
            yield _sanitize_answer(structured_price)
            return
        historical_price = _historical_price_answer(query, effective_crops)
        if historical_price:
            yield _sanitize_answer(historical_price)
            return

    if (
        intent in {"profit", "price"}
        and crop
        and not financial_confident
        and not _has_direct_financial_calculation(query, history)
        and not (intent == "knowledge")
    ):
        if topic == "price":
            yield (
                "**สรุป**\n"
                f"- ผมหาข้อมูลราคา{crop}จากเอกสารที่ดึงมาได้ยังไม่ชัดพอครับ\n\n"
                "**คำแนะนำ**\n"
                "- ลองระบุปี จังหวัด หรือคำว่า ราคาย้อนหลัง/ราคาเฉลี่ย เพิ่มครับ\n"
                "- ถ้าต้องการราคาย้อนหลัง ผมจะพยายามดึงจากข้อมูลย้อนหลังที่มีในระบบให้ครับ"
            )
            return
        fallback_answer = _financial_missing_answer(query, crop, history)
        fallback_answer = _append_structured_financial_notes(fallback_answer, query, [crop], requested_topics)
        if guardrail_note:
            fallback_answer += (
                "\n\n**ข้อควรระวัง**\n"
                "- ผมไม่สามารถฟันธงราคาขายในอนาคตหรือรับประกันผลตอบแทนได้ครับ"
            )
        yield _sanitize_answer(fallback_answer)
        return

    if intent == "profit" and crop and _has_cost_per_kg_request(query) and not _docs_have_cost_per_kg_signal(docs):
        answer = (
            "**สรุป**\n"
            f"- ตอนนี้เอกสารที่ดึงได้ยังไม่พบตัวเลข **ต้นทุนต่อกิโลกรัม** ของ{crop}ที่ชัดพอครับ\n\n"
            "**คำแนะนำ**\n"
            "- ถ้ามีข้อมูลต้นทุนต่อไร่และผลผลิตต่อไร่ ผมจะช่วยคำนวณต้นทุนต่อกิโลกรัมให้ได้ครับ\n"
            "- ถ้าต้องการดูแนวโน้มราคา ผมช่วยสรุปได้ แต่จะไม่ฟันธงราคาปีหน้าครับ\n\n"
            "**ข้อควรระวัง**\n"
            "- การตัดสินใจกู้เงินหรือลงทุนเพิ่มไม่ควรอิงการคาดเดาราคาในอนาคตเพียงอย่างเดียวครับ"
        )
        yield _sanitize_answer(answer)
        return

    if intent == "compare" and len(crops) >= 2:
        structured_compare = _compare_structured_financial_answer(query, list(crops), docs)
        compare_cues = ["ดิน", "ฝน", "แล้ง", "น้ำ", "เหมาะ", "ปลูกอะไร", "ดีกว่า", "เสี่ยง", "เปรียบเทียบ"]
        if structured_compare and (is_financial_question(query) or any(term in query for term in compare_cues)):
            yield _sanitize_answer(structured_compare)
            return

    # compare: ถ้ามี docs ให้ LLM ตอบจากเอกสาร ถ้าไม่มีค่อย fallback เป็น template
    if intent == "compare" and not is_financial_question(query):
        compare_crops = list(crops)
        if len(compare_crops) < 2 and history_crops:
            for hcrop in reversed(history_crops):
                if hcrop not in compare_crops:
                    compare_crops.insert(0, hcrop)
                    break
        if len(compare_crops) >= 2 and not docs:
            yield _compare_knowledge_answer(compare_crops, topic)
            return
        # ถ้ามี docs ให้ไหลต่อไปใช้ LLM ด้านล่าง
        crops = compare_crops
    elif intent == "compare" and is_financial_question(query) and not docs:
        yield _compare_financial_missing_answer(crops)
        return

    if intent == "compare" and is_financial_question(query) and docs:
        structured_compare = _compare_structured_financial_answer(query, list(crops), docs)
        if structured_compare:
            yield _sanitize_answer(structured_compare)
            return

    direct_answer = _direct_answer(query, crop, topic, docs, history)
    if direct_answer:
        answer = _sanitize_answer(direct_answer)
        if any(topic_name in requested_topics for topic_name in {"water"}) or _requests_historical_weather(query):
            weather_block = _structured_weather_block(region)
            if weather_block:
                answer = f"{answer.rstrip()}\n\n{weather_block}".strip()
        if intent == "knowledge" and any(topic_name in requested_topics for topic_name in {"price", "profit"}):
            answer = _append_structured_financial_notes(answer, query, effective_crops, requested_topics)
        if guardrail_note:
            answer += (
                "\n\n**ข้อควรระวัง**\n"
                "- ผมไม่สามารถฟันธงราคาขายในอนาคตหรือรับประกันผลตอบแทนได้ครับ"
            )
        yield answer
        return

    if not docs and crop and _needs_strict_grounding(requested_topics, topic):
        topic_text = ", ".join(requested_topics or ([topic] if topic else []))
        answer = _sanitize_answer(
            "**สรุป**\n"
            f"- ตอนนี้ข้อมูลอ้างอิงที่ดึงได้ยังไม่พอสำหรับตอบเรื่อง {topic_text} ของ{crop}ให้ครบถ้วนครับ\n\n"
            "**คำแนะนำ**\n"
            "- ลองระบุจังหวัด ช่วงเวลา ปี หรืออาการที่เห็นให้ละเอียดขึ้นครับ\n"
            "- ถ้ามีข้อมูลต้นทุน ราคาย้อนหลัง หรือรายละเอียดแปลงจริง ผมจะช่วยสรุปให้ตรงขึ้นครับ\n\n"
            "**ข้อควรระวัง**\n"
            "- ผมยังไม่ควรเดาข้อมูลหลายมิติแทนเอกสารอ้างอิง เพราะเสี่ยงทำให้คำตอบคลาดเคลื่อนครับ"
        )
        if any(topic_name in requested_topics for topic_name in {"water"}) or _requests_historical_weather(query):
            weather_block = _structured_weather_block(region)
            if weather_block:
                answer = f"{answer.rstrip()}\n\n{weather_block}".strip()
        answer = _append_structured_financial_notes(answer, query, effective_crops, requested_topics)
        yield answer
        return

    if docs and crop and _needs_strict_grounding(requested_topics, topic) and not _docs_cover_requested_topics(docs, requested_topics, query):
        topic_text = ", ".join(requested_topics or ([topic] if topic else []))
        answer = _sanitize_answer(
            "**สรุป**\n"
            f"- เอกสารที่ดึงได้มีข้อมูลของ{crop}บางส่วน แต่ยังครอบคลุมเรื่อง {topic_text} ไม่ครบครับ\n\n"
            "**คำแนะนำ**\n"
            "- ตอนนี้ผมตอบได้แค่บางมิติจากเอกสารที่มี จึงยังไม่ควรสรุปแทนทุกประเด็นครับ\n"
            "- ลองระบุช่วงเวลา ปี จังหวัด หรืออาการ/ตัวเลขที่ต้องการให้ชัดขึ้น แล้วผมจะดึงข้อมูลให้ตรงขึ้นครับ\n\n"
            "**ข้อควรระวัง**\n"
            "- ถ้าฝืนตอบให้ครบทั้งที่หลักฐานไม่พอ มีโอกาสปนข้อมูลคนละประเด็นหรือคนละเอกสารได้ครับ"
        )
        if any(topic_name in requested_topics for topic_name in {"water"}) or _requests_historical_weather(query):
            weather_block = _structured_weather_block(region)
            if weather_block:
                answer = f"{answer.rstrip()}\n\n{weather_block}".strip()
        answer = _append_structured_financial_notes(answer, query, effective_crops, requested_topics)
        yield answer
        return

    if docs and crop and _requests_historical_weather(query) and not _docs_have_historical_weather_signal(docs):
        answer = _sanitize_answer(
            "**สรุป**\n"
            f"- ตอนนี้เอกสารที่ดึงได้ยังไม่พบข้อมูลอากาศย้อนหลังของ{crop}ตามช่วงเวลาที่ถามแบบชัดเจนครับ\n\n"
            "**คำแนะนำ**\n"
            "- ผมช่วยสรุปเรื่องเตรียมดินหรือการปลูกจากเอกสารที่มีได้ แต่ยังไม่ควรอ้างว่าเป็นอากาศย้อนหลัง 2-3 ปีครับ\n"
            "- ถ้ามีชุดข้อมูลอากาศย้อนหลังแยกต่างหาก ผมสามารถเชื่อมเข้ามาใช้ตอบส่วนนี้ได้ตรงขึ้นครับ\n\n"
            "**ข้อควรระวัง**\n"
            "- การใช้สภาพอากาศทั่วไปของพื้นที่แทนข้อมูลย้อนหลังจริง อาจทำให้ประเมินความเสี่ยงคลาดเคลื่อนได้ครับ"
        )
        weather_block = _structured_weather_block(region)
        if weather_block:
            answer = f"{answer.rstrip()}\n\n{weather_block}".strip()
        answer = _append_structured_financial_notes(answer, query, effective_crops, requested_topics)
        yield answer
        return

    if not docs:
        system, user = build_fallback_prompt(query)
    elif intent == "compare":
        system, user = build_compare_prompt(query, docs, crops, requested_topics=requested_topics, guardrail_note=guardrail_note)
    elif intent == "profit":
        system, user = build_profit_prompt(query, docs, crop, requested_topics=requested_topics, guardrail_note=guardrail_note)
    else:
        # สร้าง history_context สำหรับช่วยให้ LLM เข้าใจบริบทก่อนหน้า
        history_context: str | None = None
        if history_crops and not query_crops:
            history_context = f"ผู้ใช้กำลังคุยเรื่อง {', '.join(history_crops)}"
        carry_region_from_history = bool(history) and not region and not query_crops and _should_carry_topic_from_history(query, query_crops)
        region_from_history = detect_region_from_text(
            " ".join(
                m.get("content", "")
                for m in (history or [])[-6:]
                if m.get("role") == "user"
                and not detect_non_scope_crop(str(m.get("content", "")))
                and not is_out_of_domain_question(str(m.get("content", "")))
                and not _is_weather_question(str(m.get("content", "")))
            )
        ) if carry_region_from_history else None
        effective_region = region or region_from_history
        if effective_region and not history_context:
            history_context = f"ผู้ใช้อยู่ในพื้นที่ภาค{effective_region}"
        elif effective_region and history_context:
            history_context += f" พื้นที่ภาค{effective_region}"
        system, user = build_knowledge_prompt(
            query,
            docs,
            topic=topic,
            crop=crop,
            history_context=history_context,
            requested_topics=requested_topics,
            guardrail_note=guardrail_note,
        )

    stream = ollama_client.chat(
        model=_model_for_response(query, intent=intent, topic=topic, requested_topics=requested_topics),
        messages=_build_messages(system, user, llm_history),
        options={
            "temperature": TEMPERATURE,
            "num_ctx": _num_ctx_for_response(intent, topic, requested_topics),
            "num_predict": _num_predict_for_response(intent, topic),
        },
        stream=True,
    )

    answers = list(_yield_sanitized_stream(stream))
    if not answers:
        return
    answer = answers[-1]
    if intent == "knowledge":
        if any(topic_name in requested_topics for topic_name in {"water"}) or _requests_historical_weather(query):
            weather_block = _structured_weather_block(region)
            if weather_block:
                answer = f"{answer.rstrip()}\n\n{weather_block}".strip()
        answer = _append_structured_financial_notes(answer, query, effective_crops, requested_topics)
    yield answer


def get_intent(query: str) -> str:
    return detect_intent(query)
