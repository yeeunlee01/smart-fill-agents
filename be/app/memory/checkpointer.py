"""LangGraph 체크포인터 (대화 영속화). Postgres 백엔드로 컨테이너 재시작에도 유지.

graph.ainvoke(비동기)와 맞추려면 AsyncPostgresSaver + AsyncConnectionPool 이 필요하다.
async 풀은 이벤트 루프가 있는 앱 시작 시점(lifespan)에서 init_checkpointer()로 연다.
"""
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings

_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None


async def init_checkpointer() -> AsyncPostgresSaver:
    """앱 시작 시 1회 호출: 풀 오픈 + checkpoints 테이블 생성."""
    global _pool, _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    _pool = AsyncConnectionPool(
        conninfo=settings.postgres_dsn,
        max_size=10,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await _pool.open()
    _checkpointer = AsyncPostgresSaver(_pool)
    await _checkpointer.setup()  # 이미 있으면 무시
    return _checkpointer


def get_checkpointer() -> AsyncPostgresSaver:
    """초기화된 checkpointer 싱글톤 반환 (init_checkpointer 선행 필요)."""
    if _checkpointer is None:
        raise RuntimeError("checkpointer가 초기화되지 않았습니다. 앱 시작 시 init_checkpointer()를 호출하세요.")
    return _checkpointer


def get_pool() -> AsyncConnectionPool:
    """공용 Postgres 커넥션 풀 (templates 등 다른 저장소도 재사용)."""
    if _pool is None:
        raise RuntimeError("Postgres 풀이 초기화되지 않았습니다. 앱 시작 시 init_checkpointer()를 호출하세요.")
    return _pool


async def close_checkpointer() -> None:
    """앱 종료 시 풀 정리."""
    global _pool, _checkpointer
    if _pool is not None:
        await _pool.close()
    _pool = None
    _checkpointer = None
