"""LangGraph 체크포인터 (대화 영속화). Postgres 백엔드로 컨테이너 재시작에도 유지."""
from langgraph.checkpoint.postgres import PostgresSaver

from app.core.config import settings

_checkpointer: PostgresSaver | None = None


def get_checkpointer() -> PostgresSaver:
    """Postgres 기반 checkpointer 싱글톤.

    최초 1회 setup()으로 테이블 생성 필요.
    """
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = PostgresSaver.from_conn_string(settings.postgres_dsn)
        # _checkpointer.setup()  # 최초 실행 시 테이블 생성
    return _checkpointer
