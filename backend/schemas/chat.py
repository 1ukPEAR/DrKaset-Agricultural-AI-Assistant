from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[int] = None


class ChatResponse(BaseModel):
    session_id: int
    message_id: int
    intent: Optional[str] = None


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    intent: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SessionOut(BaseModel):
    id: int
    title: Optional[str]
    created_at: datetime
    messages: list[MessageOut] = []

    class Config:
        from_attributes = True

