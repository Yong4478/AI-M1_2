"""(보너스) GPT Function Calling 도구 정의와 실행.

GPT는 질문에 답하는 데 시스템 프롬프트의 요약만으로 부족하다고 판단하면 아래 도구를 호출한다.
  - 요약에 없는 '특정 기간'의 값이 필요 → query_data_range
  - '가장 더운/추운 날 TOP N'처럼 순위가 필요 → find_extreme_days
  - 월별·요일별·변동성 같은 확장 통계가 필요 → get_statistics
  - 최신 요약을 다시 확인 → get_data_summary
  - 예전 대화 주제를 물어봄 → list_recent_conversations
"""

from __future__ import annotations

import json
from typing import Any, Callable

from . import conversation_service, data_service

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_data_summary",
            "description": "저장된 시계열 데이터의 최신 요약(기간, 개수, 평균/최대/최소, 최근 추세, 월별 평균)을 가져온다.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_data_range",
            "description": "특정 기간(시작일~종료일)의 일별 기록과 그 기간의 통계를 조회한다. "
                           "'이번 주', '지난달', '10월 1일~15일'처럼 요약에 없는 구체적 기간을 물을 때 사용한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "시작일 YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "종료일 YYYY-MM-DD"},
                },
                "required": ["start_date", "end_date"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_extreme_days",
            "description": "값이 가장 높은(max) 또는 가장 낮은(min) 날짜 상위 N개를 찾는다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["max", "min"]},
                    "n": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["kind", "n"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_statistics",
            "description": "확장 통계(전일 대비 변화량 변동성, 최대 상승/하락일, 요일별 평균, 전체 월별 통계)를 가져온다.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_conversations",
            "description": "최근 저장된 대화 목록(제목, 메시지 수, 마지막 메시지)을 조회한다. 사용자가 예전 대화를 물을 때 사용한다.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}},
                "required": ["limit"],
                "additionalProperties": False,
            },
        },
    },
]


def _summary(_: dict) -> Any:
    return data_service.get_summary()


def _range(args: dict) -> Any:
    return data_service.range_report(args.get("start_date"), args.get("end_date"))


def _extreme(args: dict) -> Any:
    kind = args.get("kind") if args.get("kind") in ("max", "min") else "max"
    n = max(1, min(int(args.get("n", 5)), 10))
    return data_service.extremes(kind, n)


def _stats(_: dict) -> Any:
    st = data_service.get_statistics()
    st.pop("series", None)  # 일별 시계열 전체는 토큰 낭비라 제외
    return st


def _convs(args: dict) -> Any:
    return conversation_service.list_conversations(max(1, min(int(args.get("limit", 5)), 20)))


HANDLERS: dict[str, Callable[[dict], Any]] = {
    "get_data_summary": _summary,
    "query_data_range": _range,
    "find_extreme_days": _extreme,
    "get_statistics": _stats,
    "list_recent_conversations": _convs,
}


def execute(name: str, raw_arguments: str | None) -> tuple[dict[str, Any], str]:
    """도구를 실행하고 (파싱된 인자, GPT에 돌려줄 JSON 문자열)을 반환한다. 실패해도 예외 대신 오류 JSON을 돌려준다."""
    try:
        args = json.loads(raw_arguments or "{}")
        if not isinstance(args, dict):
            args = {}
    except json.JSONDecodeError:
        args = {}
    handler = HANDLERS.get(name)
    if handler is None:
        return args, json.dumps({"error": f"알 수 없는 도구: {name}"}, ensure_ascii=False)
    try:
        result = handler(args)
    except Exception as e:  # 도구 실패를 GPT에 알려 다른 방법으로 답하게 한다
        result = {"error": str(e)}
    return args, json.dumps(result, ensure_ascii=False, default=str)
