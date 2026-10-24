from __future__ import annotations

from datetime import date, datetime
import io

import pandas as pd
import streamlit as st

from core.database import init_db
from core.security import validate_password
from services import school
from services.school import SchoolError
from ui.styles import apply_styles

st.set_page_config(page_title="School Management System", page_icon="🎓", layout="wide", initial_sidebar_state="expanded")
apply_styles()
init_db()


# ---------- Shared helpers ----------
def safe_action(fn, success_message: str | None = None) -> bool:
    try:
        fn()
    except SchoolError as exc:
        st.error(str(exc))
        return False
    except Exception as exc:
        # Keep private implementation/database details out of the user interface.
        st.error("Something went wrong while saving. Check the required fields and try again.")
        if st.session_state.get("auth_user", {}).get("role") == "admin":
            st.caption(f"Technical detail: {type(exc).__name__}")
        return False
    if success_message:
        # Persist a one-time message so it survives the rerun needed to refresh tables.
        st.session_state["_flash_message"] = success_message
        st.session_state["_flash_type"] = "success"
        st.rerun()
    return True


def clean_text(value: str | None) -> str:
    return (value or "").strip()


def check_optional_date(value: str) -> bool:
    if not value.strip():
        return True
    try:
        datetime.strptime(value.strip(), "%Y-%m-%d")
        return True
    except ValueError:
        return False


def fmt_inr(cents: int | float | None) -> str:
    amount = float(cents or 0) / 100
    return f"₹{amount:,.2f}"


def dataframe_download(rows: list[dict], filename: str, label: str = "Download CSV") -> None:
    if not rows:
        st.info("There is no data to export yet.")
        return
    df = pd.DataFrame(rows)
    payload = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(label, data=payload, file_name=filename, mime="text/csv")


def show_page_header(title: str, description: str = "") -> None:
    st.title(title)
    if description:
        st.markdown(f'<p class="muted">{description}</p>', unsafe_allow_html=True)


def student_label(row: dict) -> str:
    return f"{row['admission_no']} — {row['full_name']} (Class {row['class_name']}{('-' + row['section']) if row.get('section') else ''})"


def exam_label(row: dict) -> str:
    return f"{row['exam_name']} · {row['subject']} · Class {row['class_name']} · {row['exam_date']} (out of {row['max_marks']:g})"


def get_student_options(class_name: str | None = None) -> list[dict]:
    return school.list_students(active_only=True, class_name=class_name)


# ---------- Setup and authentication ----------
def setup_page() -> None:
    st.markdown('<div class="hero"><h2>Welcome to your School Management System</h2><p>Start with an administrator account. Your database will contain no sample students or demo records.</p></div>', unsafe_allow_html=True)
    left, center, right = st.columns([1, 1.35, 1])
    with center:
        with st.container(border=True):
            st.subheader("Create administrator account")
            st.write("This is a one-time setup. Choose a username and password that you can keep safe.")
            with st.form("initial_admin_form", clear_on_submit=True):
                username = st.text_input("Administrator username", placeholder="e.g. schooladmin")
