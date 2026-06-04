from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import ollama

from config import settings
from database import get_db
from rag.retriever import get_store

router = APIRouter(prefix="/health", tags=["health"])
ollama_client = ollama.Client(host=settings.OLLAMA_HOST)


@router.get("")
def health_check(db: Session = Depends(get_db)):
    # DB
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    # Ollama
    try:
        ollama_client.list()
        ollama_status = "ok"
    except Exception as e:
        ollama_status = f"error: {e}"

    # FAISS
    faiss_status = "loaded" if get_store() is not None else "not loaded"

    return {"db": db_status, "ollama": ollama_status, "faiss": faiss_status}

