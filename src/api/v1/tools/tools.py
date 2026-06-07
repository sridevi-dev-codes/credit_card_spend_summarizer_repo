from langchain_core.documents import Document
from typing import TypedDict, List

class RAGState(TypedDict):
    query: str
    retrieved_docs: list
    reranked_docs: list
    response: dict
    route: str
    generated_sql: str
    sql_result: str
    chat_history: list
    # 🔥 DEBUG FIELDS (ADD ONLY THESE)
    debug_router_reason: str

def vector_search_node(state: RAGState) -> RAGState:
    try:
        query = state["query"]

        print("\n🧠 VECTOR SEARCH NODE (STUB MODE)")
        print("Query:", query)
        print("STATUS: NOT IMPLEMENTED YET")

        # placeholder yet to do
        docs = [
            Document(
                page_content="Vector search is not implemented yet. This is a placeholder response.",
                metadata={
                    "status": "stub",
                    "note": "vector_search_node not implemented"
                }
            )
        ]

        return {
            **state,
            "retrieved_docs": docs
        }

    except Exception as e:
        import traceback
        print("\n❌ VECTOR NODE ERROR")
        traceback.print_exc()

        return {
            **state,
            "retrieved_docs": [],
            "error": str(e)
        }