"""Milvus 연결/컬렉션 관리."""
from functools import lru_cache

from pymilvus import DataType, MilvusClient

from app.core.config import settings


@lru_cache
def get_client() -> MilvusClient:
    return MilvusClient(uri=f"http://{settings.milvus_host}:{settings.milvus_port}")


def ensure_collection(dim: int) -> None:
    """컬렉션이 없으면 스키마+인덱스로 생성한다 (멱등).

    필드: id(auto) / vector(dim) / text(청크 본문) / doc(파일명) / location(위치 표시)
    """
    client = get_client()
    name = settings.milvus_collection
    if client.has_collection(name):
        return

    schema = client.create_schema(auto_id=True, enable_dynamic_field=False)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dim)
    schema.add_field("text", DataType.VARCHAR, max_length=8192)
    schema.add_field("doc", DataType.VARCHAR, max_length=512)
    schema.add_field("location", DataType.VARCHAR, max_length=256)

    index_params = client.prepare_index_params()
    index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")

    client.create_collection(name, schema=schema, index_params=index_params)


def drop_collection() -> None:
    """컬렉션을 통째로 삭제한다 (대화 재시작 시 적재 데이터 비우기). 다음 적재 때 자동 재생성."""
    client = get_client()
    if client.has_collection(settings.milvus_collection):
        client.drop_collection(settings.milvus_collection)
