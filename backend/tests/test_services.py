"""서비스 계층 테스트 — Firebase·OpenAI 없이 실행 가능 (메모리 DB + 가짜 GPT 클라이언트)

실행 (backend 폴더에서):  python -m pytest -q   또는   python tests/test_services.py
"""

from __future__ import annotations

import json
import math
import os
import sys
import types
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["USE_MEMORY_DB"] = "true"
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

if "openai" not in sys.modules:  # openai 패키지가 없는 환경에서도 테스트 가능하게
    try:
        import openai  # noqa: F401
    except ImportError:
        fake = types.ModuleType("openai")
        for n in ["AuthenticationError", "NotFoundError", "RateLimitError", "APITimeoutError",
                  "APIConnectionError", "APIStatusError"]:
            setattr(fake, n, type(n, (Exception,), {}))
        sys.modules["openai"] = fake

from pydantic import ValidationError  # noqa: E402

from app.errors import ConflictError, NotFoundError  # noqa: E402
from app.repositories import set_repositories  # noqa: E402
from app.repositories.memory import MemoryConversationRepository, MemoryDataRepository  # noqa: E402
from app.schemas import ChatRequest, DataCreate, DataUpdate  # noqa: E402
from app.services import chat_service, conversation_service, data_service, summary_service  # noqa: E402


def seed(n: int = 120) -> None:
    set_repositories(MemoryDataRepository(), MemoryConversationRepository())
    data_service.invalidate_cache()
    start = date(2025, 1, 1)
    rows = [{"date": (start + timedelta(days=i)).isoformat(),
             "value": round(10 + 12 * math.sin(i / 58) + (i % 5) * 0.3, 1), "memo": f"메모 {i}"}
            for i in range(n)]
    from app.repositories import get_data_repo
    get_data_repo().bulk_create(rows)
    data_service.invalidate_cache()


# ── 가짜 OpenAI 클라이언트 ─────────────────────
class FakeCompletions:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        step = self.script.pop(0)
        if step[0] == "tool":
            _, name, args = step
            tc = SimpleNamespace(id=f"call_{len(self.calls)}", type="function",
                                 function=SimpleNamespace(name=name, arguments=json.dumps(args)))
            msg = SimpleNamespace(content=None, tool_calls=[tc])
        else:
            msg = SimpleNamespace(content=step[1], tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def fake_client(script):
    comp = FakeCompletions(script)
    chat_service.set_client(SimpleNamespace(chat=SimpleNamespace(completions=comp)))
    return comp


# ── 테스트 ────────────────────────────────────
def test_schema_validation():
    assert DataCreate(date="2025-01-01", value=3.14159, memo="  hi ").memo == "hi"
    for bad in [{"date": "2025-13-01", "value": 1}, {"date": "2025-01-01", "value": float("nan")},
                {"date": "2025-01-01", "value": 1, "memo": "x" * 201}]:
        try:
            DataCreate(**bad)
            raise AssertionError(f"검증 실패: {bad}")
        except ValidationError:
            pass
    try:
        DataUpdate()
        raise AssertionError("빈 수정 요청이 통과됨")
    except ValidationError:
        pass
    try:
        ChatRequest(message="   ")
        raise AssertionError("빈 메시지가 통과됨")
    except ValidationError:
        pass


def test_summary_and_trend():
    seed(120)
    s = data_service.get_summary()
    assert s["count"] == 120 and s["period"] == "2025-01-01 ~ 2025-04-30"
    assert s["metrics"]["max"]["value"] >= s["metrics"]["average"] >= s["metrics"]["min"]["value"]
    assert s["trend_detail"]["direction"] in {"상승", "하락", "유지"}
    assert s["monthly"][0]["month"] == "2025-01" and len(s["monthly"]) == 4
    # 추세 판단 규칙
    assert summary_service.trend_of([1.0] * 7 + [5.0] * 7)["direction"] == "상승"
    assert summary_service.trend_of([5.0] * 7 + [1.0] * 7)["direction"] == "하락"
    assert summary_service.trend_of([3.0] * 14)["direction"] == "유지"
    assert summary_service.trend_of([1.0] * 5)["direction"] == "판단 불가"
    assert summary_service.compute_summary([], "t", "u")["count"] == 0


def test_crud_and_cache_invalidation():
    seed(120)
    before = data_service.get_summary()["count"]
    item = data_service.create_data(DataCreate(date="2025-06-01", value=30.5, memo="폭염"))
    assert data_service.get_summary()["count"] == before + 1           # 캐시가 비워졌는지
    assert data_service.get_summary()["metrics"]["max"]["date"] == "2025-06-01"
    try:
        data_service.create_data(DataCreate(date="2025-06-01", value=1))
        raise AssertionError("중복 날짜가 통과됨")
    except ConflictError:
        pass
    upd = data_service.update_data(item["id"], DataUpdate(value=31.0))
    assert upd["value"] == 31.0 and upd["memo"] == "폭염"
    try:
        data_service.update_data(item["id"], DataUpdate(date="2025-01-01"))
        raise AssertionError("다른 문서와 날짜 충돌이 통과됨")
    except ConflictError:
        pass
    data_service.delete_data(item["id"])
    assert data_service.get_summary()["count"] == before
    try:
        data_service.delete_data("nope")
        raise AssertionError
    except NotFoundError:
        pass
    rows = data_service.list_data("2025-02-01", "2025-02-10", order="desc", limit=3)
    assert [r["date"] for r in rows] == ["2025-02-10", "2025-02-09", "2025-02-08"]


def test_conversations():
    seed(20)
    c = conversation_service.create_conversation([{"role": "user", "content": "안녕하세요 " * 10},
                                                  {"role": "assistant", "content": "반가워요"}])
    assert c["title"].endswith("…") and c["message_count"] == 2
    conversation_service.append_messages(c["id"], [{"role": "user", "content": "추가"}])
    lst = conversation_service.list_conversations()
    assert lst[0]["id"] == c["id"] and lst[0]["message_count"] == 3 and "messages" not in lst[0]
    assert len(conversation_service.get_conversation(c["id"])["messages"]) == 3
    conversation_service.delete_conversation(c["id"])
    assert conversation_service.list_conversations() == []


def test_chat_context_injection_and_autosave():
    seed(120)
    comp = fake_client([("text", "최근 일주일 평균은 ...")])
    r = chat_service.chat("최근 추세 어때?")
    system = comp.calls[0]["messages"][0]
    assert system["role"] == "system"
    s = data_service.get_summary()
    assert s["period"] in system["content"] and str(s["count"]) in system["content"]   # 요약이 주입됨
    assert r["saved"] and r["conversation_id"] and r["reply"].startswith("최근")
    # 이어서 대화 → 같은 문서에 누적, 이전 메시지가 GPT에 전달됨
    comp = fake_client([("text", "두 번째 답")])
    r2 = chat_service.chat("그럼 가장 더운 날은?", r["conversation_id"])
    assert r2["conversation_id"] == r["conversation_id"]
    roles = [m["role"] for m in comp.calls[0]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert conversation_service.get_conversation(r["conversation_id"])["message_count"] == 4


def test_chat_function_calling():
    seed(120)
    comp = fake_client([
        ("tool", "query_data_range", {"start_date": "2025-02-01", "end_date": "2025-02-07"}),
        ("tool", "find_extreme_days", {"kind": "max", "n": 3}),
        ("text", "2월 첫 주 평균은 ..."),
    ])
    r = chat_service.chat("2월 첫째 주 기온이랑 가장 더웠던 날 알려줘")
    assert [t["name"] for t in r["tool_calls"]] == ["query_data_range", "find_extreme_days"]
    tool_msgs = [m for m in comp.calls[-1]["messages"] if m["role"] == "tool"]
    first = json.loads(tool_msgs[0]["content"])
    assert first["count"] == 7 and first["records"][0]["date"] == "2025-02-01"
    assert len(json.loads(tool_msgs[1]["content"])) == 3
    assert "tools" in comp.calls[0]
    saved = conversation_service.get_conversation(r["conversation_id"])["messages"][-1]
    assert saved["tool_calls"][0]["name"] == "query_data_range"


def test_unknown_conversation_404():
    seed(20)
    fake_client([("text", "x")])
    try:
        chat_service.chat("hi", "does-not-exist")
        raise AssertionError
    except NotFoundError:
        pass


def test_statistics():
    seed(120)
    st = data_service.get_statistics(7)
    assert st["series"][5]["moving_average"] is None and st["series"][6]["moving_average"] is not None
    assert len(st["weekday_average"]) == 7 and st["volatility"]["daily_change_std"] > 0


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"✅ {t.__name__}")
    print(f"\n{len(tests)}개 테스트 통과")
