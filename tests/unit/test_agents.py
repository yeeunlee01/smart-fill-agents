"""에이전트/그래프 단위 테스트."""


def test_build_graph():
    from app.agents.graph import build_graph

    graph = build_graph()
    assert graph is not None
