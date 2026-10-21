from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user_world
from app.models.world import World
from app.schemas.chat import ChatQueryRequest, ChatQueryResponse
from app.services.chat_service import ChatService
from app.services.profile_service import load_profile

router = APIRouter()

@router.post("/{world_id}/chat", response_model=ChatQueryResponse)
def chat_with_world(
    world_id: str,
    query_in: ChatQueryRequest,
    world: World = Depends(get_current_user_world),
    db: Session = Depends(get_db)
):
    if not query_in.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chat message cannot be empty."
        )

    chat_service = ChatService(db)
    response = chat_service.query(
        world_id=world.id,
        message=query_in.message.strip(),
        history=query_in.history,
        entity_focus=query_in.entity_focus,
        timeline_event_focus=query_in.timeline_event_focus,
        reply_length=load_profile(world.user_id)["preferences"]["chat_reply_length"]
    )
    return response
