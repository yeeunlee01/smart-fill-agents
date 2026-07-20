"""KPI 측정: 템플릿 채우기 1회 실행 → 소요 시간 + 근거 제시율 수집.

프론트와 동일한 흐름: /templates/detect로 slot 감지 → /chat/stream으로 채우기.
결과: data/시연/kpi_fill_결과.json
"""
import json
import time
import urllib.request
import uuid
from pathlib import Path

BASE = "http://localhost:8001/api/v1"
DATA = Path(__file__).resolve().parents[2] / "data" / "시연"
TEMPLATE_DOCX = DATA / "사업제안요약서_템플릿.docx"
DOCS = ["제안요청서_RFP.docx", "수행실적서.docx", "투입인력표.docx", "회사소개서.pdf"]


def post_multipart(path: str, filepath: Path) -> dict:
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filepath.name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + filepath.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        BASE + path, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode())


def post_stream_done(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    done = {}
    with urllib.request.urlopen(req, timeout=900) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data: "):
                continue
            ev = json.loads(line[len("data: "):])
            if ev.get("type") in ("done", "error"):
                done = ev
    return done


def main() -> None:
    t0 = time.time()
    det = post_multipart("/templates/detect", TEMPLATE_DOCX)
    t_detect = time.time() - t0
    segments = det.get("segments", [])
    print(f"detect: slot {len(segments)}개, {t_detect:.1f}s", flush=True)

    template = {"name": "사업제안요약서", "slots": segments}
    t1 = time.time()
    done = post_stream_done("/chat/stream", {
        "message": "이 문서들로 사업제안요약서 템플릿을 채워줘",
        "documents": DOCS,
        "template": template,
    })
    t_fill = time.time() - t1

    filled = done.get("filled", [])
    written = [f for f in filled if not f.get("skipped") and (f.get("content") or "").strip()]
    ok = [f for f in written if "찾지 못했" not in (f.get("content") or "")]
    with_src = [f for f in ok if f.get("sources")]

    out = {
        "detect_sec": round(t_detect, 1),
        "fill_sec": round(t_fill, 1),
        "total_sec": round(time.time() - t0, 1),
        "slots_total": len(filled),
        "slots_written": len(written),
        "slots_answered": len(ok),
        "slots_with_sources": len(with_src),
        "intent": done.get("intent"),
        "error": done.get("error"),
        "filled": filled,
    }
    (DATA / "kpi_fill_결과.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"fill: {t_fill:.1f}s / 작성 {len(written)} / 성공 {len(ok)} / 근거 {len(with_src)}", flush=True)
    for f in written:
        n_src = len(f.get("sources") or [])
        print(f"  - [{f.get('idx')}] {f.get('name')}: sources={n_src}", flush=True)


if __name__ == "__main__":
    main()
