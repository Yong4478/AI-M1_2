"""AI 채팅: 데이터 요약을 시스템 프롬프트에 주입(컨텍스트 주입)하고 GPT를 호출한 뒤 대화를 자동 저장한다.

동작 흐름 (POST /api/chat)
  1. 데이터 요약 조회   — GET /api/data/summary 와 같은 함수(data_service.get_summary) 사용
  2. 시스템 프롬프트에 요약 삽입
  3. GPT API 호출      — 필요하면 GPT가 도구(Function Calling)를 호출해 추가 데이터를 조회 (보너스)
  4. 대화를 conversations 컬렉션에 자동 저장
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from ..config import get_settings
from ..errors import NotFoundError, RateLimitError, ServiceUnavailableError, UpstreamError
from . import conversation_service, data_service, tools

log = logging.getLogger(__name__)
MAX_TOOL_ROUNDS = 4

_client = None


def get_client():
    """OpenAI 클라이언트 (키가 없으면 명확한 안내와 함께 503)"""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise ServiceUnavailableError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
        from openai import OpenAI
        _client = OpenAI(api_key=settings.openai_api_key, timeout=60.0, max_retries=1)
    return _client


def set_client(client) -> None:
    """테스트용 클라이언트 주입"""
    global _client
    _client = client


def _fmt_metrics(summary: dict[str, Any]) -> str:
    m, u = summary.get("metrics"), summary["unit"]
    if not m:
        return "없음"
    return (f"평균 {m['average']}{u}, 중앙값 {m['median']}{u}, "
            f"최고 {m['max']['value']}{u}({m['max']['date']}), 최저 {m['min']['value']}{u}({m['min']['date']}), "
            f"표준편차 {m['std']}{u}, 가장 최근 값 {m['latest']['value']}{u}({m['latest']['date']})")


def build_system_prompt(summary: dict[str, Any], tools_enabled: bool) -> str:
    """컨텍스트 주입: 요약 정보를 텍스트로 만들어 시스템 프롬프트에 넣는다."""
    u = summary["unit"]
    monthly = "\n".join(f"   - {m['month']}: 평균 {m['average']}{u} (최고 {m['max']}{u}, 최저 {m['min']}{u}, {m['count']}일)"
                        for m in summary.get("monthly", [])) or "   - 없음"
    tool_rule = ("- 요약에 없는 특정 날짜·기간의 값이나 순위가 필요하면 제공된 도구를 호출해 확인한 뒤 답하세요.\n"
                 if tools_enabled else
                 "- 요약에 없는 세부 값은 추측하지 말고, 데이터 관리 화면에서 확인하도록 안내하세요.\n")
    return f"""당신은 사용자의 데이터를 이해하고 답하는 '데이터 분석 비서'입니다.
오늘 날짜: {date.today().isoformat()}

[사용자 데이터 요약]
- 데이터 종류: {summary['title']} (단위: {u})
- 데이터 기간: {summary['period']}
- 총 레코드: {summary['count']}개
- 주요 지표: {_fmt_metrics(summary)}
- 최근 트렌드: {summary['trend']}
- 월별 평균 (최근 {len(summary.get('monthly', []))}개월):
{monthly}

[답변 규칙]
- 위 데이터를 근거로 한국어로 친근하고 간결하게(3~6문장) 답하세요.
- 수치를 말할 때는 단위({u})와 날짜/기간을 함께 밝히세요.
{tool_rule}- 데이터 기간 밖의 내용이나 데이터로 알 수 없는 내용(예: 내일 날씨 예보)은 추측하지 말고 모른다고 말하세요.
- 데이터와 관계없는 일반 질문에는 짧게 답한 뒤 데이터와 연결할 수 있는 질문을 제안하세요."""


def _summary_brief(summary: dict[str, Any]) -> dict[str, Any]:
    return {k: summary.get(k) for k in ("title", "period", "count", "metrics", "trend")}


def _call_openai(messages: list[dict[str, Any]], use_tools: bool):
    import openai
    settings = get_settings()
    kwargs: dict[str, Any] = {"model": settings.openai_model, "messages": messages,
                              "max_completion_tokens": settings.openai_max_tokens}
    if use_tools:
        kwargs["tools"] = tools.TOOL_SCHEMAS
        kwargs["tool_choice"] = "auto"
    try:
        return get_client().chat.completions.create(**kwargs)
    except openai.AuthenticationError as e:
        raise ServiceUnavailableError("OpenAI API 키가 올바르지 않습니다. OPENAI_API_KEY를 확인하세요.") from e
    except openai.NotFoundError as e:
        raise ServiceUnavailableError(f"모델 '{settings.openai_model}'을 사용할 수 없습니다. OPENAI_MODEL을 확인하세요.") from e
    except openai.RateLimitError as e:
        raise RateLimitError("OpenAI 요청 한도 또는 크레딧이 부족합니다. 잠시 후 다시 시도하거나 결제 설정을 확인하세요.") from e
    except openai.APITimeoutError as e:
        raise UpstreamError("OpenAI 응답 시간이 초과되었습니다. 다시 시도해 주세요.") from e
    except openai.APIConnectionError as e:
        raise UpstreamError("OpenAI 서버에 연결할 수 없습니다.") from e
    except openai.APIStatusError as e:
        raise UpstreamError(f"OpenAI 요청 실패 ({e.status_code}): {getattr(e, 'message', e)}") from e


def generate_reply(user_message: str, history: list[dict[str, Any]], summary: dict[str, Any]) -> tuple[str, list[dict]]:
    settings = get_settings()
    use_tools = settings.enable_tools
    messages: list[dict[str, Any]] = [{"role": "system", "content": build_system_prompt(summary, use_tools)}]
    for m in history[-settings.chat_history_limit:]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})

    tool_log: list[dict[str, Any]] = []
    for round_ in range(MAX_TOOL_ROUNDS + 1):
        allow_tools = use_tools and round_ < MAX_TOOL_ROUNDS   # 마지막 라운드는 반드시 답변하게 한다
        resp = _call_openai(messages, allow_tools)
        msg = resp.choices[0].message
        calls = getattr(msg, "tool_calls", None) or []
        if not calls:
            reply = (msg.content or "").strip()
            if not reply:
                reply = "죄송해요, 답변을 만들지 못했어요. 질문을 조금 더 구체적으로 다시 해 주세요."
            return reply, tool_log

        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [{"id": c.id, "type": "function",
                                         "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                        for c in calls]})
        for c in calls:
            args, result = tools.execute(c.function.name, c.function.arguments)
            tool_log.append({"name": c.function.name, "arguments": args})
            log.info("tool call: %s %s", c.function.name, args)
            messages.append({"role": "tool", "tool_call_id": c.id, "content": result})

    return "죄송해요, 답변을 만들지 못했어요.", tool_log


def chat(user_message: str, conversation_id: Optional[str] = None) -> dict[str, Any]:
    settings = get_settings()

    # 1) 이어지는 대화면 이전 메시지를 불러온다 (없는 ID면 404)
    history: list[dict[str, Any]] = []
    if conversation_id:
        history = conversation_service.get_conversation(conversation_id)["messages"]

    # 2) 데이터 요약 조회 → 3) 시스템 프롬프트 주입 + GPT 호출
    summary = data_service.get_summary()
    reply, tool_log = generate_reply(user_message, history, summary)

    # 4) 대화 자동 저장 (저장에 실패해도 답변은 돌려준다)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new_msgs = [{"role": "user", "content": user_message, "timestamp": now},
                {"role": "assistant", "content": reply, "timestamp": now, "tool_calls": tool_log}]
    saved, conv_id = True, conversation_id
    try:
        if conversation_id:
            conversation_service.append_messages(conversation_id, new_msgs)
        else:
            conv_id = conversation_service.create_conversation(new_msgs)["id"]
    except NotFoundError:
        raise
    except Exception as e:
        log.exception("대화 저장 실패: %s", e)
        saved = False

    return {"reply": reply, "conversation_id": conv_id, "saved": saved, "model": settings.openai_model,
            "summary_used": _summary_brief(summary), "tool_calls": tool_log}


def preview_prompt() -> str:
    """시스템 프롬프트 미리보기 (디버그/문서용)"""
    return build_system_prompt(data_service.get_summary(), get_settings().enable_tools)


def tool_schemas_json() -> str:
    return json.dumps(tools.TOOL_SCHEMAS, ensure_ascii=False, indent=2)
