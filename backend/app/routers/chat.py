"""AI 챗봇 API (컨텍스트 주입 + 자동 저장)"""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from ..schemas import ChatRequest, ChatResponse
from ..services import chat_service

router = APIRouter(prefix="/api/chat", tags=["AI 채팅"])


@router.post("", response_model=ChatResponse, summary="AI 대화")
def chat(payload: ChatRequest):
    """
    1. 데이터 요약 조회 (`/api/data/summary`와 같은 로직)
    2. 요약을 시스템 프롬프트에 삽입
    3. GPT API 호출 (필요 시 도구 호출)
    4. 대화를 `conversations`에 자동 저장 — `conversation_id`를 보내면 그 대화에 이어서 저장
    """
    return chat_service.chat(payload.message, payload.conversation_id)


@router.get("/system-prompt", response_class=PlainTextResponse, summary="현재 시스템 프롬프트 미리보기")
def system_prompt():
    """요약이 실제로 어떻게 프롬프트에 주입되는지 확인용."""
    return chat_service.preview_prompt()
