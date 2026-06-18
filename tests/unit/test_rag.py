"""RAG 레이어 단위 테스트."""


def test_search_returns_list():
    from app.rag.retriever import search

    assert isinstance(search("hello"), list)
