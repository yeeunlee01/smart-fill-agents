"""의존성 주입 (DI). 라우터에서 서비스/리소스를 주입받을 때 사용."""
from app.services.chat_service import ChatService


def get_chat_service() -> ChatService:
    return ChatService()
