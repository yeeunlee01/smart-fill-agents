"""템플릿 관련 엔드포인트.

- GET ''   : 저장된 템플릿 목록 (Postgres + MinIO)
- PUT ''   : 템플릿 저장/수정 (이름 기준 upsert)
- DELETE '': 템플릿 삭제 (?name=)
- /extract : 업로드 파일에서 평문 텍스트만 추출 (편집기 '템플릿 원문' 채우기용)
- /split   : 평문 원문 → slot 분할 (텍스트 방식, element_ids 없음)
- /detect  : 파일 → 공통 구조 파싱 → 논리 블록(slot) 분할 (서식 보존, 채우기 단위)
- /pdf     : docx → PDF 미리보기

구조 파싱은 app.templates.parsers 가 포맷별로 처리한다 (지금은 docx만).
분할(segment)·빈칸 감지는 포맷 무관 공통 로직.
"""
import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.agents.prompts.templates import SPLIT_SYSTEM_PROMPT
from app.db import templates as templates_db
from app.llm.client import get_llm
from app.rag.parse import parse_file
from app.templates.inject import fill_docx
from app.templates.parsers import parse_template
from app.templates.segment import detect_regions, segment_structure
from app.templates.topdf import docx_to_pdf

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

router = APIRouter()


def _ext(filename: str) -> str:
    return filename.lower().rsplit(".", 1)[-1] if "." in filename else ""


class _Slot(BaseModel):
    name: str = Field(description="원문의 항목/제목 텍스트를 그대로 (재작성·축약 금지)")
    definition: str = Field(description="이 항목에 채울 내용에 대한 한 줄 설명")


class _SplitResult(BaseModel):
    slots: list[_Slot]


class SplitRequest(BaseModel):
    text: str


class TemplateSaveRequest(BaseModel):
    """프론트 localStorage와 동일한 형태 (마이그레이션 호환)."""

    name: str
    kind: str = "text"
    file_name: str = ""
    file_b64: str = ""
    text: str = ""
    structure: dict | None = None
    slots: list = Field(default_factory=list)


@router.get("")
async def list_templates() -> list[dict]:
    """저장된 템플릿 목록 (원본 파일 base64 포함)."""
    return await templates_db.list_templates()


@router.put("")
async def save_template(req: TemplateSaveRequest) -> dict:
    """템플릿 저장/수정 (이름 기준 upsert). 파일은 MinIO, 메타는 Postgres."""
    try:
        await templates_db.upsert_template(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "name": req.name}


@router.delete("")
async def remove_template(name: str) -> dict:
    """템플릿 삭제 (?name=...)."""
    deleted = await templates_db.delete_template(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"템플릿 '{name}'이(가) 없습니다.")
    return {"ok": True}


@router.post("/extract")
async def extract_template(file: UploadFile = File(...)) -> dict:
    """업로드한 템플릿 파일에서 평문 텍스트를 추출해 반환."""
    data = await file.read()
    try:
        # 파싱(블로킹) → 스레드풀
        segments = await run_in_threadpool(parse_file, file.filename, data)
    except ValueError as e:  # 미지원 형식
        raise HTTPException(status_code=400, detail=str(e))
    text = "\n".join(t for t, _loc in segments if t.strip())
    return {"filename": file.filename, "text": text}


@router.post("/split")
async def split_template(req: SplitRequest) -> dict:
    """템플릿 원문을 채울 항목(slot)으로 분할. name은 원문 그대로, definition은 채우기 가이드."""
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="원문이 비어 있습니다.")
    llm = get_llm().with_structured_output(_SplitResult)
    result: _SplitResult = await llm.ainvoke(
        [
            {"role": "system", "content": SPLIT_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
    )
    return {"slots": [s.model_dump() for s in result.slots]}


@router.post("/detect")
async def detect_template(file: UploadFile = File(...)) -> dict:
    """업로드한 템플릿을 원형 보존한 채 의미 단위 구간(segment)으로 분할.

    지원 포맷은 app.templates.parsers 가 결정한다 (지금은 docx). 미지원이면 400.

    반환:
    - structure: 읽기 순서대로의 요소들(제목/문단/표, 원문 텍스트·표 구조 보존) — 색상 미리보기용
    - segments:  [{name, definition, element_ids}] — 각 구간이 어떤 요소들을 묶었는지 (채우기 단위)
    """
    data = await file.read()
    try:
        structure = await run_in_threadpool(parse_template, file.filename or "", data)
    except ValueError as e:  # 미지원 형식
        raise HTTPException(status_code=400, detail=str(e))
    segments = await segment_structure(structure)
    segments = await detect_regions(structure, segments)  # 채울 영역(fixed/fill) 분해 부착
    return {"structure": structure, "segments": segments}


@router.post("/pdf")
async def template_pdf(file: UploadFile = File(...)) -> Response:
    """docx → PDF 변환 (미리보기 페이지 렌더용)."""
    if _ext(file.filename) != "docx":
        raise HTTPException(status_code=400, detail="PDF 변환은 .docx만 지원합니다.")
    data = await file.read()
    try:
        pdf = await run_in_threadpool(docx_to_pdf, data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"PDF 변환 실패: {e}")
    # 디버그용: 변환된 PDF를 /data 에 저장 (LibreOffice 변환 결과를 직접 열어 확인)
    try:
        import os
        stem = os.path.splitext(os.path.basename(file.filename or "template"))[0] or "template"
        with open(f"/data/{stem}.pdf", "wb") as f:
            f.write(pdf)
    except Exception:  # noqa: BLE001 — 저장 실패해도 응답은 정상 진행
        pass
    return Response(content=pdf, media_type="application/pdf")


@router.post("/fill")
async def fill_template(file: UploadFile = File(...), injections: str = Form("[]")) -> Response:
    """템플릿 docx + 채운 내용(injections) → anchor 위치에 in-place 주입된 docx 반환.

    injections: [{"element_ids": [int], "content": str}]  (프론트가 slot↔내용 매핑해 전달)
    반환된 docx는 프론트에서 /pdf로 미리보기 + 다운로드에 쓴다.
    """
    if _ext(file.filename) != "docx":
        raise HTTPException(status_code=400, detail="채우기 렌더는 .docx 템플릿만 지원합니다.")
    data = await file.read()
    try:
        injs = json.loads(injections)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"injections JSON 파싱 실패: {e}")
    try:
        filled = await run_in_threadpool(fill_docx, data, injs)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"주입 실패: {e}")
    return Response(content=filled, media_type=_DOCX_MIME)
