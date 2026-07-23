"""중앙 환경설정. 모든 호스트/키는 환경변수로 주입 (compose 서비스명 대응)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 실행 모드: MODE=personal → 개인 OpenAI(api.openai.com) 사용.
    # 미설정/그 외 값 → 사내 Azure 형식 게이트웨이(skax) 사용.
    mode: str = ""

    # LLM
    openai_api_key: str = ""  # 사내 게이트웨이 api-key (atl-...)
    openai_api_key_personal: str = ""  # 개인 OpenAI 키 (sk-...), MODE=personal일 때 사용
    openai_model: str = "gpt-4o"  # = Azure deployment 이름 (OpenAI에선 모델명)
    openai_embedding_model: str = "text-embedding-3-small"  # = 임베딩 deployment/모델 이름
    azure_openai_endpoint: str = "https://skax.ai-talentlab.com"
    openai_api_version: str = "2024-12-01-preview"
    # 사내 게이트웨이의 자기서명 CA(SK holdings C&C) 신뢰용 PEM 경로.
    # 파일이 없으면 기본 시스템 CA로 폴백한다.
    openai_ca_bundle: str = "/app/certs/sk-ca.pem"

    # Backend
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # Milvus
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "documents"

    # Checkpointer (Postgres)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "app"
    postgres_password: str = "app"
    postgres_db: str = "agents"

    # MinIO (템플릿 원본 파일 저장소 — Milvus 스택의 minio 재사용)
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "templates"

    @property
    def is_personal(self) -> bool:
        """MODE=personal 이면 개인 OpenAI 계정 사용."""
        return self.mode.strip().lower() == "personal"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
