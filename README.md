# 이야기 읽기 친구 — 초등학생 문해력 학습 에이전트

한국문학번역원(KLWAVE) 한국 현대 단편소설 발췌본을 RAG로 그라운딩하여, 초등학생 학년별 눈높이에 맞는 한국어 지문으로 각색하고, 정답을 바로 주지 않는 4단계(예측→명료화→질문→요약) 대화형 코칭으로 문해력 학습을 돕는 Gemini 기반 AI 튜터입니다.

GCP PBL(Project Based Learning) 1차 MVP 프로젝트로 제작되었습니다.

## 주요 기능

- **RAG 기반 원문 검색·그라운딩**: Vertex AI Search로 학년·주제에 맞는 실제 원문 구절 검색
- **번역/각색 에이전트**: 원문을 저학년(1~3학년)/고학년(4~6학년) 눈높이의 한국어 지문으로 재구성
- **코칭 에이전트**: 예측→명료화→질문→요약 단계로 정답을 바로 주지 않고 스스로 사고하도록 유도
- **안전 필터**: 음주·자해·성적·폭력 등 아동에게 부적절한 원문은 자동으로 걸러내고, 검색 결과가 없으면 지어내지 않고 정직하게 실패를 알림

미구현 상태인 기능(서술형 논술 첨삭, 학습 이력 저장 등)은 기획 문서의 SECTION 05·14를 참고하세요.

## 아키텍처

```
[사용자 브라우저]
      │  (정적 HTML/JS 로드)
      ▼
[Cloud Run: FastAPI 백엔드]
   ├─ GET  /               → 정적 웹 UI 서빙
   ├─ POST /api/passage     → RAG 검색 → Gemini 2.5 Flash(번역 에이전트) → 지문 반환
   ├─ POST /api/coach/turn  → Gemini 2.5 Flash(코칭 에이전트) → 대화 응답
   └─ POST /api/essay/feedback → 501 (미구현)
      │
      ▼
[Vertex AI Search 데이터 스토어] ── 원문 검색 ──▶ [Cloud Storage]
```

인증은 API 키 없이 Cloud Run 서비스 계정(ADC)으로 처리됩니다.

## 기술 스택

| 영역 | 기술 |
|---|---|
| 백엔드 | Python 3.12, FastAPI, uvicorn |
| AI 모델 | Gemini 2.5 Flash (Vertex AI) |
| 검색/그라운딩 | Vertex AI Search |
| 데이터 저장 | Cloud Storage |
| 배포 | Cloud Run (소스 기반 배포) |
| 프론트엔드 | 정적 HTML/CSS/JS (빌드 도구 없음) |

## 사전 준비

- Google Cloud 프로젝트 (Vertex AI API, Cloud Run API, Cloud Build API 사용 설정)
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) 설치 및 인증(`gcloud auth login`)
- Python 3.12

## 1. 필수 IAM 권한 (최초 1회)

Cloud Run이 소스 배포·Vertex AI 호출을 하려면 아래 권한이 필요합니다. `{PROJECT_ID}`, `{PROJECT_NUMBER}`는 본인 프로젝트 값으로 바꿔주세요 (`gcloud projects describe {PROJECT_ID} --format="value(projectNumber)"`로 확인).

```bash
# Cloud Run 소스 배포용 (Cloud Build)
gcloud projects add-iam-policy-binding {PROJECT_ID} \
  --member="serviceAccount:{PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/cloudbuild.builds.builder"

# Vertex AI(Gemini, RAG 검색) 호출용
gcloud projects add-iam-policy-binding {PROJECT_ID} \
  --member="serviceAccount:{PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

## 2. 데이터 준비 (최초 1회)

1. KLWAVE API로 원문 수집 후 `filter_klwave.py`로 Gemini 기반 초등학생 적합성 필터링 실행
2. 필터링된 원문 텍스트를 Cloud Storage 버킷에 `.txt`로 업로드
3. Vertex AI Search 데이터 스토어 생성 후 버킷과 연결하여 인덱싱

## 3. 로컬 실행

```bash
pip install -r requirements.txt
```

`translation_agent.py`, `coaching_agent.py` 상단의 `PROJECT_ID`, `LOCATION`을 본인 환경에 맞게 수정한 뒤:

```bash
uvicorn main:app --reload --port 8080
```

브라우저에서 `http://localhost:8080` 접속(웹 UI), `http://localhost:8080/docs` 접속(API 테스트, Swagger UI).

## 4. 에이전트 단독 테스트

```bash
python3 translation_agent.py   # 번역 에이전트만 테스트
python3 coaching_agent.py      # 코칭 에이전트 대화형 테스트 (직접 입력)
```

## 5. Cloud Run 배포

```bash
gcloud run deploy literacy-agent-backend \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --min-instances 1 --max-instances 1 \
  --memory 512Mi --timeout 60
```

> `--min-instances 1`은 세션이 Cloud Run 프로세스 메모리에 저장되기 때문에 임시로 걸어둔 조치입니다. 자세한 이유는 아래 "알려진 한계"를 참고하세요.

배포 후 확인:

```bash
curl {SERVICE_URL}/health   # {"status": "ok"} 나오면 정상
```

## 알려진 한계

- **세션 비영속성**: 코칭 세션이 Firestore가 아닌 Cloud Run 프로세스 메모리에 저장되어, 다중 인스턴스로 확장하면 대화가 끊길 수 있습니다. 현재는 인스턴스 1개로 고정해 운영 중입니다.
- **데이터셋 규모**: 초등학생 적합성 필터링을 통과한 원문이 21건뿐이라, 흔한 주제(예: "동물 친구와의 우정")도 검색 결과가 없을 수 있습니다. 이 경우 지어내지 않고 정직하게 실패를 알리도록 설계되어 있습니다.
- **응답 시간**: RAG 검색과 Gemini 생성이 순차 처리되어 지문 생성에 약 10~15초가 소요됩니다.
- **서술형 논술 첨삭(F-04)**: 아직 구현되지 않았으며, 해당 엔드포인트는 501을 반환합니다.

프로젝트 배경, 문제 정의, 검증 결과, 후반기 계획 등 자세한 내용은 프로젝트 기획서·결과보고서를 참고하세요.

## 데이터 및 라이선스

- 원문 데이터: 한국문학번역원(LTI Korea) KLWAVE — 비영리 교육용 MVP 프로젝트 목적으로만 사용
- 본 프로젝트는 학습 목적의 MVP이며, 상업적 이용을 위해서는 별도의 데이터 이용 허가가 필요합니다

## 프로젝트 구조

```
.
├── main.py                 # FastAPI 백엔드 (엔드포인트 정의)
├── translation_agent.py    # 번역/각색 에이전트 (RAG 검색 + Gemini)
├── coaching_agent.py       # 코칭 에이전트 (멀티턴 대화)
├── filter_klwave.py        # 데이터 준비: Gemini 기반 적합성 필터링
├── static/index.html       # 웹 UI
├── requirements.txt
├── Dockerfile
└── .dockerignore
```

※ 이 프로젝트는 실습용 GCP 프로젝트를 사용하며, 코드 내 프로젝트 ID는 수업 과제 제출 목적으로만 유효합니다.
