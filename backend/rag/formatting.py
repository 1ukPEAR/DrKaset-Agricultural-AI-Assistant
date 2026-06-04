import re


def normalize_markdown_answer(text: str) -> str:
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


def sanitize_answer(text: str, chinese_re: re.Pattern[str], thai_sentence_split_re: re.Pattern[str]) -> str:
    text = chinese_re.sub("", text)
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

    text = normalize_markdown_answer(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = re.sub(r"(\*\*สรุป\*\*\s*\n(?:- .+\n?)+)\1+", r"\1", text, flags=re.MULTILINE)

    if any(marker in text for marker in ["\n-", "\n1.", "\n**", "\n|"]):
        text = re.sub(r"(ครับ[\s.。]*){2,}$", "ครับ", text).strip()
        return text

    sentences = [part.strip() for part in thai_sentence_split_re.split(text) if part.strip()]
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
