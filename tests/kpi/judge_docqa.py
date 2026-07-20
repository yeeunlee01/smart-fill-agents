"""LLM-as-a-Judge: DocQA 결과(jsonl, stdin)의 근거 충실도/질문 관련성 채점.

be 컨테이너 안에서 실행: docker exec -i be python - < judge_docqa.py 형태가 아니라
스크립트 자체를 stdin으로 못 넘기므로, jsonl을 stdin으로 받는 이 파일을 컨테이너에 복사해 실행한다.
출력: 문항별 판정 + 집계 (stdout, json)
"""
import asyncio
import json
import sys

from pydantic import BaseModel, Field

from app.llm.client import get_llm


class Judgement(BaseModel):
    faithful: bool = Field(description="답변이 제시된 근거 인용문(또는 '못 찾음' 선언)에만 기반하며, 근거 없는 추측·창작이 없는가")
    relevant: bool = Field(description="답변이 질문이 묻는 바에 실제로 답하고 있는가 (못 찾았다는 답변은 관련성 없음으로 판정)")
    reason: str = Field(description="한 줄 판정 이유")


JUDGE_SYSTEM = """당신은 RAG 시스템의 답변을 채점하는 평가자입니다.
[질문], [답변], [제시된 근거 인용문]을 보고 두 가지를 판정하세요.

1. faithful (근거 충실도): 답변의 사실 주장이 모두 근거 인용문으로 뒷받침되는가?
   - 근거에 없는 내용을 추측·창작했으면 false.
   - "자료에서 찾을 수 없다"고 정직하게 답한 경우는 true (지어내지 않았으므로).
2. relevant (질문 관련성): 답변이 질문이 묻는 정보를 실제로 제공하는가?
   - "찾을 수 없다"는 답변은 정보를 제공하지 못했으므로 false."""


async def judge_one(llm, row: dict) -> dict:
    quotes = []
    for s in row.get("sources") or []:
        quotes.extend(s.get("texts") or [])
    ev = "\n".join(f"- {q}" for q in quotes) if quotes else "(제시된 근거 없음)"
    reply = row.get("reply", "").split("📎")[0].strip()  # 근거 목록 푸터 제외한 본문만
    user = f"[질문]\n{row['question']}\n\n[답변]\n{reply}\n\n[제시된 근거 인용문]\n{ev}"
    result: Judgement = await llm.ainvoke(
        [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}]
    )
    return {"id": row["id"], "faithful": result.faithful, "relevant": result.relevant, "reason": result.reason}


async def main() -> None:
    rows = [json.loads(l) for l in sys.stdin if l.strip()]
    llm = get_llm(temperature=0).with_structured_output(Judgement)
    out = []
    for row in rows:
        j = await judge_one(llm, row)
        out.append(j)
        print(json.dumps(j, ensure_ascii=False), flush=True)
        await asyncio.sleep(3)
    n = len(out)
    nf = sum(1 for j in out if j["faithful"])
    nr = sum(1 for j in out if j["relevant"])
    print(json.dumps({"total": n, "faithful": nf, "relevant": nr,
                      "faithfulness": round(nf / n, 3), "relevance": round(nr / n, 3)}, ensure_ascii=False))


asyncio.run(main())
