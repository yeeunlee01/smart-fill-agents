"""템플릿 영구 저장소 (Postgres).

- 메타데이터(slot 정의, docx 구조)는 templates 테이블(JSONB)에,
- 원본 파일(docx 등)은 MinIO에 file_key로 저장한다 (DB에는 키만).
API 응답은 프론트가 쓰던 localStorage 객체 형태({name, kind, file_name, file_b64, ...})를 유지한다.
"""
import base64
import json
import uuid

from fastapi.concurrency import run_in_threadpool

from app.memory.checkpointer import get_pool
from app.storage import minio_client

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS templates (
    id         UUID PRIMARY KEY,
    name       TEXT UNIQUE NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'text',
    file_name  TEXT NOT NULL DEFAULT '',
    file_key   TEXT NOT NULL DEFAULT '',
    text_body  TEXT NOT NULL DEFAULT '',
    structure  JSONB,
    slots      JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


async def init_table() -> None:
    async with get_pool().connection() as conn:
        await conn.execute(_CREATE_SQL)


async def _row_to_template(row: dict, with_file: bool = True) -> dict:
    """DB row → 프론트 localStorage와 동일한 형태. 파일은 MinIO에서 읽어 base64로."""
    file_b64 = ""
    if with_file and row["file_key"]:
        data = await run_in_threadpool(minio_client.get_object, row["file_key"])
        if data:
            file_b64 = base64.b64encode(data).decode()
    return {
        "name": row["name"],
        "kind": row["kind"],
        "file_name": row["file_name"],
        "file_b64": file_b64,
        "text": row["text_body"],
        "structure": row["structure"],
        "slots": row["slots"],
    }


async def list_templates() -> list[dict]:
    async with get_pool().connection() as conn:
        cur = await conn.execute("SELECT * FROM templates ORDER BY created_at")
        rows = await cur.fetchall()
    return [await _row_to_template(r) for r in rows]


async def upsert_template(tpl: dict) -> None:
    """이름 기준 upsert. 파일이 있으면 MinIO에 저장하고 키만 DB에 남긴다."""
    name = (tpl.get("name") or "").strip()
    if not name:
        raise ValueError("템플릿 이름이 비어 있습니다.")

    # 기존 파일 키 조회 (교체 시 이전 오브젝트 삭제용)
    async with get_pool().connection() as conn:
        cur = await conn.execute("SELECT file_key FROM templates WHERE name = %s", (name,))
        prev = await cur.fetchone()
    prev_key = prev["file_key"] if prev else ""

    file_b64 = tpl.get("file_b64") or ""
    file_key = ""
    if file_b64:
        data = base64.b64decode(file_b64)
        file_key = f"{uuid.uuid4().hex}_{tpl.get('file_name') or 'template'}"
        await run_in_threadpool(minio_client.put_object, file_key, data)

    async with get_pool().connection() as conn:
        await conn.execute(
            """
            INSERT INTO templates (id, name, kind, file_name, file_key, text_body, structure, slots)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            ON CONFLICT (name) DO UPDATE SET
                kind = EXCLUDED.kind,
                file_name = EXCLUDED.file_name,
                file_key = EXCLUDED.file_key,
                text_body = EXCLUDED.text_body,
                structure = EXCLUDED.structure,
                slots = EXCLUDED.slots,
                updated_at = now()
            """,
            (
                str(uuid.uuid4()),
                name,
                tpl.get("kind") or "text",
                tpl.get("file_name") or "",
                file_key,
                tpl.get("text") or "",
                json.dumps(tpl.get("structure")) if tpl.get("structure") is not None else None,
                json.dumps(tpl.get("slots") or []),
            ),
        )

    # 새 파일로 교체됐으면 이전 오브젝트 정리
    if prev_key and prev_key != file_key:
        await run_in_threadpool(minio_client.delete_object, prev_key)


async def delete_template(name: str) -> bool:
    async with get_pool().connection() as conn:
        cur = await conn.execute("DELETE FROM templates WHERE name = %s RETURNING file_key", (name,))
        row = await cur.fetchone()
    if row is None:
        return False
    if row["file_key"]:
        await run_in_threadpool(minio_client.delete_object, row["file_key"])
    return True
