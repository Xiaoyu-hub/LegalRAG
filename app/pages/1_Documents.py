"""Streamlit Documents page — upload, list, and manage PDF documents.

Per UI-SPEC Page 1:
  - States: Empty, Uploading, Upload error, List, Processing.
  - Copywriting from UI-SPEC copywriting contract.
  - Status badges with UI-SPEC color tokens.
"""
import os
import time

import requests
import streamlit as st

API_BASE = os.environ.get("API_BASE") or "http://localhost:8000"

st.set_page_config(page_title="Documents - LegalRAG", page_icon="\u2696\ufe0f", layout="wide")

st.title("Documents")


def fetch_documents():
    """Fetch all documents from the API."""
    try:
        resp = requests.get(f"{API_BASE}/api/v1/documents/", timeout=5)
        if resp.status_code == 200:
            return resp.json().get("data", {}).get("documents", [])
    except requests.RequestException:
        pass
    return None


def render_status_badge(status: str) -> str:
    """Render a coloured HTML status badge."""
    if status == "ready":
        return '<span class="status-ready">\u2705 Ready</span>'
    elif status == "processing":
        return '<span class="status-processing">\u23f3 Indexing...</span>'
    elif status == "error":
        return '<span class="status-error">\u274c Error</span>'
    else:
        return f'<span class="status-error">\u2753 {status}</span>'


# ── State ──────────────────────────────────────────────────────────────────

documents = fetch_documents()

# ── Empty State ────────────────────────────────────────────────────────────

if documents is None:
    st.error(
        "Could not connect to the backend. Please ensure the API server is running "
        "and refresh the page."
    )
elif len(documents) == 0:
    st.markdown(
        '<div class="upload-area">'
        "<h3>No documents uploaded yet</h3>"
        "<p>Upload a PDF legal document to begin. Supported format: PDF only.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

# ── Upload Widget ──────────────────────────────────────────────────────────

uploaded_file = st.file_uploader(
    "Upload Document", type=["pdf"], accept_multiple_files=False
)

if uploaded_file is not None:
    with st.spinner("Indexing document... this may take a moment"):
        try:
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
            resp = requests.post(
                f"{API_BASE}/api/v1/documents/upload",
                files=files,
                timeout=300,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "ok":
                    doc_id = data["data"]["document_id"]
                    # Poll until processing completes
                    while True:
                        poll_resp = requests.get(
                            f"{API_BASE}/api/v1/documents/{doc_id}/status",
                            timeout=5,
                        )
                        if poll_resp.status_code == 200:
                            poll_data = poll_resp.json().get("data", {})
                            processing_status = poll_data.get("processing_status", "processing")
                            if processing_status == "ready":
                                chunk_count = poll_data.get("chunk_count", 0)
                                st.success(f"Ready \u2014 {chunk_count} chunks indexed")
                                break
                            elif processing_status == "error":
                                st.error("Upload failed: document processing error. "
                                         "Please check the file and try again.")
                                break
                        time.sleep(2)
                    st.rerun()
                else:
                    st.error(
                        f"Upload failed: {data.get('error', 'unknown error')}. "
                        "Please check the file and try again."
                    )
            else:
                err_detail = resp.json().get("error", f"HTTP {resp.status_code}")
                st.error(
                    f"Upload failed: {err_detail}. "
                    "Please check the file and try again."
                )
        except requests.RequestException as exc:
            st.error(
                f"Upload failed: {exc}. "
                "Please check the file and try again."
            )

# ── Document List ──────────────────────────────────────────────────────────

documents = fetch_documents()
if documents and len(documents) > 0:
    st.markdown("### Uploaded Documents")
    for doc in documents:
        doc_id = doc["id"]
        filename = doc["filename"]
        created_at = doc.get("created_at", "")[:10] if doc.get("created_at") else ""
        chunk_count = doc.get("chunk_count", 0)
        status = doc.get("status", "unknown")
        status_html = render_status_badge(status)

        with st.container():
            cols = st.columns([1, 3, 2, 2, 1])
            # Icon column
            cols[0].markdown("\ud83d\udcc4")
            # Filename
            cols[1].markdown(
                f'<div class="doc-card-title">{filename}</div>',
                unsafe_allow_html=True,
            )
            # Date
            cols[2].markdown(
                f'<div class="doc-card-meta">{created_at}</div>',
                unsafe_allow_html=True,
            )
            # Chunk count
            cols[3].markdown(
                f'<div class="doc-card-meta">{chunk_count} chunks indexed</div>',
                unsafe_allow_html=True,
            )
            # Status badge
            cols[4].markdown(status_html, unsafe_allow_html=True)

            # Click to select
            if cols[0].button("\ud83d\udccb", key=f"select_{doc_id}"):
                st.session_state.selected_doc_id = doc_id
                st.session_state.selected_doc_name = filename
                st.rerun()

        st.markdown("---")
