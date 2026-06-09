import traceback

from src.api.v1.agents.agents import run_search_agent, run_search_agent_stream
from src.api.v1.services.chat_history import save_chat, load_history


def query_documents(query: str, session_id: str):

    try:
        history_rows = load_history(session_id)
        chat_history = history_rows

        result = run_search_agent(query, chat_history)

        answer = result.get("response", {}).get("answer", "")
        route = result.get("route", "unknown")

        save_chat(session_id, query, answer, route)

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