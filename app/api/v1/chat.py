from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_processor import ChatProcessor

router = APIRouter()

@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    processor = ChatProcessor(db, current_user.id)
    response_text, extracted = await processor.process_message(request.message)
    return ChatResponse(response=response_text, extracted_metrics=extracted)
