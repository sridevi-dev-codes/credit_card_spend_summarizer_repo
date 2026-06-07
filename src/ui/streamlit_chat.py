import streamlit as st
import requests

API_URL = "http://localhost:8000/api/v1/query"

st.set_page_config(page_title="Credit Card Assistant", layout="centered")

st.title("💳 Credit Card Spend Assistant")

# ─────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = "demo-session"

# ─────────────────────────────────────────────
# Session input
# ─────────────────────────────────────────────
session_id = st.text_input(
    "Session ID",
    value=st.session_state.session_id
)

st.session_state.session_id = session_id


# ─────────────────────────────────────────────
# Display chat history
# ─────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# ─────────────────────────────────────────────
# Chat input
# ─────────────────────────────────────────────
query = st.chat_input("Ask something about your credit card...")

if query:

    # 1. Show user message immediately
    st.session_state.messages.append(
        {"role": "user", "content": query}
    )

    with st.chat_message("user"):
        st.markdown(query)

    # 2. Call backend
    with st.spinner("Thinking..."):
        try:
            res = requests.post(
                API_URL,
                json={
                    "query": query,
                    "session_id": session_id
                }
            )

            if res.status_code != 200:
                raise Exception(res.text)

            data = res.json()

            answer = data.get("answer", "No response")
            route = data.get("route", "unknown")

        except Exception as e:
            answer = f"Error: {str(e)}"
            route = "error"

    # 3. Show assistant message
    assistant_message = f"{answer}\n\n🧭 Route: `{route}`"

    st.session_state.messages.append(
        {"role": "assistant", "content": assistant_message}
    )

    with st.chat_message("assistant"):
        st.markdown(assistant_message)


# ─────────────────────────────────────────────
# Sidebar: session controls
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("🧠 Session Controls")

    st.write(f"Current Session: `{session_id}`")

    if st.button("🧹 Clear Chat UI"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.caption("Backend persists history in PostgreSQL chat_history table")