# smart-fill-agents

여러 형태의 입력 문서(PPT, HTML, etc)를 읽고 원하는 템플릿에 맞게 자동으로 채워주는 멀티 에이전트 시스템.

오케스트레이션 워크플로우 + supervisor 라우터 구조(LangGraph).

## 스택

| 영역 | 기술 |
|------|------|
| 에이전트 | LangGraph (멀티에이전트 + supervisor router) |
| LLM | GPT (OpenAI) |
| Backend | FastAPI |
| Frontend | Streamlit |
| VectorDB | Milvus |

## 구조

```
be/        FastAPI + LangGraph (에이전트 핵심)
fe/        Streamlit UI
docker/    인프라 설정/볼륨
scripts/   문서 적재 등 운영 스크립트
```

## 실행

```bash
cp .env.example .env      # 값 채우기 (OPENAI_API_KEY 등)
make up                   # 전체 스택 기동 (compose)
```

- Frontend: http://localhost:8501
- Backend docs: http://localhost:8000/docs

## 컨테이너 구성 (compose)

be, fe, milvus, etcd, minio, postgres
