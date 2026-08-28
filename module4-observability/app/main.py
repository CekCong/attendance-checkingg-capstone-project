"""
SAIV Module 4 — Prometheus / Grafana still run from this folder.

Instructor UI now lives in the Next.js app:
http://localhost:3000/instructor
"""

import streamlit as st

st.set_page_config(page_title="SAIV", layout="centered")
st.title("Instructor UI moved")
st.info(
    "The instructor dashboard is the React app at http://localhost:3000/instructor. "
    "This Streamlit process is unused for teaching workflows."
)
