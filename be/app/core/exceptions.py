"""도메인 예외 정의."""


class AppError(Exception):
    """애플리케이션 공통 베이스 예외."""


class AgentError(AppError):
    """에이전트 실행 중 오류."""


class RetrievalError(AppError):
    """Milvus 검색/적재 오류."""
