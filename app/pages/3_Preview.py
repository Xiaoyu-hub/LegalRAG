import os

import requests
import streamlit as st

API_BASE = os.environ.get("API_BASE") or "http://localhost:8000"

st.title("Document Preview")

doc_id = st.session_state.get("selected_doc_id")
doc_name = st.session_state.get("selected_doc_name", "")

if not doc_id:
    st.info("Select a document from the sidebar to preview its structure")
    st.stop()

st.caption(f"Document: {doc_name}")

try:
    with st.spinner("Loading document structure..."):
        resp = requests.get(f"{API_BASE}/api/v1/documents/{doc_id}/chunks", timeout=10)

    if resp.status_code == 200:
        data = resp.json()
        chunks = data.get("data", {}).get("chunks", [])

        st.markdown(f"Showing **{len(chunks)}** chunks")

        articles = {}
        for chunk in chunks:
            article = chunk.get("article") or "General"
            if article not in articles:
                articles[article] = []
            articles[article].append(chunk)

        for article_name, article_chunks in articles.items():
            with st.expander(f"**{article_name}**", expanded=False):
                for chunk in article_chunks:
                    section = chunk.get("section")
                    text = chunk.get("text", "")[:500]
                    if section:
                        st.markdown(f"**{section}**")
                    st.text(text)
                    st.divider()
    else:
        st.error("Could not load document preview. The document may have been removed.")

except requests.exceptions.RequestException:
    st.error("Could not load document preview. Please check your connection.")
