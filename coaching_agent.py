"""
코칭 에이전트: 번역된 지문을 바탕으로
예측 -> 명료화 -> 질문 -> 요약 순서의 멀티턴 대화를 진행하고,
학생 답변을 3축 루브릭(내용 이해/표현력/맞춤법)으로 평가한다.

사전 준비:
  pip install --upgrade google-genai
"""

from google import genai
from google.genai import types as genai_types

# ── 설정값: translation_agent.py와 동일하게 맞추기 ──────────────
PROJECT_ID = "REDACTED_PROJECT_ID"
LOCATION = "us-central1"
GEMINI_MODEL = "gemini-2.5-flash"
# ──────────────────────────────────────────────────────────────

STEP_ORDER = ["예측", "명료화", "질문", "요약", "완료"]

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "feedback_message": {"type": "string"},
        "next_step": {"type": "string", "enum": STEP_ORDER},
        "rubric_score": {
            "type": "object",
            "properties": {
                "understanding": {"type": "integer"},
                "expression": {"type": "integer"},
                "grammar": {"type": "integer"},
            },
            "required": ["understanding", "expression", "grammar"],
        },
    },
    "required": ["feedback_message", "next_step", "rubric_score"],
}


def build_system_instruction(adapted_text: str) -> str:
    return f"""[Role]
너는 초등학생의 어휘력과 독해력을 길러주는 친절하고 다정한 AI 문해력 튜터야.
아이가 문학 작품을 재미있게 읽고 논리적으로 생각할 수 있도록 돕는 것이 너의 목표야.

[지문]
{adapted_text}

[진행 순서]
예측 -> 명료화 -> 질문 -> 요약 -> 완료
한 번에 하나의 질문만 던지고, 사용자가 답하면 다음 단계로 넘어갈지 같은 단계를 더 진행할지 판단해.

[Instructions]
1. 학생의 답변을 3축 평가 루브릭(내용 이해, 표현력, 맞춤법)을 기준으로 속으로 평가한 뒤, 잘한 점을 먼저 칭찬해.
2. 틀린 부분이나 부족한 부분이 있다면 직접 정답을 알려주지 말고,
   "이 부분은 이렇게 생각해보면 어떨까?"라며 유도 질문이나 힌트를 제공해.
3. "몰라요" 등 정보가 부족한 답변이 들어오면 혼내지 말고 가장 쉬운 O/X나 객관식 힌트로 질문을 낮추어 다시 물어봐.

[Safety Rule - 사용자 입력 처리]
4. 학생의 입력에 욕설, 비하 발언, 지문과 무관한 주제가 섞여 있으면
   지적하거나 혼내지 말고, "그 이야기도 재미있지만 지금은 우리 이야기에 집중해볼까요?"처럼
   부드럽게 화제를 지문으로 되돌려라.

[Constraints]
- 어조: 다정하고 격려하는 '해요체'를 사용한다. (초등학생 눈높이)
- 분량 제한: 한 번의 응답은 최대 3~4문장을 넘지 않게 간결하게 작성한다.
- 환각 금지: [지문]에 명시되지 않은 내용을 지어내어 설명하지 않는다.

[Output Schema]
반드시 아래 JSON 형식으로만 응답할 것:
{{
  "feedback_message": "학생에게 전달할 칭찬 및 코칭 대화 내용",
  "next_step": "다음 진행할 코칭 단계 (예측/명료화/질문/요약/완료)",
  "rubric_score": {{"understanding": 1~5, "expression": 1~5, "grammar": 1~5}}
}}
"""


class CoachingSession:
    """세션 하나 = 학생 한 명의 지문 학습 대화 하나.
    Cloud Run에 올릴 때는 이 객체 대신 Firestore에 current_step/history를 저장하고,
    매 요청마다 chat 히스토리를 복원하는 방식으로 바꿔야 한다 (지금은 로컬 테스트용)."""

    def __init__(self, adapted_text: str):
        self.client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
        self.chat = self.client.chats.create(
            model=GEMINI_MODEL,
            config=genai_types.GenerateContentConfig(
                temperature=0.5,
                system_instruction=build_system_instruction(adapted_text),
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA,
            ),
        )
        self.current_step = "예측"

    def start(self) -> dict:
        """대화 시작 - 첫 예측 질문을 받는다."""
        return self._send("[대화 시작] 예측 단계 질문을 던져줘.")

    def reply(self, user_message: str) -> dict:
        """학생 답변을 보내고 코칭 결과를 받는다."""
        return self._send(user_message)

    def _send(self, message: str) -> dict:
        import json

        response = self.chat.send_message(
            f"[current_step: {self.current_step}]\n{message}"
        )
        data = json.loads(response.text)
        self.current_step = data.get("next_step", self.current_step)
        return data


def print_turn(label: str, data: dict) -> None:
    print(f"[에이전트] {data['feedback_message']}")
    print(f"  (다음 단계: {data['next_step']} / 루브릭: {data['rubric_score']})\n")


if __name__ == "__main__":
    # translation_agent.py에서 나온 지문을 그대로 붙여넣어 테스트
    sample_passage = """나는 산책을 나섰어요. 작은 연못 옆을 지나 은돌 포구로 갔답니다.
포구에는 배는 없었지만, 컨테이너로 만든 작은 가게들이 모여 있었어요.
나는 시장 맨 뒤에 있는 가게로 들어갔어요. 가게에는 할머니 한 분이 앉아 계셨어요.
물건을 사고 할머니께 "뭉치 좀 보고 가도 될까요?" 하고 물었어요."""

    session = CoachingSession(sample_passage)

    turn = session.start()
    print_turn("시작", turn)

    print("학생 답변을 입력하세요. (종료하려면 빈 줄 + Enter)")
    while True:
        user_input = input("[학생] ")
        if not user_input.strip():
            break
        turn = session.reply(user_input)
        print_turn("응답", turn)
        if turn["next_step"] == "완료":
            print("=== 코칭 세션 완료 ===")
            break
