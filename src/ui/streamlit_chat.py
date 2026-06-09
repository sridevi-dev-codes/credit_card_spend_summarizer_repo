import json

import streamlit as st
import requests

import uuid

API_URL = "http://localhost:8000/api/v1/query/stream"

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

    # User message
    st.session_state.messages.append(
        {"role": "user", "content": query}
    )

    with st.chat_message("user"):
        st.markdown(query)

    # Assistant streaming response
    with st.chat_message("assistant"):

        message_placeholder = st.empty()
        full_response = ""

        try:
            response = requests.post(
                API_URL,
                json={
                    "query": query,
                    "session_id": session_id
                },
                stream=True
            )

            response.raise_for_status()

            for line in response.iter_lines():

                if not line:
                    continue

                line = line.decode("utf-8")

                if line.startswith("data: "):

                    payload = line[6:]

                    if payload == "[DONE]":
                        break

                    data = json.loads(payload)

                    token = data.get("type", "")

                    full_response += token

                    message_placeholder.markdown(full_response + "▌")

            message_placeholder.markdown(full_response)

        except Exception as e:
            full_response = f"Error: {e}"
            message_placeholder.markdown(full_response)

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": full_response
        }
    )


# ─────────────────────────────────────────────
# Sidebar: session controls
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("🧠 Session Controls")

    st.write(f"Current Session: {session_id}")

    if st.button("🧹 Clear Chat UI"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.caption("Backend persists history in PostgreSQL chat_history table")