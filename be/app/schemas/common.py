"""공통 스키마."""
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str
