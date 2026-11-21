"""Pydantic 요청/응답 스키마.

요청 데이터를 라우터에 들어오기 전에 검증해, 잘못된 값이 DB나 GPT 프롬프트로 흘러가지 않게 한다.
검증에 실패하면 FastAPI가 자동으로 422 응답과 어떤 필드가 왜 틀렸는지를 돌려준다.
"""

from __future__ import annotations

import math
from datetime import date as Date
from datetime import timedelta
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ─────────────────────────────────────────────
# 데이터 (date, value, memo)
# ─────────────────────────────────────────────
VALUE_MIN, VALUE_MAX = -1_000_000_000, 1_000_000_000


def _check_value(v: float) -> float:
    if not math.isfinite(v):
        raise ValueError("value는 유한한 숫자여야 합니다 (NaN/Infinity 불가)")
    if not VALUE_MIN <= v <= VALUE_MAX:
        raise ValueError("value가 허용 범위를 벗어났습니다")
    return round(v, 4)


class DataCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True,
                              json_schema_extra={"example": {"date": "2026-11-01", "value": 9.8, "memo": "맑음, 일교차 큼"}})

    date: Date = Field(..., description="날짜 (YYYY-MM-DD)")
    value: float = Field(..., description="값 (이 프로젝트에서는 일평균 기온 ℃)")
    memo: str = Field("", max_length=200, description="메모 (최대 200자)")

    @field_validator("value")
    @classmethod
    def validate_value(cls, v: float) -> float:
        return _check_value(v)

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Date) -> Date:
        if v.year < 1900 or v > Date.today() + timedelta(days=366):
            raise ValueError("날짜는 1900년 이후, 오늘부터 1년 이내여야 합니다")
        return v


class DataUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True,
                              json_schema_extra={"example": {"value": 10.2, "memo": "관측값 보정"}})

    date: Optional[Date] = None
    value: Optional[float] = None
    memo: Optional[str] = Field(None, max_length=200)

    @field_validator("value")
    @classmethod
    def validate_value(cls, v: Optional[float]) -> Optional[float]:
        return None if v is None else _check_value(v)

    @model_validator(mode="after")
    def at_least_one(self) -> "DataUpdate":
        if self.date is None and self.value is None and self.memo is None:
            raise ValueError("date, value, memo 중 최소 1개는 입력해야 합니다")
        return self


class DataItem(BaseModel):
    id: str
    date: str
    value: float
    memo: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class Extreme(BaseModel):
    value: float
    date: str


class SummaryMetrics(BaseModel):
    average: float
    median: float
    max: Extreme
    min: Extreme
    std: float
    total: float
    latest: Extreme


class TrendDetail(BaseModel):
    direction: Literal["상승", "하락", "유지", "판단 불가"]
    window_days: int
    recent_average: Optional[float] = None
    previous_average: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None


class MonthlyStat(BaseModel):
    month: str
    count: int
    average: float
    max: float
    min: float


class SummaryResponse(BaseModel):
    title: str
    unit: str
    period: str
    start: Optional[str] = None
    end: Optional[str] = None
    count: int
    metrics: Optional[SummaryMetrics] = None
    trend: str
    trend_detail: TrendDetail
    monthly: list[MonthlyStat] = []
    generated_at: str


# ─────────────────────────────────────────────
# 대화 기록
# ─────────────────────────────────────────────
class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)
    timestamp: Optional[str] = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list, description="AI가 호출한 도구 기록 (보너스)")


class ConversationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, json_schema_extra={"example": {
        "title": "11월 기온 질문",
        "messages": [{"role": "user", "content": "이번 달 기온 어때?"},
                     {"role": "assistant", "content": "이번 달 평균은 8.1℃로 ..."}]}})

    title: Optional[str] = Field(None, max_length=100)
    messages: list[Message] = Field(..., min_length=1, max_length=200)


class ConversationSummary(BaseModel):
    """목록 조회용: messages는 포함하지 않는다 (전체 메시지는 GET /api/conversations/{id})"""
    id: str
    title: str
    message_count: int
    last_message: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ConversationDetail(ConversationSummary):
    messages: list[Message]


# ─────────────────────────────────────────────
# 채팅
# ─────────────────────────────────────────────
class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True,
                              json_schema_extra={"example": {"message": "최근 일주일 기온 추세가 어때?", "conversation_id": None}})

    message: str = Field(..., min_length=1, max_length=1000, description="사용자 질문 (최대 1000자)")
    conversation_id: Optional[str] = Field(None, max_length=128, description="이어서 대화할 경우 대화 ID")


class ToolCallLog(BaseModel):
    name: str
    arguments: dict[str, Any] = {}


class ChatResponse(BaseModel):
    reply: str
    conversation_id: Optional[str] = None
    saved: bool
    model: str
    summary_used: dict[str, Any]
    tool_calls: list[ToolCallLog] = []


class MessageResponse(BaseModel):
    message: str
    id: Optional[str] = None
