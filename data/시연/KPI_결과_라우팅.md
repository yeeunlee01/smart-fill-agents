# KPI 측정 결과 — 멀티 에이전트 라우팅 정확도

- 측정일: 2026-07-20
- 방법: 표본 발화 30건을 `POST /api/v1/chat`으로 전송, 응답의 `intent`(supervisor 분류 결과)를 정답 라벨과 비교
- 조건: 참고 문서 4개 첨부 + 빈 slot 템플릿 선택 상태 (실제 사용 상황과 동일하게 분류만 수행)
- 원본 로그: `kpi_routing_결과.jsonl`

## 결과 요약

| 지표 | 값 |
|---|---|
| **라우팅 정확도** | **30/30 = 100%** |
| 목표 | ≥ 90% (27/30) |
| 판정 | **목표 달성** |

라벨별: TemplateFill 10/10 · DocQA 10/10 · Chat 10/10

## 문항별 상세

| 번호 | 발화 | 정답 | 분류 결과 | 판정 |
|---|---|---|---|---|
| R1 | 사업제안요약서 템플릿을 이 문서들로 채워줘 | TemplateFill | TemplateFill | O |
| R2 | 첨부한 자료로 제안요약서 작성해줘 | TemplateFill | TemplateFill | O |
| R3 | 템플릿 채우기 시작해줘 | TemplateFill | TemplateFill | O |
| R4 | 이 RFP랑 회사소개서 가지고 사업제안요약서 만들어줘 | TemplateFill | TemplateFill | O |
| R5 | 등록해둔 템플릿에 방금 올린 문서 내용 넣어줘 | TemplateFill | TemplateFill | O |
| R6 | 제안요약서 초안 뽑아줘 | TemplateFill | TemplateFill | O |
| R7 | 이 자료들로 문서 양식 채워서 완성본 만들어줘 | TemplateFill | TemplateFill | O |
| R8 | 수행실적서 내용 반영해서 템플릿 다시 채워줘 | TemplateFill | TemplateFill | O |
| R9 | 사업제안요약서 양식대로 작성 부탁해 | TemplateFill | TemplateFill | O |
| R10 | 이 문서로 요약서 만들어줘 | TemplateFill | TemplateFill | O |
| R11 | RFP에서 사업 예산이 얼마라고 나와 있어? | DocQA | DocQA | O |
| R12 | 이 문서 요약해줘 | DocQA | DocQA | O |
| R13 | 수행실적서에 나온 프로젝트 3개를 정리해줘 | DocQA | DocQA | O |
| R14 | 제안서 제출 마감일이 언제야? | DocQA | DocQA | O |
| R15 | 투입 인력 중에 PM이 누구야? | DocQA | DocQA | O |
| R16 | 회사소개서 보고 회사 연혁 알려줘 | DocQA | DocQA | O |
| R17 | 이번 사업의 비기능 요구사항이 뭐뭐 있어? | DocQA | DocQA | O |
| R18 | 첨부한 문서에서 하자보수 기간 찾아줘 | DocQA | DocQA | O |
| R19 | RFP랑 수행실적서 비교해서 우리가 부합하는 부분 알려줘 | DocQA | DocQA | O |
| R20 | 이 PDF에 담당자 연락처 나와 있어? | DocQA | DocQA | O |
| R21 | 안녕! | Chat | Chat | O |
| R22 | 고마워, 수고했어 | Chat | Chat | O |
| R23 | 너는 뭘 할 수 있어? | Chat | Chat | O |
| R24 | 제안서 잘 쓰는 일반적인 팁 좀 알려줘 | Chat | Chat | O |
| R25 | RFP가 뭐의 약자야? | Chat | Chat | O |
| R26 | 협상에 의한 계약이 무슨 뜻이야? | Chat | Chat | O |
| R27 | 방금 답변 더 짧게 다시 말해줘 | Chat | Chat | O |
| R28 | 콜드체인이 뭐야? | Chat | Chat | O |
| R29 | 오늘 할 일이 많네 | Chat | Chat | O |
| R30 | 좋은 제안서 목차 구성 예시 들어줄래? | Chat | Chat | O |

## 특기 사항

- 경계 케이스로 설계한 쌍도 모두 정확히 갈렸다: R10 "이 문서로 요약서 **만들어줘**"(TemplateFill) vs R12 "이 문서 **요약해줘**"(DocQA).
- 문서에 등장하는 용어지만 일반 지식 질문인 R25(RFP 약자)·R26(협상에 의한 계약)·R28(콜드체인)도 문서 첨부 상태에서 Chat으로 올바르게 분류됐다.
