import os
from typing import Literal
import cohere
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from pydantic import BaseModel

from src.api.v1.schema.query_schema import AIResponse
from src.api.v1.tools.tools import RAGState, vector_search_node
from src.core.db import get_sql_database

load_dotenv()

# ─────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────
def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("OPENAI_CHAT_MODEL"),
        api_key=os.getenv("OPENAI_API_KEY")
    )

# ─────────────────────────────────────────────
# ROUTER SCHEMA
# ─────────────────────────────────────────────
# class _RouteDecision(BaseModel):
#     route: Literal[
#         "transaction",
#         "document",
#         "greeting",
#         "unsupported"
#     ]
#     reason: str
class _RouteDecision(BaseModel):
    route: Literal[
        "transaction",
        "document",
        "greeting",
        "identity",
        "unsupported"
    ]
    reason: str

# ─────────────────────────────────────────────
# ROUTER NODE
# ─────────────────────────────────────────────
def router_node(state: RAGState) -> RAGState:
    llm = _get_llm()
    structured_llm = llm.with_structured_output(_RouteDecision)

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
You are a query router for a credit card intelligence system.

Routes:

1. transaction:
- credit card spending, billing, statements, rewards, cashback, EMI, fees,
  fraud, limits, card usage, monthly summary
- structured DB: billing_statements, card_transactions, credit_cards, customers, reward_transactions

2. document:
- policies, benefits, forex markup, FAQs, rules, regulations, explanations

3. greeting
- hi, hello, hey, good morning, good evening ,bye, goodbye, see you, thank you,
thanks, ok, cool

4. identity
- who are you, what can you do, what is this application, tell me about yourself,
help, capabilities

5. unsupported
- anything outside credit card domain

Return ONLY route + reason.
"""
        ),
        ("human", "Chat history:\n{history}\n\nQuery: {query}")
    ])

    chain = prompt | structured_llm

    decision = chain.invoke({
        "query": state["query"],
        "history": "\n".join(state.get("chat_history", []))
    })
    # 🔥 DEBUG PRINTS
    print("\n🧭 ROUTER DEBUG")
    print("Route:", decision.route)
    print("Reason:", decision.reason)

    return {
        **state,
        "route": decision.route,
        "debug_router_reason": decision.reason
    }

    # return {
    #     **state,
    #     "route": decision.route
    # }

# ─────────────────────────────────────────────
# SAFE SQL EXECUTION (AUTO RETRY)
# ─────────────────────────────────────────────
def safe_sql_execute(db, sql, retries=2):
    for i in range(retries):
        try:
            return db.run(sql)
        except Exception as e:
            if i == retries - 1:
                return f"SQL execution error after retries: {e}"
            sql = sql + " LIMIT 10"

# ─────────────────────────────────────────────
# NL2SQL NODE (TRANSACTION PATH)
# ─────────────────────────────────────────────
def nl2sql_node(state: RAGState) -> RAGState:
    llm = _get_llm()
    db = get_sql_database()

    schema_info = db.get_table_info()

    sql_prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
You are a PostgreSQL expert for a credit card analytics system.

Rules:
- ONLY SELECT queries
- No DDL/DML
- Always LIMIT 50 unless aggregation
- Use synonyms for transaction search
- Interpret chat history if needed
- Prefer recent transactions if time is unclear

Schema:
{schema}
"""
        ),
        ("human", "Chat history:\n{history}\n\nQuestion: {question}")
    ])

    sql_chain = sql_prompt | llm

    raw_sql = sql_chain.invoke({
        "schema": schema_info,
        "question": state["query"],
        "history": "\n".join(state.get("chat_history", []))
    })

    content = raw_sql.content
    if isinstance(content, list):
        content = "".join(
            p.get("text", "") if isinstance(p, dict) else str(p)
            for p in content
        )

    generated_sql = content.strip().strip("```").strip()
    print("\n🧾 GENERATED SQL DEBUG")
    print(generated_sql)

    if generated_sql.lower().startswith("sql"):
        generated_sql = generated_sql[3:].strip()

    sql_result = safe_sql_execute(db, generated_sql)

    structured_llm = llm.with_structured_output(AIResponse)

    answer_prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
You are a credit card data analyst.

Use SQL results to answer clearly.

Rules:
- concise answer
- structured output
- policy_citations = N/A
- document_name = agentic_credit_db
"""
        ),
        ("human",
         "Question: {query}\nSQL: {sql}\nResult: {result}")
    ])

    chain = answer_prompt | structured_llm

    answer = chain.invoke({
        "query": state["query"],
        "sql": generated_sql,
        "result": sql_result
    })

    response = answer.model_dump()
    response["sql_query_executed"] = generated_sql

    return {
        **state,
        "generated_sql": generated_sql,
        "sql_result": str(sql_result),
        "response": response
    }

# ─────────────────────────────────────────────
# MULTI QUERY EXPANSION (DOCUMENT PATH)
# ─────────────────────────────────────────────
def expand_queries(query: str, llm) -> list:
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Generate 3 alternative search queries."),
        ("human", "{query}")
    ])

    chain = prompt | llm
    result = chain.invoke({"query": query})

    return [query] + result.content.split("\n")[:3]

# ─────────────────────────────────────────────
# RERANK NODE (UNCHANGED)
# ─────────────────────────────────────────────
def rerank_node(state: RAGState) -> RAGState:
    co = cohere.ClientV2(api_key=os.getenv("COHERE_API_KEY"))
    docs = state["retrieved_docs"]

    rerank_response = co.rerank(
        model="rerank-english-v3.0",
        query=state["query"],
        documents=[doc.page_content for doc in docs],
        top_n=10
    )

    reranked_docs = [docs[r.index] for r in rerank_response.results]

    return {**state, "reranked_docs": reranked_docs}

# ─────────────────────────────────────────────
# GENERATE ANSWER (DOCUMENT PATH)
# ─────────────────────────────────────────────
def generate_answer_node(state: RAGState) -> RAGState:
    llm = _get_llm()
    structured_llm = llm.with_structured_output(AIResponse)

    context = "\n\n".join([
        f"[Source: {doc.metadata.get('source','unknown')} | Page: {doc.metadata.get('page','?')}]"
        f"\n{doc.page_content}"
        for doc in state["reranked_docs"]
    ])

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
Answer using ONLY context.

If multiple versions exist:
- prefer latest version
- mention differences across versions
"""
        ),
        ("human", "Context:\n{context}\n\nQuestion: {query}")
    ])

    chain = prompt | structured_llm

    result = chain.invoke({
        "context": context,
        "query": state["query"]
    })

    return {
        **state,
        "response": result.model_dump()
    }

# ─────────────────────────────────────────────
# GREETING NODE
# ─────────────────────────────────────────────
def greeting_node(state: RAGState) -> RAGState:
    q = state["query"].lower()
    if any(x in q for x in ["bye", "goodbye", "see you"]):
        msg = "Goodbye 👋 Have a great day."
    elif any(x in q for x in ["thanks", "thank you"]):
        msg = "You're welcome 😊"
    else:
        msg = (
            "Hello 👋 I can help with credit card transactions, "
            "spending summaries, rewards, cashback, billing statements, "
            "and card policy questions."
        )
    return {
        **state,
        "response": {
            "answer": msg,
            "policy_citations": "N/A",
            "document_name": "N/A",
            "page_no": "N/A"
        }
    }
#___________________________________________
#IDENTITY NODE
#___________________________________________
def identity_node(state: RAGState) -> RAGState:
    return {
        **state,
        "response": {
            "answer": (
                "I am a Credit Card Spend Assistant. "
                "I can help you analyse card transactions, spending patterns, "
                "billing statements, rewards, cashback, and answer questions "
                "about credit card policies and benefits."
            ),
            "policy_citations": "N/A",
            "document_name": "N/A",
            "page_no": "N/A"
        }
    }
# ─────────────────────────────────────────────
# UNSUPPORTED NODE
# ─────────────────────────────────────────────
def unsupported_node(state: RAGState) -> RAGState:
    return {
        **state,
        "response": {
            "answer": "I can only assist with credit card related queries.",
            "policy_citations": "N/A",
            "document_name": "N/A",
            "page_no": "N/A"
        }
    }

# ─────────────────────────────────────────────
# GRAPH BUILDER
# ─────────────────────────────────────────────
def build_rag_graph():
    graph = StateGraph(RAGState)

    graph.add_node("router", router_node)
    graph.add_node("nl2sql", nl2sql_node)
    graph.add_node("vector_search", vector_search_node)
    graph.add_node("rerank", rerank_node)
    graph.add_node("generate_answer", generate_answer_node)
    graph.add_node("greeting", greeting_node)
    graph.add_node("identity", identity_node)
    graph.add_node("unsupported", unsupported_node)

    graph.set_entry_point("router")

    graph.add_conditional_edges(
        "router",
        lambda state: state["route"],
        {
            "transaction": "nl2sql",
            "document": "vector_search",
            "greeting": "greeting",
            "identity": "identity",
            "unsupported": "unsupported"
        }
    )

    graph.add_edge("nl2sql", END)
    graph.add_edge("vector_search", END)

    # graph.add_edge("vector_search", "rerank")
    # graph.add_edge("rerank", "generate_answer")
    # graph.add_edge("generate_answer", END)

    return graph.compile()

# ─────────────────────────────────────────────
# COMPILED AGENT
# ─────────────────────────────────────────────
rag_graph = build_rag_graph()

# ─────────────────────────────────────────────
# PUBLIC ENTRYPOINT
# ─────────────────────────────────────────────
def run_search_agent(query: str, chat_history: list = None) -> dict:
    if chat_history is None:
        chat_history = []

    initial_state: RAGState = {
        "query": query,
        "chat_history": chat_history,
        "retrieved_docs": [],
        "reranked_docs": [],
        "response": {},
        "route": "",
        "generated_sql": "",
        "sql_result": "",
    }

    final_state = rag_graph.invoke(initial_state)
    return final_state["response"]