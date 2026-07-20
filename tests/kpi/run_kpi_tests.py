"""KPI 측정: 라우팅 정확도 + DocQA 근거 수집.

사용법: python run_kpi_tests.py [routing|docqa|all]
결과: data/시연/ 에 jsonl로 기록 (라우팅은 즉시 집계 출력).

- 라우팅: 빈 slot 템플릿을 첨부해 TemplateFill로 분류돼도 실제 채우기가 돌지 않게 함
  (fill_dispatch가 slot 0개면 바로 aggregator로 감) → 분류 결과(intent)만 저렴하게 수집.
- DocQA: /chat/stream 의 done 이벤트에서 reply + sources(근거)를 수집.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://localhost:8001/api/v1"
OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "시연"
DOCS = ["제안요청서_RFP.docx", "수행실적서.docx", "투입인력표.docx", "회사소개서.pdf"]
EMPTY_TEMPLATE = {"name": "사업제안요약서_템플릿", "slots": []}

ROUTING_CASES = [
    ("R1", "사업제안요약서 템플릿을 이 문서들로 채워줘", "TemplateFill"),
    ("R2", "첨부한 자료로 제안요약서 작성해줘", "TemplateFill"),
    ("R3", "템플릿 채우기 시작해줘", "TemplateFill"),
    ("R4", "이 RFP랑 회사소개서 가지고 사업제안요약서 만들어줘", "TemplateFill"),
    ("R5", "등록해둔 템플릿에 방금 올린 문서 내용 넣어줘", "TemplateFill"),
    ("R6", "제안요약서 초안 뽑아줘", "TemplateFill"),
    ("R7", "이 자료들로 문서 양식 채워서 완성본 만들어줘", "TemplateFill"),
    ("R8", "수행실적서 내용 반영해서 템플릿 다시 채워줘", "TemplateFill"),
    ("R9", "사업제안요약서 양식대로 작성 부탁해", "TemplateFill"),
    ("R10", "이 문서로 요약서 만들어줘", "TemplateFill"),
    ("R11", "RFP에서 사업 예산이 얼마라고 나와 있어?", "DocQA"),
    ("R12", "이 문서 요약해줘", "DocQA"),
    ("R13", "수행실적서에 나온 프로젝트 3개를 정리해줘", "DocQA"),
    ("R14", "제안서 제출 마감일이 언제야?", "DocQA"),
    ("R15", "투입 인력 중에 PM이 누구야?", "DocQA"),
    ("R16", "회사소개서 보고 회사 연혁 알려줘", "DocQA"),
    ("R17", "이번 사업의 비기능 요구사항이 뭐뭐 있어?", "DocQA"),
    ("R18", "첨부한 문서에서 하자보수 기간 찾아줘", "DocQA"),
    ("R19", "RFP랑 수행실적서 비교해서 우리가 부합하는 부분 알려줘", "DocQA"),
    ("R20", "이 PDF에 담당자 연락처 나와 있어?", "DocQA"),
    ("R21", "안녕!", "Chat"),
    ("R22", "고마워, 수고했어", "Chat"),
    ("R23", "너는 뭘 할 수 있어?", "Chat"),
    ("R24", "제안서 잘 쓰는 일반적인 팁 좀 알려줘", "Chat"),
    ("R25", "RFP가 뭐의 약자야?", "Chat"),
    ("R26", "협상에 의한 계약이 무슨 뜻이야?", "Chat"),
    ("R27", "방금 답변 더 짧게 다시 말해줘", "Chat"),
    ("R28", "콜드체인이 뭐야?", "Chat"),
    ("R29", "오늘 할 일이 많네", "Chat"),
    ("R30", "좋은 제안서 목차 구성 예시 들어줄래?", "Chat"),
]

DOCQA_CASES = [
    ("Q1", "이번 사업의 예산은 얼마야?"),
    ("Q2", "제안서 제출 마감일이 언제야?"),
    ("Q3", "사업 기간은 어떻게 돼?"),
    ("Q4", "발주기관이 어디야?"),
    ("Q5", "대금 지급 조건을 알려줘"),
    ("Q6", "하자보수 기간은 얼마나 돼?"),
    ("Q7", "제안서 분량 제한이 있어?"),
    ("Q8", "시스템 성능 요구사항이 뭐야?"),
    ("Q9", "이번 사업 범위에서 제외되는 건 뭐야?"),
    ("Q10", "제안서 평가에서 배점이 가장 높은 항목은?"),
    ("Q11", "콜드체인 온도관제 플랫폼의 발주처는 어디였어?"),
    ("Q12", "부산항만공사 사업의 사업 금액은 얼마였어?"),
    ("Q13", "WMS 고도화 사업은 언제 수행했고 발주처는 어디야?"),
    ("Q14", "세 실적 중 이번 사업과 기술적으로 가장 유사하다고 강조된 실적은?"),
    ("Q15", "이 사업의 PM은 누구야?"),
    ("Q16", "QA 담당자의 투입률은 얼마야?"),
    ("Q17", "기술 리드는 누구고 어떤 경력이야?"),
    ("Q18", "테크노브릿지는 언제 설립됐어?"),
    ("Q19", "테크노브릿지 대표이사는 누구야?"),
    ("Q20", "임직원 수는 몇 명이야?"),
    ("Q21", "콜드체인 분야로 사업을 확장한 건 언제야?"),
    ("Q22", "영업 담당자 연락처를 알려줘"),
    ("Q23", "RFP가 요구하는 유사 수행실적에 해당하는 우리 실적은 몇 건이야?"),
    ("Q24", "RFP의 온·습도 실시간 모니터링 요구를 우리가 수행할 수 있다는 근거는?"),
    ("Q25", "100% 투입되는 인력은 총 몇 명이야?"),
]


def post_json(path: str, payload: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def post_stream_done(path: str, payload: dict, timeout: int = 300) -> dict:
    """SSE 스트림에서 마지막 done(또는 error) 이벤트를 반환."""
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    done = {}
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data: "):
                continue
            ev = json.loads(line[len("data: "):])
            if ev.get("type") in ("done", "error"):
                done = ev
    return done


def run_routing() -> None:
    out = OUT_DIR / "kpi_routing_결과.jsonl"
    results = []
    with out.open("w") as f:
        for rid, text, label in ROUTING_CASES:
            t0 = time.time()
            try:
                res = post_json("/chat", {"message": text, "documents": DOCS, "template": EMPTY_TEMPLATE})
                intent = res.get("intent")
            except Exception as e:  # noqa: BLE001
                intent = f"ERROR: {e}"
            row = {
                "id": rid, "message": text, "expected": label, "actual": intent,
                "match": intent == label, "sec": round(time.time() - t0, 1),
            }
            results.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{rid}: expected={label} actual={intent} {'O' if row['match'] else 'X'}", flush=True)
            time.sleep(4)
    n_ok = sum(r["match"] for r in results)
    print(f"\n라우팅 정확도: {n_ok}/{len(results)} = {n_ok / len(results):.1%}", flush=True)


def run_docqa() -> None:
    out = OUT_DIR / "kpi_docqa_결과.jsonl"
    with out.open("w") as f:
        for qid, question in DOCQA_CASES:
            t0 = time.time()
            try:
                ev = post_stream_done("/chat/stream", {"message": question, "documents": DOCS})
                row = {
                    "id": qid, "question": question,
                    "reply": ev.get("reply", ""), "intent": ev.get("intent"),
                    "sources": [
                        {"doc": s.get("doc"), "location": s.get("location"), "texts": s.get("texts", [])}
                        for s in ev.get("sources", [])
                    ],
                    "error": ev.get("error"),
                    "sec": round(time.time() - t0, 1),
                }
            except Exception as e:  # noqa: BLE001
                row = {"id": qid, "question": question, "error": str(e), "sec": round(time.time() - t0, 1)}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            n_src = len(row.get("sources") or [])
            print(f"{qid}: intent={row.get('intent')} sources={n_src} sec={row['sec']}", flush=True)
            time.sleep(8)  # TPM 여유
    print("\nDocQA 수집 완료 →", out, flush=True)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("routing", "all"):
        run_routing()
    if mode in ("docqa", "all"):
        run_docqa()
