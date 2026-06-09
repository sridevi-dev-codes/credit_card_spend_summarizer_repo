# upload_app.py

import requests
import streamlit as st

st.title("Credit Card Knowledge Base Upload")

uploaded_file = st.file_uploader(
    "Upload PDF",
    type=["pdf"]
)

if uploaded_file:

    if st.button("Ingest"):
        with st.spinner("Ingesting PDF... please wait"):
            files = {
                "file": (
                    uploaded_file.name,
                    uploaded_file,
                    "application/pdf"
                )
            }

            response = requests.post(
                "http://localhost:8000/api/v1/upload-pdf",
                files=files
            )

            st.json(response.json())