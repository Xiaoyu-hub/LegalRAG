import os

import requests
import streamlit as st

API_BASE = os.environ.get("API_BASE") or "http://localhost:8000"

st.title("Chat")

doc_id = st.session_state.get("selected_doc_id")
doc_name = st.session_state.get("selected_doc_name", "")

if not doc_id:
    st.info("Select a document from the sidebar to begin asking questions")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("sources"):
            with st.expander(f"View Retrieved Sources ({len(msg['sources'])} chunks)"):
                for src in msg["sources"]:
                    st.markdown(f"**{src['article']}** — {src['section']}")
                    st.text(src["text"][:300])

col1, col2 = st.columns([4, 1])
with col1:
    if prompt := st.chat_input(f"Ask a question about {doc_name}..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            placeholder = st.empty()
            full_text = ""

            try:
                response = requests.post(
                    f"{API_BASE}/api/v1/chat/",
                    json={"question": prompt, "document_id": doc_id},
                    stream=True,
                    timeout=60,
                )
                response.raise_for_status()

                for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                    if chunk:
                        full_text += chunk
                        placeholder.markdown(full_text + "▌")

                placeholder.markdown(full_text)

                src_resp = requests.get(f"{API_BASE}/api/v1/chat/sources", timeout=5)
                sources = []
                if src_resp.status_code == 200:
                    sources = src_resp.json().get("data", {}).get("sources", [])

                if sources:
                    with st.expander(f"View Retrieved Sources ({len(sources)} chunks)"):
                        for src in sources:
                            st.markdown(f"**{src['article']}** — {src['section']}")
                            st.text(src["text"][:300])

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_text,
                    "sources": sources,
                })

            except requests.exceptions.RequestException:
                st.error("Failed to get answer. Please check your connection and try again.")
                st.session_state.messages.pop()

with col2:
    st.button("Clear", on_click=lambda: st.session_state.update(messages=[]))
