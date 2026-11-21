"""(보너스) MCP 서버 — 같은 내부 기능을 외부 AI 클라이언트(Claude Desktop 등)에서 도구로 호출

이 서버는 배포된 백엔드 REST API를 호출하는 얇은 어댑터다.
웹 채팅의 Function Calling과 같은 기능을 MCP 프로토콜로 노출해, 외부 채널에서도 호출 흐름을 검증할 수 있다.

설치:  pip install mcp   (1.x, 2.x 모두 지원)
실행:  API_BASE_URL=https://<render-주소> python mcp_server/server.py   (stdio 방식)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = 90  # Render 무료 티어 콜드스타트 대비

mcp = _Server("seoul-weather-assistant")


def _request(method: str, path: str, params: dict | None = None, body: dict | None = None) -> Any:
    url = f"{API_BASE_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "detail": e.read().decode("utf-8", errors="ignore")[:500]}
    except urllib.error.URLError as e:
        return {"error": f"백엔드에 연결할 수 없습니다: {e.reason}"}


@mcp.tool()
def get_data_summary() -> dict:
    """저장된 서울 기온 데이터의 요약(기간, 개수, 평균/최고/최저, 최근 추세, 월별 평균)을 가져온다."""
    return _request("GET", "/api/data/summary")


@mcp.tool()
def query_data_range(start_date: str, end_date: str) -> list:
    """특정 기간(YYYY-MM-DD ~ YYYY-MM-DD)의 일별 기온 기록을 조회한다."""
    return _request("GET", "/api/data", {"start": start_date, "end": end_date})


@mcp.tool()
def get_statistics() -> dict:
    """확장 통계(변동성, 최대 상승/하락일, 요일별·월별 평균)를 가져온다."""
    result = _request("GET", "/api/data/statistics")
    if isinstance(result, dict):
        result.pop("series", None)
    return result


@mcp.tool()
def list_conversations(limit: int = 10) -> list:
    """웹 서비스에 저장된 최근 대화 목록을 조회한다."""
    return _request("GET", "/api/conversations", {"limit": limit})


@mcp.tool()
def ask_assistant(message: str) -> dict:
    """웹 서비스의 AI 비서(POST /api/chat)에게 질문하고 답변과 호출된 도구 기록을 받는다. 대화는 자동 저장된다."""
    return _request("POST", "/api/chat", body={"message": message})


if __name__ == "__main__":
    mcp.run()
