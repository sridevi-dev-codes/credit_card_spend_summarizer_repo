from langchain_core.documents import Document
from typing import TypedDict, List, Dict, Any
from src.core.db import vector_search_chunks

class RAGState(TypedDict):
    query: str
    chat_history: List[str]
    route: str
    # Vector Search elements
    retrieved_docs: List[Any]
    reranked_docs: List[Any]
    # SQL elements
    generated_sql: str
    sql_result: str
    # Final Output
    response: Dict[str, Any]
    debug_router_reason: str


def vector_search_node(state: RAGState) -> RAGState:
    print(f"[vector_search_node] Running vector search for query: {state['query']}")
    rows = vector_search_chunks(state["query"], k=20)
    print (f"[vector_search_node] Retrieved {len(rows)} rows from PGVector")    
    # for row in rows:
    #     print(f"Row content: {row['content']}")
    
    docs = [
        Document(
            page_content=row["content"],
            metadata={
                **row["metadata"],
                "chunk_type": row["chunk_type"],
                "page_number": row["page_number"],
                "section": row["section"],
                "source_file": row["source_file"],
            },
        )
        for row in rows
    ]

    return {**state, "retrieved_docs": docs}