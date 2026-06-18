"""Milvus 컬렉션 초기화. 실행: python -m scripts.init_milvus"""
from app.core.config import settings
from app.rag.milvus_client import get_client


def main() -> None:
    client = get_client()
    # TODO: 컬렉션 스키마 정의 및 생성 (없으면 create)
    print(f"[init_milvus] target collection: {settings.milvus_collection}")
    print(f"[init_milvus] client: {client}")


if __name__ == "__main__":
    main()
