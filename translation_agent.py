"""
번역 에이전트: RAG로 검색된 LOC/한국문학번역원 원문을
초등학생 학년별 눈높이에 맞는 한국어 지문으로 각색한다.

사전 준비:
  pip install --upgrade google-genai google-cloud-aiplatform
  gcloud auth application-default login   (Cloud Shell이면 보통 이미 인증됨)
"""

import os
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from vertexai import rag
import vertexai

load_dotenv()

# ── 설정값 ──────────────────────────────────────────────────
PROJECT_ID = os.environ["PROJECT_ID"]
LOCATION = os.environ["RAG_LOCATION"]
CORPUS_NAME = (
    f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{os.environ['RAG_CORPUS_ID']}"
)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
# ──────────────────────────────────────────────────────────────

def get_rag_context(topic: str, top_k: int = 5) -> list[dict]:
    """RAG 코퍼스에서 주제 관련 원문 청크를 검색해 반환한다."""
    vertexai.init(project=PROJECT_ID, location=LOCATION)

    response = rag.retrieval_query(
        rag_resources=[rag.RagResource(rag_corpus=CORPUS_NAME)],
        text=topic,
        rag_retrieval_config=rag.RagRetrievalConfig(top_k=top_k),
    )

    results = []
    for ctx in response.contexts.contexts:
        results.append(
            {
                "source_uri": ctx.source_uri,
                "text": ctx.text,
                "score": ctx.score,
            }
        )
    return results


def build_translation_prompt(original_text: str, grade_track: str) -> str:
    """번역 에이전트용 프롬프트를 구성한다. grade_track: 'low' 또는 'high'"""
    grade_desc = {
        "low": "저학년 (1~3학년): 쉬운 어휘 사용, 짧고 단순한 문장 구조, 직관적이고 친근한 서술.",
        "high": "고학년 (4~6학년): 풍부한 어휘 및 문장 구조 적용, 비판적 사고 및 독서 논술 대화가 가능하도록 맥락과 논리적 서사 유지.",
    }[grade_track]

    return f"""[Role]
너는 초등학생의 눈높이에 맞춰 문학 작품을 친근하게 재구성해 주는 전문 가공 에이전트이자 AI 문해력 튜터야.

[Task]
아래 [원문]을 사용자가 요청한 학년 수준에 맞는 한국어 지문으로 각색 및 요약해라.

[원문]
{original_text}

[Rules]
1. 근거 기반 작성(Grounding): 반드시 [원문]의 내용만 바탕으로 작성할 것.
   원문에 없는 사건, 인물, 내용을 임의로 지어내지 말 것.
2. 학년별 난이도 조정: {grade_desc}
3. 어조: 다정하고 친근한 '해요체' 사용 (~했답니다, ~했어요).
4. 분량: 아이들이 읽기 부담스럽지 않도록 2~3개 이내의 짧은 문단으로 구성할 것.

[Safety Rule - 최우선 적용]
5. 콘텐츠 적합성 검사: [원문]에 아래 중 하나라도 핵심 내용으로 포함되어 있으면,
   지문을 생성하지 말고 "[UNSUITABLE]" 한 줄만 출력해라.
   - 음주·흡연·약물(항우울제 등 처방약 포함) 관련 상세 묘사
   - 자해·우울증·정신질환 증상에 대한 구체적 묘사
   - 성적/로맨틱한 신체 접촉, 클럽·유흥업소 등 성인 유흥 공간
   - 금전 갈취, 사기, 폭력, 범죄 행위
   단, 위 소재가 스토리의 핵심이 아니라 배경에서 스치듯 언급되는 수준이면
   해당 부분을 제외하고 나머지 내용만으로 각색을 시도해도 좋다.
   판단이 애매하면 안전한 쪽(=생성하지 않는 쪽)을 선택해라.

[Output Format]
- [제목]: (지문에 어울리는 한글 제목)
- [읽기 지문]: (각색된 지문 본문)
- 5번 규칙에 의해 생성이 불가능하면 "[UNSUITABLE]" 한 줄만 출력하고 그 외 텍스트는 출력하지 말 것.
"""


def run_translation_agent(topic: str, grade_track: str, top_k: int = 5) -> dict:
    """RAG 검색 -> Gemini 각색까지 한 번에 실행."""
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

    contexts = get_rag_context(topic, top_k=top_k)
    if not contexts:
        return {"status": "no_context", "passage": None, "sources": []}

    # top_k개 청크 중 가장 관련도 높은 것부터 순서대로 시도
    for ctx in contexts:
        prompt = build_translation_prompt(ctx["text"], grade_track)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(temperature=0.3),
        )
        output = response.text.strip()

        if "[UNSUITABLE]" in output:
            continue  # 다음 후보 청크로 재시도

        return {
            "status": "ok",
            "passage": output,
            "source_uri": ctx["source_uri"],
            "score": ctx["score"],
        }

    # top_k개 모두 부적합 판정된 경우
    return {"status": "all_unsuitable", "passage": None, "sources": [c["source_uri"] for c in contexts]}


if __name__ == "__main__":
    result = run_translation_agent(topic="용감한 동물 친구 이야기", grade_track="low")
    print("상태:", result["status"])
    if result["status"] == "ok":
        print("출처:", result["source_uri"], "| 점수:", result["score"])
        print()
        print(result["passage"])
    else:
        print("사용 가능한 원문을 찾지 못했습니다:", result.get("sources"))