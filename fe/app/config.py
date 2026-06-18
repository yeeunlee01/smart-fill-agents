"""프론트엔드 설정. backend 주소는 환경변수로 주입 (compose: backend 서비스명)."""
import os

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
