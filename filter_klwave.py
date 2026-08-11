"""
KLWAVE 발췌본 아동 적합성 필터링 스크립트

목적:
  GCS 버킷(klwave-raw-texts-1)에 있는 발췌본 50개를 Gemini로 분류해서
  ① 아동에게 적합한지 여부, ② 적합하다면 저학년/고학년 중 어느 트랙에
  맞는지, ③ 판단 근거를 함께 JSON으로 태깅합니다.

  결과는 filter_results.jsonl 로 저장되고, 적합 판정된 파일만
  approved_uris.txt 에 목록으로 남습니다. 이 목록을 RAG Engine 코퍼스에
  다시 임포트하거나, 검색 결과 후처리 단계에서 화이트리스트로 쓰면 됩니다.

사용법:
  python3 filter_klwave.py --bucket klwave-raw-texts-1 --prefix excerpts/ \
      --project your-project-id --location us-central1
"""

import argparse
import json
import time

from google.cloud import storage
import vertexai
from vertexai.generative_models import GenerativeModel

SYSTEM_PROMPT = """당신은 초등학생(7~12세) 대상 콘텐츠 심사자입니다.
주어진 한국문학 발췌본이 초등학생에게 읽혀도 되는지 판단하세요.

판단 기준:
- 폭력, 죽음(특히 상세 묘사), 자해, 성적 내용, 심한 욕설, 약물,
  종교적으로 민감하거나 논쟁적인 소재가 포함되면 부적합입니다.
- 슬픔, 이별, 우정, 성장, 모험, 자연, 동물 등은 적합할 수 있습니다.
- 문장이 너무 어렵거나 시적/추상적이어서 초등학생이 이해하기
  힘든 경우도 고려하되, 이건 부적합이 아니라 "고학년" 트랙으로 분류하세요.

아래 JSON 스키마로만 응답하세요. 다른 텍스트는 포함하지 마세요.
{
  "appropriate": true 또는 false,
  "track": "저학년" 또는 "고학년" 또는 null(부적합 시),
  "reason": "판단 근거 한 문장"
}
"""


def classify_excerpt(model: GenerativeModel, text: str) -> dict:
    prompt = f"{SYSTEM_PROMPT}\n\n---\n발췌본:\n{text[:3000]}\n---"
    response = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"},
    )
    try:
        return json.loads(response.text)
    except (json.JSONDecodeError, AttributeError) as e:
        return {"appropriate": False, "track": None, "reason": f"파싱 실패: {e}"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="us-central1")
    parser.add_argument("--model", default="gemini-2.5-flash")
    args = parser.parse_args()

    vertexai.init(project=args.project, location=args.location)
    model = GenerativeModel(args.model)

    storage_client = storage.Client(project=args.project)
    bucket = storage_client.bucket(args.bucket)
    blobs = list(bucket.list_blobs(prefix=args.prefix))
    print(f"총 {len(blobs)}개 파일 발견")

    results = []
    approved = []

    for i, blob in enumerate(blobs):
        if not blob.name.endswith(".txt"):
            continue
        text = blob.download_as_text()
        verdict = classify_excerpt(model, text)
        verdict["uri"] = f"gs://{args.bucket}/{blob.name}"
        results.append(verdict)

        status = "적합" if verdict.get("appropriate") else "부적합"
        print(f"[{i+1}/{len(blobs)}] {blob.name} -> {status} "
              f"({verdict.get('track')}) - {verdict.get('reason', '')[:50]}")

        if verdict.get("appropriate"):
            approved.append(verdict["uri"])

        time.sleep(0.5)  # 쿼터 여유

    with open("filter_results.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open("approved_uris.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(approved))

    print(f"\n총 {len(results)}개 중 {len(approved)}개 적합 판정")
    print("상세 결과: filter_results.jsonl")
    print("적합 파일 목록: approved_uris.txt")


if __name__ == "__main__":
    main()
