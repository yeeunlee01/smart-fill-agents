"""문서 업로드/적재 엔드포인트. 첨부 파일을 파싱·임베딩해 Milvus에 적재한다."""
from fastapi import APIRouter, File, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.rag.ingest import ingest_file
from app.rag.milvus_client import drop_collection

router = APIRouter()


@router.post("")
async def upload_documents(files: list[UploadFile] = File(...)) -> dict:
    results = []
    for f in files:
        data = await f.read()
        try:
            # 블로킹(파싱/임베딩/Milvus) → 스레드풀에서 실행
            chunks = await run_in_threadpool(ingest_file, f.filename, data)
            results.append({"doc": f.filename, "chunks": chunks, "ok": True})
        except Exception as e:  # noqa: BLE001 — 형식 미지원/파싱 실패 등 개별 보고
            results.append({"doc": f.filename, "chunks": 0, "ok": False, "error": str(e)})
    return {"ingested": results, "total": sum(r["chunks"] for r in results)}


@router.delete("")
async def clear_documents() -> dict:
    """적재된 모든 문서(컬렉션)를 비운다. 대화 재시작 시 호출."""
    await run_in_threadpool(drop_collection)
    return {"cleared": True}
