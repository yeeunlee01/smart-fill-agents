.PHONY: up down logs build ingest test lint fmt

# ===== Docker =====
up:            ## 전체 스택 기동
	docker compose up -d --build

down:          ## 전체 스택 종료
	docker compose down

logs:          ## 로그 follow
	docker compose logs -f be fe

build:         ## 이미지 빌드만
	docker compose build

# ===== App =====
ingest:        ## Milvus에 문서 적재
	docker compose exec be python -m scripts.ingest_docs

init-milvus:   ## Milvus 컬렉션 초기화
	docker compose exec be python -m scripts.init_milvus

# ===== Dev =====
test:
	cd be && pytest

lint:
	ruff check be

fmt:
	ruff format be
