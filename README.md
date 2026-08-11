# 📖 이야기 읽기 친구 (Literacy Agent)

초등학생 문해력 향상을 위한 **Gemini + RAG 기반 AI 독서 코칭 서비스**

🔗 **배포 링크**: https://literacy-agent-backend-1036470066046.us-central1.run.app/
📂 **API 문서**: [배포 URL]/docs (Swagger UI)


![서비스 화면](./docs/screenshot.png)


---

## 문제 정의

디지털 매체 과몰입으로 인해 초등학생의 어휘력·문해력이 저하되고 있지만,
기존 학습 콘텐츠는 정해진 수준의 문제를 일방적으로 제공하고, 기존 AI
챗봇은 정답을 곧바로 알려줘 아이가 스스로 생각할 기회를 빼앗는다는
한계가 있었습니다.

## 해결 방식

- **RAG 그라운딩**: 한국문학번역원(LTI Korea) KLWAVE의 한국 현대 단편소설
  영문 발췌본을 Vertex AI Search로 검색·그라운딩해, 매번 실제 원문에
  근거한 새로운 지문을 제공 (AI가 지어낸 이야기 아님)
- **학년별 맞춤 번역**: Gemini가 검색된 원문을 저학년(1~3학년)·
  고학년(4~6학년) 눈높이에 맞는 자연스러운 한국어로 재구성
- **소크라테스식 코칭**: 정답을 바로 주지 않고 예측 → 명료화 → 질문 →
  요약의 4단계 대화로 아이가 스스로 사고 과정을 거치도록 유도

## 핵심 기능

| 기능 | 설명 |
|---|---|
| 학년·주제 선택 기반 지문 생성 | RAG 검색 + Gemini 번역 에이전트 |
| 멀티턴 대화형 독해 코칭 | 4단계 코칭 에이전트, 컨텍스트 유지 |
| 콘텐츠 안전 필터링 | 성인 소재 원문 자동 배제 (UNSUITABLE 판정) |
| 그라운딩되지 않은 응답 거부 | 검색 결과 없으면 창작 대신 정직하게 실패 응답 |

## 기술 스택

`Python` `FastAPI` `Gemini 2.5 Flash` `Vertex AI Search (RAG)`
`Cloud Storage` `Cloud Run` `google-genai SDK`

프론트엔드는 별도 프레임워크 없이 정적 HTML/CSS/JS로 구성해 4일 MVP
기간 내 빌드 파이프라인 없이 빠르게 배포 가능하도록 단순화했습니다.

## 아키텍처

```
사용자 브라우저
      │ HTTPS
      ▼
Cloud Run (FastAPI)
      │
      ├─▶ Vertex AI Search (RAG 그라운딩) ─▶ Cloud Storage (원문 텍스트)
      │
      └─▶ Gemini 2.5 Flash (번역·코칭 생성)

인증: Cloud IAM (ADC) — API 키 미사용
```

## 기술적으로 풀었던 문제

**1. LLM 그라운딩 위반(환각) 대응**
검색 결과가 없을 때 모델이 임의로 동화를 창작하는 사례를 발견
("아기 토끼와 작은 새" — 실제 데이터셋과 무관한 내용 생성). "지어내는
것은 아이들에게 거짓 정보를 주는 것과 같다"는 근거를 프롬프트에 명시적
으로 추가한 뒤, 동일 질의 5회 반복 테스트에서 모두 정직한 실패 응답으로
재현됨을 확인했습니다.

**2. 콘텐츠 안전 필터링**
원본 데이터가 성인 대상 문학이라 음주·자해·폭력 등 소재가 포함된 원문이
검색될 수 있었습니다. 번역 에이전트 프롬프트에 콘텐츠 적합성 검사 규칙을
추가해, 부적합 판정 시 다음 순위 후보로 자동 재시도하도록 설계했습니다.

**3. 민감 정보 관리**
GCP 프로젝트 ID·리소스 경로가 코드에 하드코딩되어 공개 저장소에 노출된
것을 발견하고, 환경변수(`.env`)로 분리한 뒤 `git filter-repo`로 커밋
히스토리 전체에서 값을 제거하는 작업까지 완료했습니다.

**4. 플랫폼 제약 대응**
GCP Agent Studio(콘솔 기반 에이전트 플랫폼) 연동을 시도했으나, 플랫폼이
자동 등록한 도구 이름과 모델이 호출한 도구 이름이 불일치하는 버그로
도구 호출이 실패했습니다. 원인이 플랫폼 내부 이슈로 판단해, 이미 검증된
파이썬 직접 구현(`google-genai` + `retrieval_query`) 방식으로 롤백해
최종 제출했습니다.

## 한계 및 다음 단계

- 세션 상태를 현재 Cloud Run 프로세스 메모리에 저장 중 → Firestore
  전환으로 다중 인스턴스 확장 필요
- 원문 데이터셋 21건으로 규모가 작아 흔한 아동 주제도 검색 결과가 없는
  경우 존재 → 데이터셋 확장 예정
- 응답 시간 목표(5초) 대비 실측 10~15초로 미달성 → 병렬 처리 등 최적화 필요
- 서술형 답안 논술 첨삭 기능은 MVP 범위에서 보류 (`501` 스텁만 존재)

## 로컬 실행

```bash
git clone https://github.com/chajinhee/literacy-agent.git
cd literacy-agent
pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env
# .env를 열어 PROJECT_ID, RAG_LOCATION, GEMINI_LOCATION, RAG_CORPUS_ID 값을 채우세요

uvicorn main:app --reload --port 8080
# http://localhost:8080 접속, /docs 에서 API 테스트
```

## 배포

```bash
gcloud run deploy literacy-agent-backend \
  --source . \
  --region us-central1 \
  --set-env-vars PROJECT_ID=<YOUR_PROJECT_ID>,RAG_LOCATION=asia-northeast3,GEMINI_LOCATION=us-central1,RAG_CORPUS_ID=<YOUR_RAG_CORPUS_ID> \
  --allow-unauthenticated \
  --min-instances 1 --max-instances 1 \
  --memory 512Mi --timeout 60
```

## 데이터 및 라이선스

한국문학번역원(LTI Korea) KLWAVE 데이터셋을 교육 목적 비영리 MVP
프로젝트에 한해 사용했습니다. 총 286건 중 Gemini를 활용해 초등학생
읽기에 적합한 21건을 1차 필터링해 사용했습니다.
