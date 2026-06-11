import json
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

class _RouteDecision(BaseModel):
    route: Literal["transaction", "document", "Hybrid_SQL_Document", "general"]
    reason: str


# ─────────────────────────────────────────────
# ROUTER NODE
# ─────────────────────────────────────────────
def router_node(state: RAGState) -> RAGState:
    llm = _get_llm()
    structured_llm = llm.with_structured_output(_RouteDecision)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
You are an expert query router for a credit card intelligence system. Your job is to classify the user's intent into exactly ONE route.

IMPORTANT CONTEXT RULE:
If the current query omits information such as card number, account ID, card type, or customer identifier, infer the missing information from the most recent conversation history.

Pronouns and references such as:
- it
- this card
- my card
- that account
- the above card

should refer to the latest card/account identifier mentioned in previous messages.

Example:

History:
User: What is the balance on card CC-110098?
Assistant: ₹12,000

Current query:
Is it eligible for annual fee waiver?

Interpretation:
"it" = card CC-110098

Since eligibility requires both spend data and policy rules,
route = Hybrid_SQL_Document.

--- CRITICAL ROUTING PRIORITY RULE ---
Always check for 'Hybrid_SQL_Document' FIRST. If a query requires searching both concrete database records (specific account IDs, transaction codes, balances, or card types) AND matching them against fine-print rules or policies, you MUST choose 'Hybrid_SQL_Document'. Do NOT route to 'transaction' or 'document' if elements of both are present.

Routes:

1. Hybrid_SQL_Document:
- Select this when an answer requires BOTH customer-specific account data AND general company policy guidelines to answer.
- Indicators: Mention of a specific card identifier (e.g., "CC-110098") or any credit card number, transaction details, or spend histories combined with policy words like "eligible", "waiver", "rules", "perks", or "benefits".
- Example: "is my card CC-110098 eligible for annual fee waiver" -> (Needs to check if CC-110098 has met spend thresholds via SQL, and check waiver criteria via Policy Document).

2. transaction:
- Purely structured database inquiries. Spending lookups, billing amounts, statement data, reward balances, or direct transaction histories.
- Does NOT require reading unstructured rulebooks or fine-print policies.
- Example: "Show me my transactions for last month" or "What is the balance on card CC-110098?"

3. general:
- greetings, identity questions, memory questions, or anything not requiring SQL or documents

STRICT RULE:
If unsure → choose general
""",
            ),
            ("human", "Chat history:\n{history}\n\nQuery: {query}"),
        ]
    )

    chain = prompt | structured_llm

    decision = chain.invoke({
        "query": state["query"],
        "history": "\n".join(state.get("chat_history", []))
    })

    print("\n🧭 ROUTER:", decision.route, decision.reason)

    return {
        **state,
        "route": decision.route
    }
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

Use SQL results to answer clearly. But dont mention any database jargons. Translate SQL output into natural language insights.

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
    print('**********************************')
    print(f'After reranking:{reranked_docs}')

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
# GENERAL NODE ( HANDLES EVERYTHING ELSE)
# ─────────────────────────────────────────────
def general_node(state: RAGState) -> RAGState:
    llm = _get_llm()

    history = "\n".join(state.get("chat_history", []))

    prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
You are a friendly Credit Card Assistant.

You MUST:
Handle greetings naturally
Handle small talk naturally
Answer identity questions
Use chat history for memory

Examples:
"hi" → greet normally
"how are you" → respond naturally
"thank you" → respond politely

ONLY refuse when:
User asks something completely unrelated
AND it is not casual conversation/small talk

For unrelated topics, say:
"Sorry.. I can only assist with credit card related queries."

Chat History:
{history}
"""
    ),
    ("human", "{query}")
])

    answer = (prompt | llm).invoke({
        "query": state["query"],
        "history": history
    })

    return {
        **state,
        "response": {
            "answer": answer.content,
            "policy_citations": "N/A",
            "document_name": "N/A",
            "page_no": "N/A"
        }
    }
	
# ─────────────────────────────────────────────
# HYBRID ORCHESTRATION NODE
# ─────────────────────────────────────────────
def hybrid_node(state: RAGState) -> RAGState:
    """Executes BOTH SQL data extraction and vector retrieval concurrently or sequentially."""
    print("\n🔀 RUNNING HYBRID NODE")

    # --- 1. Execute SQL Extraction Part ---
    llm = _get_llm()
    db = get_sql_database()
    schema_info = db.get_table_info()

    sql_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a PostgreSQL expert for a credit card analytics system. Return ONLY valid SELECT code.\nSchema:\n{schema}",
            ),
            ("human", "Chat history:\n{history}\n\nQuestion: {question}"),
        ]
    )

    sql_chain = sql_prompt | llm
    raw_sql = sql_chain.invoke(
        {
            "schema": schema_info,
            "question": state["query"],
            "history": "\n".join(state.get("chat_history", [])),
        }
    )

    generated_sql = raw_sql.content.strip().strip("```").strip()
    if generated_sql.lower().startswith("sql"):
        generated_sql = generated_sql[3:].strip()

    print(f"[Hybrid] Executing Generated SQL: {generated_sql}")
    sql_result = safe_sql_execute(db, generated_sql)

    # --- 2. Execute Document Vector Search Part ---
    print(f"[Hybrid] Querying PGVector for context...")
    # Directly pull vector search logic
    from src.api.v1.tools.tools import vector_search_chunks
    from langchain_core.documents import Document

    rows = vector_search_chunks(
        state["query"], k=15
    )  # Slightly lower k since it's hybrid
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

    # Return everything collected into the state pipeline
    return {
        **state,
        "generated_sql": generated_sql,
        "sql_result": str(sql_result),
        "retrieved_docs": docs,
    }


# ─────────────────────────────────────────────
# HYBRID GENERATOR NODE (COMBINER)
# ─────────────────────────────────────────────
def generate_hybrid_answer_node(state: RAGState) -> RAGState:
    """Synthesizes structured transaction results and policy rules into one cohesive AIResponse."""
    llm = _get_llm()
    structured_llm = llm.with_structured_output(AIResponse)

    # Setup document context from the Reranker step
    context = "\n\n".join(
        [
            f"[Source: {doc.metadata.get('source_file','unknown')} | Page: {doc.metadata.get('page_number','?')}]"
            f"\n{doc.page_content}"
            for doc in state["reranked_docs"]
        ]
    )

    hybrid_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
You are a senior credit card optimization analyst. 

Your job is to answer the user's inquiry by evaluating their real-time transaction history against company policy documentation.

Guidelines:
1. Examine the SQL Database Output to check user details (e.g., specific transactions, spending milestones, fee charges).
2. Cross-reference this with the Provided Policy Context (e.g., fee waiver rules, timeline limits).
3. Synthesize both to provide a definite conclusion (e.g., "Yes, you hit the $5,000 threshold, so you qualify" or "No, you have not spent enough yet").
""",
            ),
            (
                "human",
                """
User Question: {query}

--- TRANSACTION DATA (SQL RESULT) ---
SQL Query Executed: {sql}
Data Returned: {sql_result}

--- POLICY RULES CONTEXT ---
{context}
""",
            ),
        ]
    )

    chain = hybrid_prompt | structured_llm
    result = chain.invoke(
        {
            "query": state["query"],
            "sql": state["generated_sql"],
            "sql_result": state["sql_result"],
            "context": context,
        }
    )

    # Inject metadata back into the final response model payload
    response = result.model_dump()
    response["sql_query_executed"] = state["generated_sql"]

    return {**state, "response": response}	
	
# ─────────────────────────────────────────────
# GRAPH BUILDER
# ─────────────────────────────────────────────


def build_rag_graph():
    graph = StateGraph(RAGState)

    # 1. Register ALL nodes
    graph.add_node("router", router_node)
    graph.add_node("nl2sql", nl2sql_node)
    graph.add_node("vector_search", vector_search_node)
    graph.add_node("rerank", rerank_node)
    graph.add_node("generate_answer", generate_answer_node)

    # New Hybrid Nodes
    graph.add_node("hybrid_orchestrator", hybrid_node)
    graph.add_node("generate_hybrid_answer", generate_hybrid_answer_node)

    graph.add_node("general", general_node)

    graph.set_entry_point("router")

    # 2. Update Conditional Router Mapping
    graph.add_conditional_edges(
        "router",
        lambda state: state["route"],
        {
            "transaction": "nl2sql",
            "document": "vector_search",
            "Hybrid_SQL_Document": "hybrid_orchestrator",  # Map to the new hybrid flow
           "general" : "general"
        },
    )

    # 3. Handle Edge Handshakes
    graph.add_edge("nl2sql", END)

    # Pure Unstructured Path
    graph.add_edge("vector_search", "rerank")

    # Hybrid Path (Passes documents to Reranker seamlessly)
    graph.add_edge("hybrid_orchestrator", "rerank")

    # Conditional Split or Direct Edge after Rerank
    # Since both paths use rerank, we check State Route to determine final generation node
    graph.add_conditional_edges(
        "rerank",
        lambda state: state["route"],
        {
            "document": "generate_answer",
            "Hybrid_SQL_Document": "generate_hybrid_answer",
        },
    )

    graph.add_edge("generate_answer", END)
    graph.add_edge("generate_hybrid_answer", END)
    graph.add_edge("general", END)

    graph = graph.compile()

    graph_image = graph.get_graph().draw_mermaid_png()
    with open("src/agents.png", "wb") as f:
        f.write(graph_image)

    return graph

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
    return final_state  # frontend can access final_state["route"]


async def run_search_agent_stream(query: str, chat_history: list = None):
    print(f"\n🚀 [run_search_agent_stream - agents] Invoked with query: {query}")
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

    async for event in rag_graph.astream_events(initial_state, version="v2"):
        kind = event["event"]

         # Which graph node produced this event
        node_name = (
            event.get("metadata", {})
            .get("langgraph_node")
        )

        # Stream only from answer-producing nodes
        allowed_nodes = {
            "general",
            "generate_answer",
            "generate_hybrid_answer",
            "nl2sql"
        }

        if (kind == "on_chat_model_stream" and node_name in allowed_nodes):
            content = event["data"]["chunk"].content
            print(f"\n[Stream Event] Node: {node_name} | Content Chunk: {content}")
            yield f"data: {json.dumps({'type': content})}\n\n"
    yield "data: [DONE]\n\n"


