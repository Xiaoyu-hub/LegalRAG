"""Streamlit application entry point — sidebar, navigation, global state.

Per CONTEXT.md:
  - D-09: Three-page structure (Documents, Chat, Preview) via Streamlit multi-page.
  - D-10: Navigation via st.sidebar.radio.
  - D-11: Document selector in sidebar via st.selectbox.
"""
import os

import requests
import streamlit as st

st.set_page_config(page_title="LegalRAG", page_icon="\u2696\ufe0f", layout="wide")

# ── API Base URL ───────────────────────────────────────────────────────────

API_BASE = os.environ.get("API_BASE") or "http://localhost:8000"

# ── Custom CSS (UI-SPEC Color Palette) ─────────────────────────────────────

st.markdown(
    f"""
<style>
    /* Font */
    body, .stApp {{
        font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }}
    /* Accent color */
    .stButton>button {{
        background-color: #1E3A5F;
        color: #FFFFFF;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1rem;
        font-weight: 600;
    }}
    .stButton>button:hover {{
        background-color: #2C5282;
        color: #FFFFFF;
    }}
    /* Sidebar */
    section[data-testid="stSidebar"] {{
        background-color: #F0F2F6;
    }}
    /* Status badges */
    .status-processing {{
        color: #D69E2E;
        font-weight: 600;
    }}
    .status-ready {{
        color: #38A169;
        font-weight: 600;
    }}
    .status-error {{
        color: #E53E3E;
        font-weight: 600;
    }}
    /* Document card */
    .doc-card {{
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.75rem;
    }}
    .doc-card:hover {{
        border-color: #1E3A5F;
        cursor: pointer;
    }}
    .doc-card-title {{
        font-size: 16px;
        font-weight: 600;
        color: #1A202C;
    }}
    .doc-card-meta {{
        font-size: 14px;
        color: #718096;
    }}
    /* Upload area dashed border */
    .upload-area {{
        border: 2px dashed #E2E8F0;
        border-radius: 12px;
        padding: 3rem 2rem;
        text-align: center;
        background-color: #FFFFFF;
    }}
    .upload-area h3 {{
        color: #1A202C;
    }}
    .upload-area p {{
        color: #718096;
    }}
</style>
""",
    unsafe_allow_html=True,
)

# ── Session State Initialisation ───────────────────────────────────────────

if "nav_page" not in st.session_state:
    st.session_state.nav_page = "Documents"
if "selected_doc_id" not in st.session_state:
    st.session_state.selected_doc_id = None
if "selected_doc_name" not in st.session_state:
    st.session_state.selected_doc_name = None

# ── Sidebar Layout ─────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## \u2696\ufe0f LegalRAG")
    st.caption("v1.0")

    # Navigation radio (D-10)
    nav_page = st.radio(
        "Navigation",
        ["Documents", "Chat", "Preview"],
        index=["Documents", "Chat", "Preview"].index(st.session_state.nav_page),
        label_visibility="collapsed",
    )
    st.session_state.nav_page = nav_page

    # Document selector (D-11) — populated from /api/v1/documents
    st.markdown("---")
    st.markdown("**Select Document**")
    try:
        resp = requests.get(f"{API_BASE}/api/v1/documents", timeout=5)
        if resp.status_code == 200:
            docs = resp.json().get("data", {}).get("documents", [])
            doc_options = {f"{d['filename']} (ID: {d['id']})": d["id"] for d in docs}
            if doc_options:
                selected = st.selectbox(
                    "Select document", list(doc_options.keys()), label_visibility="collapsed"
                )
                st.session_state.selected_doc_id = doc_options[selected]
                st.session_state.selected_doc_name = selected.split(" (ID:")[0]
            else:
                st.info("No documents uploaded yet")
    except requests.ConnectionError:
        st.warning("Backend not reachable")
