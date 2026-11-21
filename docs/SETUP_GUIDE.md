# 설정 · 배포 가이드 (작업 순서대로)

처음부터 끝까지 이 순서대로 진행하면 됩니다. 각 단계에 **접속 주소 → 설정할 값 → 동작 방식**을 적었습니다.

| 단계 | 할 일 | 사용하는 서비스 | 비용 |
|---|---|---|---|
| 0 | 프로그램 설치 | Python, Git, VS Code | 무료 |
| 1 | Firestore DB 만들기, 서비스 계정 키 받기 | Firebase | 무료 (Spark 요금제) |
| 2 | OpenAI API 키 발급, 사용 한도 설정 | OpenAI Platform | **유료** (사용한 만큼) |
| 3 | 로컬에서 실행·확인 | 내 PC | 무료 |
| 4 | GitHub에 코드 올리기 | GitHub | 무료 |
| 5 | 백엔드 배포 | Render | 무료 (Free 인스턴스) |
| 6 | 프론트엔드 배포 | Vercel | 무료 (Hobby) |
| 7 | CORS 연결, 최종 확인, 스크린샷 | Render, Vercel | — |
| 8 | (보너스) MCP 연동 확인 | Claude Desktop | 무료 |

---

## 0. 프로그램 설치

| 프로그램 | 주소 | 비고 |
|---|---|---|
| Python 3.10 이상 | https://www.python.org/downloads/ | 설치 화면에서 **Add python.exe to PATH** 체크 |
| Git | https://git-scm.com/downloads | 기본 옵션으로 설치 |
| VS Code (권장) | https://code.visualstudio.com/ | README 미리보기·편집용 |
| GitHub 계정 | https://github.com/signup | |

설치 확인 (PowerShell):
```powershell
python --version   # 3.10 이상
git --version
```

---

## 1. Firebase — Firestore DB와 서비스 계정 키

**동작 방식:** 백엔드가 **서비스 계정 키**(관리자 권한 열쇠)로 Firestore에 접속해 `data`, `conversations` 컬렉션을 읽고 씁니다. 브라우저는 Firestore에 직접 접근하지 않고 항상 백엔드 API를 거칩니다. 그래서 보안 규칙은 "프로덕션 모드(외부 접근 차단)"로 두면 됩니다.

1. https://console.firebase.google.com 에 접속해 구글 계정으로 로그인합니다.
2. **프로젝트 만들기(추가)** → 이름 입력(예: `seoul-weather-assistant`) → Google Analytics는 꺼도 됩니다 → 만들기
3. 왼쪽 메뉴 **빌드(Build) → Firestore Database → 데이터베이스 만들기**
   - 위치: **`asia-northeast3 (Seoul)`** — 한 번 정하면 바꿀 수 없습니다.
   - 보안 규칙: **프로덕션 모드**
4. 톱니바퀴 **프로젝트 설정 → 서비스 계정** 탭 → **새 비공개 키 생성** → JSON 파일이 다운로드됩니다.
5. 받은 파일 이름을 `serviceAccountKey.json`으로 바꿔 `backend/` 폴더에 넣습니다.

> ⚠️ 이 JSON 파일은 DB 관리자 비밀번호와 같습니다. `.gitignore`에 등록되어 있으니 **절대 GitHub에 올리지 마세요.** 컬렉션(`data`, `conversations`)은 첫 데이터가 저장될 때 자동으로 생깁니다.

---

## 2. OpenAI — API 키와 사용 한도

**동작 방식:** `/api/chat` 요청이 오면 백엔드가 데이터 요약을 시스템 프롬프트에 넣고 OpenAI API를 호출합니다. 키는 서버 환경 변수에만 있고 브라우저로 내려가지 않습니다.

1. https://platform.openai.com/api-keys → **Create new secret key** → `sk-...` 키를 복사해 둡니다 (다시 볼 수 없음).
2. https://platform.openai.com/settings/organization/billing → 결제 수단을 등록하고 크레딧을 충전합니다 ($5 정도면 과제에 충분).
3. https://platform.openai.com/settings/organization/limits → **월 예산 한도(Budget)**를 낮게 설정해 과금 사고를 막습니다.
4. 모델은 `OPENAI_MODEL` 환경 변수로 정합니다. 기본값은 `gpt-5.4-mini`입니다. https://platform.openai.com/docs/models 에서 사용 가능한 모델을 확인하고, 오류가 나면 이 값만 바꾸면 됩니다.

**비용 보호 장치 (코드에 이미 적용됨)**
- 응답 최대 토큰 `OPENAI_MAX_TOKENS=1500`
- 프롬프트에 넣는 이전 대화는 최근 10개만 (`CHAT_HISTORY_LIMIT`)
- 질문 길이 최대 1000자 (Pydantic 검증)
- 도구 호출은 한 질문당 최대 4회

---

## 3. 로컬 실행

### 3-1. 백엔드

```powershell
cd ai-weather-assistant\backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

`.env`를 메모장이나 VS Code로 열어 값을 채웁니다.

```
OPENAI_API_KEY=sk-...(2단계에서 복사한 키)
FIREBASE_SERVICE_ACCOUNT_PATH=./serviceAccountKey.json
ALLOWED_ORIGINS=http://localhost:5500,http://127.0.0.1:5500
```

초기 데이터를 넣고(서울 최근 365일 기온), 서버를 실행합니다.

```powershell
.venv\Scripts\python.exe scripts\seed_data.py
.venv\Scripts\python.exe -m uvicorn main:app --reload
```

- http://localhost:8000/docs 에 접속하면 **Swagger UI**가 보입니다.
- `GET /api/data/summary` → **Try it out → Execute**를 눌러 요약이 나오는지 확인합니다.

> 💡 `pip.exe`나 `Activate.ps1`이 회사·학교 보안 정책으로 막혀 있으면, 위처럼 항상 `.venv\Scripts\python.exe -m ...` 형태로 실행하면 됩니다.
>
> 💡 Firebase 설정 전에 화면부터 보고 싶다면 `.env`에서 `USE_MEMORY_DB=true`로 바꿉니다. 서버를 재시작하면 데이터가 사라지고, 이 모드에서는 시드 스크립트가 적용되지 않습니다(데이터 관리 화면에서 직접 추가).
>
> 💡 `seed_data.py`가 인터넷 문제로 실패하면, 화면에 나온 URL을 브라우저로 열어 `raw.json`으로 저장한 뒤 `scripts\seed_data.py --json raw.json`으로 실행하세요.

### 3-1-1. (선택) 내가 가진 CSV로 데이터 넣기

`seed_data.py --csv`는 열 이름을 자동으로 찾습니다. 먼저 `--dry-run`으로 어떻게 읽히는지 확인한 뒤, `--reset`으로 기존 데이터를 지우고 넣으세요.

**이전 과제 CSV가 `backend/data/seoul_2000_2024.csv`에 들어 있습니다 (9,132일, 결측 0).** 2024년 1년치(366일)를 넣는 명령:

```powershell
.venv\Scripts\python.exe scripts\seed_data.py --csv data\seoul_2000_2024.csv --start 2024-01-01 --dry-run   # 확인
.venv\Scripts\python.exe scripts\seed_data.py --csv data\seoul_2000_2024.csv --start 2024-01-01 --reset     # 저장
```

- `--last 365`가 아니라 `--start 2024-01-01`을 쓰는 이유: 2024년은 윤년(366일)이라 `--last 365`면 1월 1일이 빠집니다.
- 2년치 비교 질문까지 하려면 `--start 2023-01-01` (731개)을 쓰세요.
- 데이터가 오늘보다 오래되었기 때문에, 서버는 **데이터 마지막 날(2024-12-31)을 분석 기준일**로 삼습니다. "이번 달", "최근"은 2024년 12월 기준으로 답하고, 화면에도 기준일이 표시됩니다 (`DATA_REFERENCE_DATE=auto`).

다른 CSV를 쓸 때의 예시:

```powershell
.venv\Scripts\python.exe scripts\seed_data.py --csv my_steps.csv --value-col 걸음수 --memo-col 비고 --reset
```

| 항목 | 자동 처리 |
|---|---|
| 날짜 열 | `date`, `날짜`, `일자`, `일시`, `Date` 등 |
| 값 열 | `value`, `값`, `tmean`, `평균기온(°C)`, `temp`, `close`, `종가` 등 (없으면 `--value-col`로 지정) |
| 메모 열 | `memo`, `메모`, `비고`, `note`. 이전 과제 CSV는 최고/최저/강수로 메모를 자동 생성 |
| 날짜 형식 | `2024-01-01`, `2024/01/01`, `2024.01.01`, `20240101`, `2024-01-01 09:00` |
| 인코딩 | UTF-8, CP949(엑셀·기상청 자료) |
| 정리 | 빈 값·숫자가 아닌 값은 건너뛰고, 같은 날짜는 첫 행만 사용. `8,000`처럼 쉼표 있는 숫자도 처리 |
| 기간 | `--last 365` (최근 N개), `--start 2025-01-01`, `--end 2025-12-31` |

- **데이터는 100개 이상**이어야 합니다 (과제 조건). 적으면 경고가 나옵니다.
- **너무 많으면 줄이세요.** 수천 개 이상이면 Firestore 무료 읽기 한도(하루 5만 회)에 부담이 되므로 `--last 365` 정도를 권장합니다.
- **다른 주제(걸음 수, 학습 시간 등)라면** `.env`(배포 시 Render 환경 변수)의 `DATA_TITLE`과 `DATA_UNIT`을 바꾸세요. 예: `DATA_TITLE=하루 걸음 수`, `DATA_UNIT=걸음`. AI 프롬프트와 화면 표시가 함께 바뀝니다.

### 3-2. 프론트엔드

새 PowerShell 창에서 실행합니다.
```powershell
cd ai-weather-assistant\frontend
python -m http.server 5500
```
http://localhost:5500 에 접속합니다. `frontend/config.js`의 `API_BASE_URL`이 `http://localhost:8000`으로 되어 있어 로컬 백엔드에 연결됩니다.

### 3-3. 테스트 (선택)

```powershell
cd ai-weather-assistant\backend
.venv\Scripts\python.exe tests\test_services.py
```
Firebase·OpenAI 없이 메모리 DB와 가짜 GPT로 서비스 로직 8개 항목을 검사합니다.

---

## 4. GitHub에 올리기

1. https://github.com/new → 저장소 이름(예: `ai-weather-assistant`) → **Create repository**
2. 프로젝트 폴더에서 실행합니다.

```powershell
cd ai-weather-assistant
git init
git add .
git status          # ← .env, serviceAccountKey.json이 목록에 없는지 반드시 확인
git commit -m "AI 날씨 비서 초기 버전"
git branch -M main
git remote add origin https://github.com/<아이디>/ai-weather-assistant.git
git push -u origin main
```

---

## 5. Render — 백엔드 배포

**동작 방식:** Render가 GitHub의 `backend/` 폴더를 받아 `pip install`로 설치한 뒤 `uvicorn`으로 서버를 띄웁니다. 비밀 값은 Render 환경 변수에 넣습니다.

1. https://dashboard.render.com 에서 GitHub 계정으로 가입·로그인합니다.
2. **New + → Web Service** → GitHub 저장소 연결 → `ai-weather-assistant` 선택
3. 설정 값

| 항목 | 값 |
|---|---|
| Name | `seoul-weather-assistant-api` (주소가 됨) |
| Region | Singapore (한국에서 가장 가까움) |
| Branch | `main` |
| Root Directory | **`backend`** |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Instance Type | **Free** |

4. **Environment Variables**에 아래 값을 추가합니다.

| Key | Value |
|---|---|
| `PYTHON_VERSION` | `3.12.7` |
| `OPENAI_API_KEY` | `sk-...` |
| `OPENAI_MODEL` | `gpt-5.4-mini` |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | `serviceAccountKey.json` 파일 내용 **전체**를 복사해 붙여 넣기 (`{`부터 `}`까지) |
| `ALLOWED_ORIGINS` | 일단 `http://localhost:5500` (7단계에서 Vercel 주소 추가) |

5. **Advanced → Health Check Path**에 `/health`를 입력합니다.
6. **Create Web Service** → 로그에 `Uvicorn running on ...`이 나오면 배포가 끝난 것입니다.
7. `https://<서비스이름>.onrender.com/docs` 에 접속해 Swagger UI를 확인합니다.

> **무료 티어 콜드스타트:** 15분 동안 요청이 없으면 서버가 잠들고, 다음 첫 요청은 깨어나는 데 최대 1분 정도 걸립니다.
> 이 프로젝트는 다음과 같이 대응합니다.
> - 프론트가 첫 화면에서 `/health`로 서버를 먼저 깨웁니다. 2.5초가 넘으면 "서버를 깨우는 중" 안내 배너를 띄우고, 최대 3회(각 70초) 재시도합니다.
> - 채팅 대기 중 10초가 지나면 "서버가 깨어나는 중일 수 있어요" 문구로 바뀝니다.
> - (선택) https://cron-job.org 에서 10분마다 `https://<서비스이름>.onrender.com/health`를 호출하게 하면 잠들지 않습니다.

> **초기 데이터:** 3단계에서 로컬로 시드를 실행했다면 같은 Firestore를 쓰므로 배포 서버에도 이미 데이터가 있습니다.

---

## 6. Vercel — 프론트엔드 배포

**동작 방식:** 브라우저에서 실행되는 JS는 환경 변수를 직접 읽을 수 없습니다. 그래서 Vercel이 배포할 때 `build.js`를 실행해, 환경 변수 `API_BASE_URL` 값을 담은 `config.js`를 만들고 `dist/` 폴더를 배포합니다. (프레임워크 없이 Node 기본 모듈만 사용)

1. https://vercel.com/new 에서 GitHub로 로그인 → `ai-weather-assistant` 저장소 **Import**
2. 설정 값

| 항목 | 값 |
|---|---|
| Root Directory | **`frontend`** (Edit을 눌러 선택) |
| Framework Preset | **Other** |
| Build / Output 설정 | `vercel.json`에 있으므로 그대로 둠 (`node build.js` → `dist`) |

3. **Environment Variables**

| Key | Value |
|---|---|
| `API_BASE_URL` | `https://<서비스이름>.onrender.com` (끝에 `/` 없이) |

4. **Deploy** → 완료되면 `https://<프로젝트>.vercel.app` 주소가 나옵니다.

> 환경 변수를 나중에 바꿨다면 **Deployments → … → Redeploy**를 해야 반영됩니다.

---

## 7. CORS 연결 및 최종 확인

**왜 필요한가:** 브라우저는 `vercel.app` 페이지에서 `onrender.com` API를 호출하는 것을 기본적으로 막습니다(다른 출처). 백엔드가 "이 주소는 허용한다"고 응답해야 요청이 통과합니다. 모든 주소(`*`)를 허용하면 아무 사이트나 내 API와 OpenAI 크레딧을 쓸 수 있으므로, 내 프론트 주소만 허용합니다.

1. Render → 서비스 → **Environment** → `ALLOWED_ORIGINS` 값을 아래처럼 바꿉니다.
   ```
   https://<프로젝트>.vercel.app,http://localhost:5500
   ```
   쉼표로 구분하고, 끝에 `/`를 붙이지 않습니다.
2. 저장하면 자동으로 다시 배포됩니다.
3. Vercel 주소에 접속해 아래를 확인합니다.
   - [ ] 오른쪽 위에 "서버 연결됨" 표시
   - [ ] 요약 카드와 그래프 표시
   - [ ] 질문 → 로딩 표시 → 답변 (답변 아래 "요약 반영" 표시)
   - [ ] 데이터 추가·수정·삭제
   - [ ] 왼쪽 대화 목록 클릭 → 이전 대화 불러오기

**자주 나오는 오류**

| 증상 | 원인 / 해결 |
|---|---|
| "서버에 연결할 수 없어요" | `ALLOWED_ORIGINS`에 Vercel 주소가 없거나 오타 (`https://`, 끝 `/` 확인) |
| 채팅 시 "OPENAI_API_KEY ..." (503) | Render 환경 변수의 키 확인 |
| "모델 ... 을 사용할 수 없습니다" | `OPENAI_MODEL`을 계정에서 쓸 수 있는 모델로 변경 |
| "요청 한도 또는 크레딧" (429) | OpenAI 결제·한도 확인 |
| "Firebase 서비스 계정 키가 설정되지 않았습니다" (503) | `FIREBASE_SERVICE_ACCOUNT_JSON`에 JSON 전체가 들어갔는지 확인 |
| Vercel 빌드 실패 "API_BASE_URL이 없습니다" | Vercel 환경 변수 추가 후 Redeploy |

### 제출 스크린샷 찍기

`docs/screenshots/`에 아래 파일명으로 저장하면 README에 자동으로 표시됩니다.

| 파일명 | 화면 |
|---|---|
| `chat.png` | 상단 요약 띠가 보이는 상태에서 질문과 답변 1세트 이상 |
| `data.png` | 데이터 관리 탭에서 추가 또는 수정 직후 (초록 강조 행과 "추가했어요" 알림이 보이게) |
| `history.png` | 왼쪽 대화 목록에서 이전 대화를 클릭해 메시지가 다시 표시된 화면 |
| `swagger.png` | 배포 주소의 `/docs` 화면 |
| `dark.png` (보너스) | 다크 모드 + 그래프 |

---

## 8. (보너스) MCP 연동 확인 — Claude Desktop

**동작 방식:** `mcp_server/server.py`는 배포된 백엔드 API를 MCP 도구 5개로 노출합니다. Claude Desktop이 이 서버를 실행하고, 대화 중 필요한 도구를 호출합니다. 웹 채팅의 Function Calling과 같은 기능을 외부 클라이언트에서 검증하는 방식입니다.

1. https://claude.ai/download 에서 Claude Desktop을 설치하고 로그인합니다.
2. MCP 라이브러리를 설치합니다: `python -m pip install mcp`
3. Claude Desktop → **설정 → 개발자(Developer) → 구성 편집(Edit Config)**을 누릅니다. Windows에서는 `%APPDATA%\Claude\claude_desktop_config.json` 파일이 열립니다.
4. `mcp_server/claude_desktop_config.example.json` 내용을 참고해 붙여 넣습니다.
   - `args`: `server.py`의 실제 경로
   - `API_BASE_URL`: Render 주소
5. Claude Desktop을 완전히 종료했다가 다시 실행하면, 입력창의 도구 아이콘에 `seoul-weather-assistant`가 보입니다.
6. "서울 기온 데이터 요약해 줘", "가장 더웠던 날이 언제야?"처럼 물어보고 도구 호출 화면을 캡처해 `docs/screenshots/mcp.png`로 저장합니다.
