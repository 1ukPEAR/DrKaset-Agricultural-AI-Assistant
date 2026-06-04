import json
import ollama
from config import settings
from rag.constants import ROUTER_SYSTEM_PROMPT

ollama_client = ollama.Client(host=settings.OLLAMA_HOST)

def get_llm_intent(query: str) -> str:
    """ส่งคำถามให้ LLM แยกหมวดหมู่ความต้องการ"""
    try:
        response = ollama_client.chat(
            model=settings.OLLAMA_FAST_MODEL, 
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": f"ประโยคจากผู้ใช้: '{query}'"}
            ],
            format="json",
            options={
                "temperature": 0.0,
                "num_predict": 20
            }
        )
        result_text = response["message"]["content"]
        parsed_json = json.loads(result_text)
        return parsed_json.get("intent", "agriculture_knowledge")
    except Exception as e:
        print(f"[Router Error] {e}")
        return "agriculture_knowledge" # Fallback ถ้า Router พัง