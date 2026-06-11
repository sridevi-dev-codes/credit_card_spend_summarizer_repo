import traceback
from fastapi import APIRouter, HTTPException
from src.api.v1.agents.agents import run_search_agent, run_search_agent_stream
from src.api.v1.services.chat_history import save_chat, load_history
import json
from src.core.guardrails import guard_input, guard_output
from src.core.guardrails import GuardrailViolation


def query_documents(query: str, session_id: str):

    # 1️⃣ Load chat history
    history_rows = load_history(session_id)
    chat_history = history_rows

    # 2️⃣ Validate input
    guard_input(query)

    # 3️⃣ Run agent
    result = run_search_agent(query, chat_history)

    # 4️⃣ Extract answer from nested result
    answer = result.get("response", {}).get("answer", "")

    # 5️⃣ Guard the output
    if answer:
        try:
            answer = guard_output(answer)
            # Update result dict to keep consistent schema
            if "response" in result:
                result["response"]["answer"] = answer
            else:
                result["response"] = {"answer": answer}
        except Exception as e:
            # optional: log output guard errors
            print(f"⚠️ Output guard failed: {str(e)}")
            # fallback: keep original answer

    route = result.get("route", "unknown")

    # 6️⃣ Save chat
    save_chat(session_id, query, answer, route)

    return result
    

async def query_documents_stream(query: str, session_id: str):
    print ("[query_documents_stream - service] Starting stream for query:", query)
    try:
        history_rows = load_history(session_id)
        chat_history = history_rows

        result = run_search_agent_stream(query, chat_history)
        print(f"[query_documents_stream - service] Stream started for query: {query}")
        print(f"[query_documents_stream - service] Result generator: {result}")
        # answer = result.get("response", {}).get("answer", "")
        # route = result.get("route", "unknown")

        # save_chat(session_id, query, answer, route)

        return result

    except Exception as e:
        print("\n❌ [query_documents ERROR]")
        print(str(e))

        print("\n🧠 FULL TRACEBACK:")
        print(traceback.format_exc())

        return {
            "answer": "Something went wrong while processing your request.",
            "route": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }