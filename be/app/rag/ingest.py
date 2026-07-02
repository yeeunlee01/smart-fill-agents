"""문서 적재 파이프라인: 파싱 -> 청킹 -> 임베딩 -> Milvus insert."""
from app.core.config import settings
from app.core.logging import get_logger
from app.rag.chunk import chunk_text
from app.rag.embeddings import embed
from app.rag.milvus_client import ensure_collection, get_client
from app.rag.parse import parse_file

logger = get_logger(__name__)


def ingest_file(filename: str, data: bytes) -> int:
    """업로드된 파일 1개를 파싱·청킹·임베딩해 Milvus에 적재. 적재한 청크 수 반환."""
    segments = parse_file(filename, data)  # [(text, location), ...]

    rows: list[dict] = []
    for text, location in segments:
        for chunk in chunk_text(text):
            rows.append({"text": chunk, "doc": filename, "location": location})
    if not rows:
        logger.info("ingest: %s → 추출된 청크 없음", filename)
        return 0

    vectors = embed([r["text"] for r in rows])
    ensure_collection(dim=len(vectors[0]))
    for r, v in zip(rows, vectors):
        r["vector"] = v

    client = get_client()
    # 같은 파일명의 기존 청크 제거 후 적재 (재업로드 시 중복 방지)
    client.delete(collection_name=settings.milvus_collection, filter=f'doc == "{filename}"')
    client.insert(collection_name=settings.milvus_collection, data=rows)
    logger.info("ingest: %s → %d 청크 적재", filename, len(rows))
    return len(rows)
