"""data/raw 문서를 파싱/적재. 실행: python -m scripts.ingest_docs"""
from app.rag.ingest import ingest_documents


def main() -> None:
    # TODO: data/raw 순회 -> PPT/HTML 파싱 -> 청킹 -> ingest_documents
    chunks: list[str] = []
    count = ingest_documents(chunks)
    print(f"[ingest_docs] ingested {count} chunks")


if __name__ == "__main__":
    main()
