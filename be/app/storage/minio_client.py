"""MinIO 오브젝트 스토리지 — 템플릿 원본 파일(docx 등) 저장.

Milvus 스택에 이미 떠 있는 minio 컨테이너를 재사용한다 (버킷만 분리).
클라이언트는 동기 API이므로 호출부(endpoint)에서 run_in_threadpool로 감싼다.
"""
import io

from minio import Minio
from minio.error import S3Error

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,  # compose 내부 통신 (TLS 없음)
        )
    return _client


def ensure_bucket() -> None:
    c = _get_client()
    if not c.bucket_exists(settings.minio_bucket):
        c.make_bucket(settings.minio_bucket)
        logger.info("MinIO 버킷 생성: %s", settings.minio_bucket)


def put_object(key: str, data: bytes) -> None:
    ensure_bucket()
    _get_client().put_object(
        settings.minio_bucket, key, io.BytesIO(data), length=len(data),
        content_type="application/octet-stream",
    )


def get_object(key: str) -> bytes | None:
    try:
        resp = _get_client().get_object(settings.minio_bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()
    except S3Error as e:
        if e.code in ("NoSuchKey", "NoSuchBucket"):
            return None
        raise


def delete_object(key: str) -> None:
    try:
        _get_client().remove_object(settings.minio_bucket, key)
    except S3Error as e:
        if e.code not in ("NoSuchKey", "NoSuchBucket"):
            raise
