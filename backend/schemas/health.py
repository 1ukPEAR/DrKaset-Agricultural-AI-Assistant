from pydantic import BaseModel


class HealthResponse(BaseModel):
    db: str
    ollama: str
    faiss: str

