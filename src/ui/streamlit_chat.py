import streamlit as st
import requests

import uuid

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

session_id = st.session_state.session_id

# ─────────────────────────────────────────────
# Display chat history
# ─────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ────────────────────────────────────────────
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

            data = res.json()

            # ----------------------------
            # CASE 1: SUCCESS (200)
            # ----------------------------
            if res.status_code == 200:
                answer = data.get("response", {}).get("answer", "")
                route = data.get("route", "unknown")

            # ----------------------------
            # CASE 2: GUARDRAIL / CLIENT ERROR (400)
            # ----------------------------
            elif res.status_code == 400:
                answer = data.get("detail", {}).get("message", "Blocked by guardrails")
                route = "guardrail"

            # ----------------------------
            # CASE 3: SERVER ERROR (500)
            # ----------------------------
            else:
                answer = data.get("detail", "Something went wrong")
                route = "error"

        except Exception as e:
            answer = "Unable to reach server. Please try again."
            route = "error"

        # 3. Show assistant message
        if route == "guardrail":
            assistant_message = f"⚠️ {answer}"
        else:
            assistant_message = answer
        # assistant_message = f"{answer}\n\n🧭 Route: `{route}`"

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