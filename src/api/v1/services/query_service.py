import traceback

from src.api.v1.agents.agents import run_search_agent
from src.api.v1.services.chat_history import save_chat, load_history


def query_documents(query: str, session_id: str):

    try:
        history_rows = load_history(session_id)

        chat_history = [
            f"User: {q} | Assistant: {a}"
            for q, a, _ in history_rows
        ]

        result = run_search_agent(query, chat_history)

        answer = result.get("answer", "")
        route = result.get("route", "unknown")

        save_chat(session_id, query, answer, route)

        return result

    except Exception as e:
        print("\n❌ [query_documents ERROR]")
        print(str(e))

        # 🔥 FULL TRACEBACK (THIS IS WHAT YOU WANT)
        print("\n🧠 FULL TRACEBACK:")
        print(traceback.format_exc())

        return {
            "answer": "Something went wrong while processing your request.",
            "route": "error",
            "error": str(e),                 # optional but useful
            "traceback": traceback.format_exc()  # ⚠️ helps frontend debugging
        }
