"""대화 기록 API

불러오기 방식: (A) 목록(GET /api/conversations)에는 messages를 포함하지 않고,
특정 대화의 전체 messages는 GET /api/conversations/{id}로 조회한다.
"""

from fastapi import APIRouter, Path, Query

from ..schemas import ConversationCreate, ConversationDetail, ConversationSummary, MessageResponse
from ..services import conversation_service

router = APIRouter(prefix="/api/conversations", tags=["대화 기록"])


@router.post("", response_model=ConversationDetail, status_code=201, summary="대화 저장")
def create_conversation(payload: ConversationCreate):
    """메시지 목록을 새 대화로 저장한다. (채팅 API는 이 과정을 자동으로 수행한다)"""
    return conversation_service.create_conversation([m.model_dump() for m in payload.messages], payload.title)


@router.get("", response_model=list[ConversationSummary], summary="대화 목록 조회 (messages 미포함)")
def list_conversations(limit: int = Query(50, ge=1, le=100)):
    """최근 수정순. 응답에는 messages가 없고 message_count, last_message만 포함된다."""
    return conversation_service.list_conversations(limit)


@router.get("/{conv_id}", response_model=ConversationDetail, summary="특정 대화 불러오기 (전체 messages)")
def get_conversation(conv_id: str = Path(..., min_length=1, max_length=128, description="대화 문서 ID")):
    return conversation_service.get_conversation(conv_id)


@router.delete("/{conv_id}", response_model=MessageResponse, summary="대화 삭제")
def delete_conversation(conv_id: str = Path(..., min_length=1, max_length=128, description="대화 문서 ID")):
    conversation_service.delete_conversation(conv_id)
    return {"message": "삭제되었습니다.", "id": conv_id}
