"""
FastAPI 백엔드 - 번역 에이전트 + 코칭 에이전트 통합

로컬 실행:
  pip install --upgrade fastapi uvicorn[standard] google-genai
  uvicorn main:app --reload --port 8080

주의: 세션/지문 데이터를 지금은 프로세스 메모리(dict)에 저장합니다.
Cloud Run은 인스턴스가 여러 개 뜨거나 재시작될 수 있어 메모리 저장은
운영 환경에서 안전하지 않습니다. MVP 로컬 테스트 통과 후,
Firestore로 옮기는 작업이 반드시 필요합니다 (SECTION 06 아키텍처 참고).
"""

import uuid
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from translation_agent import run_translation_agent
from coaching_agent import CoachingSession

app = FastAPI(title="Literacy Agent Backend")

# ── 임시 인메모리 저장소 (추후 Firestore로 교체) ──────────────────
PASSAGES: dict[str, dict] = {}      # passage_id -> {"text":..., "source_uri":...}
SESSIONS: dict[str, CoachingSession] = {}  # session_id -> CoachingSession
# ──────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "ok"}


# ── /api/passage ────────────────────────────────────────────────
class PassageRequest(BaseModel):
    grade_track: str   # "low" | "high"
    topic: str


class PassageResponse(BaseModel):
    passage_id: str
    text: str
    source: str


@app.post("/api/passage", response_model=PassageResponse)
def get_passage(req: PassageRequest):
    if req.grade_track not in ("low", "high"):
        raise HTTPException(status_code=422, detail="grade_track must be 'low' or 'high'")

    result = run_translation_agent(topic=req.topic, grade_track=req.grade_track)

    if result["status"] != "ok":
        raise HTTPException(
            status_code=404,
            detail=f"적합한 지문을 찾지 못했습니다 (status={result['status']})",
        )

    passage_id = str(uuid.uuid4())
    PASSAGES[passage_id] = {
        "text": result["passage"],
        "source_uri": result["source_uri"],
    }

    return PassageResponse(
        passage_id=passage_id,
        text=result["passage"],
        source=result["source_uri"],
    )


# ── /api/coach/turn ─────────────────────────────────────────────
class CoachTurnRequest(BaseModel):
    session_id: str
    passage_id: str
    user_message: str | None = None  # 세션 시작 시(첫 호출)는 생략 가능


class CoachTurnResponse(BaseModel):
    session_id: str
    stage: str
    agent_message: str


@app.post("/api/coach/turn", response_model=CoachTurnResponse)
def coach_turn(req: CoachTurnRequest):
    # 새 세션이면 passage로부터 코칭 세션 생성
    if req.session_id not in SESSIONS:
        if req.passage_id not in PASSAGES:
            raise HTTPException(status_code=400, detail="passage_id를 찾을 수 없습니다.")
        passage_text = PASSAGES[req.passage_id]["text"]
        session = CoachingSession(passage_text)
        SESSIONS[req.session_id] = session
        turn = session.start()
    else:
        session = SESSIONS[req.session_id]
        if not req.user_message:
            raise HTTPException(status_code=400, detail="user_message가 필요합니다.")
        turn = session.reply(req.user_message)

    return CoachTurnResponse(
        session_id=req.session_id,
        stage=turn["next_step"],
        agent_message=turn["feedback_message"],
    )


# ── /api/essay/feedback (기능 4 - 추후 구현) ────────────────────
class EssayFeedbackRequest(BaseModel):
    session_id: str
    essay_text: str


@app.post("/api/essay/feedback")
def essay_feedback(req: EssayFeedbackRequest):
    raise HTTPException(
        status_code=501,
        detail="서술형 답안 논술 첨삭(기능 4)은 아직 구현되지 않았습니다.",
    )


# ── 웹 UI 서빙 (반드시 API 라우트 등록 이후, 파일 맨 끝에 위치) ──
app.mount("/", StaticFiles(directory="static", html=True), name="static")
