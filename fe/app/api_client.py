"""Backend 호출 클라이언트. UI는 backend 내부 코드를 import하지 않고 HTTP로만 통신."""
import httpx

from config import BACKEND_URL


def send_chat(message: str, thread_id: str | None = None) -> dict:
    resp = httpx.post(
        f"{BACKEND_URL}/api/v1/chat",
        json={"message": message, "thread_id": thread_id},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()
