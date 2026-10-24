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
                password = st.text_input("Password (10+ characters, include a number)", type="password")
                confirm = st.text_input("Confirm password", type="password")
                submitted = st.form_submit_button("Create administrator", use_container_width=True)
            if submitted:
                if password != confirm:
                    st.error("The passwords do not match.")
                else:
                    ok = safe_action(lambda: school.create_initial_admin(username, password), "Administrator created. You can now sign in.")
                    if ok:
                        st.rerun()
        st.caption("No default username or password is created by the project.")


def login_page() -> None:
    st.markdown('<div class="hero"><h2>One school. One secure workspace.</h2><p>Manage student records, attendance, grades, fees, courses, and notices in one place.</p></div>', unsafe_allow_html=True)
    left, center, right = st.columns([1, 1.15, 1])
    with center:
        with st.container(border=True):
            st.subheader("Sign in")
            with st.form("login_form", clear_on_submit=True):
                username = st.text_input("Username", placeholder="Enter your assigned username")
                password = st.text_input("Password", type="password", placeholder="Enter your password")
                submitted = st.form_submit_button("Sign in", use_container_width=True)
            if submitted:
                user = school.authenticate(username, password)
                if user:
                    st.session_state.auth_user = user
                    st.rerun()
                else:
                    st.error("Sign-in failed. Check your username and password, or contact the administrator.")
    st.caption("Student and teacher accounts are created by your school administrator. There are no public sign-ups.")


def account_page(user: dict, force_change: bool = False) -> None:
    show_page_header("Account & Security", "Change your password and protect your account.")
    st.info(f"Signed in as **{user['username']}** · Role: **{user['role'].title()}**")
    if force_change:
        st.warning("Your password was assigned or reset by the administrator. Change it before continuing.")
    with st.form("change_password_form", clear_on_submit=True):
        current = st.text_input("Current password", type="password")
        new = st.text_input("New password (10+ characters, include a number)", type="password")
        confirm = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Update password", use_container_width=True)
    if submitted:
        if new != confirm:
            st.error("The new passwords do not match.")
        else:
            ok = safe_action(lambda: school.update_password(user["id"], current, new), "Password updated successfully.")
            if ok:
                refreshed = school.get_user(user["id"])
                st.session_state.auth_user = refreshed
                st.rerun()
    if user["role"] == "admin" and not force_change:
        with st.expander("Recent security activity"):
            logs = school.get_audit_logs(100)
            if logs:
                st.dataframe(pd.DataFrame(logs), use_container_width=True, hide_index=True)
            else:
                st.info("No activity recorded yet.")


# ---------- Dashboards ----------
def admin_dashboard(user: dict) -> None:
    st.markdown('<div class="hero"><h2>Good to see you, Administrator</h2><p>Your school overview. Metrics will appear as you enter real school data.</p></div>', unsafe_allow_html=True)
    m = school.dashboard_metrics("admin", user["id"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active students", f"{m['students']:,}")
    c2.metric("Active teachers", f"{m['teachers']:,}")
    c3.metric("Active courses", f"{m['courses']:,}")
    c4.metric("Attendance marked today", f"{m['attendance_today']:,}")
    f1, f2 = st.columns([1.3, 1])
    with f1:
        st.subheader("Get started")
        st.write("Use the sidebar to create student accounts, add teachers, set up courses, and enter attendance or assessment data.")
        st.markdown("- Student records and accounts are created by the administrator.\n- Passwords are stored as secure hashes, not readable text.\n- Historical attendance, marks, and fees are kept when an account is deactivated.")
    with f2:
        st.subheader("Outstanding fees")
        st.metric("Unpaid balance", fmt_inr(m["unpaid_cents"]))
        st.caption("This total reflects fee records currently marked Unpaid.")


def teacher_dashboard(user: dict) -> None:
    st.markdown('<div class="hero"><h2>Teacher workspace</h2><p>Access classes linked to your teacher account.</p></div>', unsafe_allow_html=True)
    m = school.dashboard_metrics("teacher", user["id"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Students in your assigned classes", f"{m['students']:,}")
    c2.metric("Active courses assigned", f"{len(school.list_courses(active_only=True, teacher_user_id=user['id'])):,}")
    c3.metric("Attendance marked today", f"{m['attendance_today']:,}")
    courses = school.list_courses(active_only=True, teacher_user_id=user["id"])
    st.subheader("Your assigned courses")
    if courses:
        st.dataframe(pd.DataFrame(courses)[["course_code", "course_name", "class_name", "subject", "status"]], use_container_width=True, hide_index=True)
    else:
        st.info("No courses have been assigned to this account yet. Ask the administrator to assign a course.")


def student_dashboard(user: dict) -> None:
    student = school.get_student_for_user(user["id"])
    if not student:
        st.error("This account is not linked to a student record. Contact the school administrator.")
        return
    m = school.dashboard_metrics("student", user["id"])
    st.markdown(f'<div class="hero"><h2>Welcome, {student["full_name"]}</h2><p>Admission No. {student["admission_no"]} · Class {student["class_name"]}{(" - " + student["section"]) if student["section"] else ""}</p></div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Attendance", f"{m['attendance_pct']}%" if m["attendance_pct"] is not None else "No records yet")
    c2.metric("Average assessment", f"{m['average_pct']}%" if m["average_pct"] is not None else "No grades yet")
    c3.metric("Outstanding fees", fmt_inr(m["outstanding_cents"]))
    st.subheader("Latest notices")
    notices = school.list_notices("student")[:5]
    if not notices:
        st.info("There are no published notices for you yet.")
    else:
        for notice in notices:
            with st.container(border=True):
                st.markdown(f"**{notice['title']}**")
                st.write(notice["body"])
                st.caption(f"Posted {notice['created_at']}")


# ---------- Student management ----------
def student_form_data(prefix: str, defaults: dict | None = None) -> dict:
    d = defaults or {}
    c1, c2, c3 = st.columns(3)
    with c1:
        admission_no = st.text_input("Admission number *", value=d.get("admission_no", ""), key=f"{prefix}_admission")
        full_name = st.text_input("Full name *", value=d.get("full_name", ""), key=f"{prefix}_name")
        class_name = st.text_input("Class *", value=d.get("class_name", ""), key=f"{prefix}_class", placeholder="e.g. 9")
        section = st.text_input("Section", value=d.get("section", ""), key=f"{prefix}_section")
    with c2:
        roll_no = st.text_input("Roll number", value=d.get("roll_no", ""), key=f"{prefix}_roll")
        gender = st.selectbox("Gender", ["", "Female", "Male", "Other", "Prefer not to say"], index=( ["", "Female", "Male", "Other", "Prefer not to say"].index(d.get("gender", "")) if d.get("gender", "") in ["", "Female", "Male", "Other", "Prefer not to say"] else 0), key=f"{prefix}_gender")
        dob = st.text_input("Date of birth (YYYY-MM-DD, optional)", value=d.get("date_of_birth", ""), key=f"{prefix}_dob")
        status = st.selectbox("Student status", ["Active", "Inactive"], index=0 if d.get("status", "Active") == "Active" else 1, key=f"{prefix}_status")
    with c3:
        guardian_name = st.text_input("Parent/guardian name", value=d.get("guardian_name", ""), key=f"{prefix}_guardian")
        guardian_phone = st.text_input("Parent/guardian phone", value=d.get("guardian_phone", ""), key=f"{prefix}_phone")
        guardian_email = st.text_input("Parent/guardian email", value=d.get("guardian_email", ""), key=f"{prefix}_email")
    address = st.text_area("Address (optional)", value=d.get("address", ""), key=f"{prefix}_address", height=70)
    return {"admission_no": admission_no, "full_name": full_name, "class_name": class_name,
            "section": section, "roll_no": roll_no, "gender": gender, "date_of_birth": dob.strip(),
            "status": status, "guardian_name": guardian_name, "guardian_phone": guardian_phone,
            "guardian_email": guardian_email, "address": address}


def student_management(user: dict) -> None:
    show_page_header("Students", "Create student records and issue each student a login username and password.")
    add_tab, manage_tab, reset_tab = st.tabs(["Add student", "Manage students", "Reset student password"])
    with add_tab:
        with st.form("add_student_form", clear_on_submit=True):
            data = student_form_data("new_student")
            st.markdown("#### Student login credentials")
            u1, u2 = st.columns(2)
            with u1:
                username = st.text_input("Student username *", key="new_student_username", placeholder="Must be unique; no spaces")
            with u2:
                password = st.text_input("Initial password *", type="password", key="new_student_password", help="At least 10 characters, including a number.")
            confirm = st.text_input("Confirm initial password *", type="password", key="new_student_confirm")
            submitted = st.form_submit_button("Save student and create login", use_container_width=True)
        if submitted:
            if not check_optional_date(data["date_of_birth"]):
                st.error("Use YYYY-MM-DD for date of birth, or leave it blank.")
            elif password != confirm:
                st.error("The passwords do not match.")
            else:
                ok = safe_action(lambda: school.create_student(user["id"], data, username, password), "Student record and login account created. The password is stored securely and cannot be viewed later.")
                if ok:
                    st.caption("Give the student their username and initial password through your school's secure process. They can change it in Account & Security.")
    with manage_tab:
        students = school.list_students()
        if not students:
            st.info("No student records yet. Use Add student to enter your first student.")
        else:
            df = pd.DataFrame(students)
            c1, c2 = st.columns([1, 2])
            with c1:
                class_filter = st.selectbox("Filter by class", ["All classes"] + sorted(df["class_name"].dropna().astype(str).unique().tolist()), key="students_class_filter")
            with c2:
                search = st.text_input("Search by name or admission number", key="students_search")
            filtered = df.copy()
            if class_filter != "All classes":
                filtered = filtered[filtered["class_name"] == class_filter]
            if search.strip():
                q = search.strip().lower()
                filtered = filtered[filtered.apply(lambda r: q in str(r["full_name"]).lower() or q in str(r["admission_no"]).lower(), axis=1)]
            show_cols = ["admission_no", "full_name", "class_name", "section", "roll_no", "username", "status", "account_active"]
            st.dataframe(filtered[show_cols], use_container_width=True, hide_index=True)
            dataframe_download(filtered[show_cols].to_dict("records"), "students.csv")
            st.divider()
            options = students
            selected = st.selectbox("Select a student to edit", options, format_func=student_label, key="edit_student_choice")
            if selected:
                current = school.get_student(selected["id"])
                with st.form("edit_student_form"):
                    updated = student_form_data(f"edit_student_{current['id']}", current)
                    save = st.form_submit_button("Save changes", use_container_width=True)
                if save:
                    if not check_optional_date(updated["date_of_birth"]):
                        st.error("Use YYYY-MM-DD for date of birth, or leave it blank.")
                    else:
                        safe_action(lambda: school.update_student(user["id"], current["id"], updated), "Student record updated.")
                with st.expander("Reset this student's login password"):
                    st.caption(f"Username: **{current['username']}**. Existing passwords cannot be recovered; set a new one instead.")
                    with st.form("inline_reset_student_password", clear_on_submit=True):
                        new_password = st.text_input("New temporary password", type="password", key="inline_reset_pwd")
                        new_confirm = st.text_input("Confirm temporary password", type="password", key="inline_reset_confirm")
                        reset = st.form_submit_button("Reset password and require a change")
                    if reset:
                        if new_password != new_confirm:
                            st.error("The passwords do not match.")
                        else:
                            safe_action(lambda: school.reset_password(user["id"], current["linked_user_id"], new_password), "Password reset. The student must change it after signing in.")
    with reset_tab:
        students = school.list_students()
        if not students:
            st.info("No student accounts exist yet.")
        else:
            selected = st.selectbox("Student account", students, format_func=student_label, key="reset_student_select")
            st.caption(f"Username: {selected['username']} · Admission No.: {selected['admission_no']}")
            with st.form("reset_student_password_form", clear_on_submit=True):
                p1 = st.text_input("New temporary password", type="password", key="reset_student_pwd_1")
                p2 = st.text_input("Confirm temporary password", type="password", key="reset_student_pwd_2")
                submitted = st.form_submit_button("Reset password", use_container_width=True)
            if submitted:
                if p1 != p2:
                    st.error("The passwords do not match.")
                else:
                    safe_action(lambda: school.reset_password(user["id"], selected["user_id"], p1), "Password reset. The student must change it after signing in.")


# ---------- Teachers ----------
def teacher_management(user: dict) -> None:
    show_page_header("Teachers", "Create teacher records and assign login credentials.")
    add_tab, manage_tab = st.tabs(["Add teacher", "Manage teachers"])
    with add_tab:
        with st.form("add_teacher_form", clear_on_submit=True):
            a, b = st.columns(2)
            with a:
                employee_no = st.text_input("Employee number *", key="add_teacher_employee_no")
                full_name = st.text_input("Teacher name *", key="add_teacher_full_name")
                subject = st.text_input("Primary subject", key="add_teacher_primary_subject")
            with b:
                phone = st.text_input("Phone", key="add_teacher_phone")
                email = st.text_input("Email", key="add_teacher_email")
                username = st.text_input("Login username *", key="add_teacher_username")
            password = st.text_input("Initial password *", type="password", key="add_teacher_password")
            confirm = st.text_input("Confirm initial password *", type="password", key="add_teacher_password_confirm")
            submitted = st.form_submit_button("Create teacher account", use_container_width=True)
        if submitted:
            if password != confirm:
                st.error("The passwords do not match.")
            else:
                data = {"employee_no": employee_no, "full_name": full_name, "subject": subject, "phone": phone, "email": email, "status": "Active"}
                safe_action(lambda: school.create_teacher(user["id"], data, username, password), "Teacher and login account created.")
    with manage_tab:
        teachers = school.list_teachers()
        if not teachers:
            st.info("No teacher records yet.")
        else:
            df = pd.DataFrame(teachers)
            st.dataframe(df[["employee_no", "full_name", "subject", "phone", "email", "username", "status", "account_active"]], use_container_width=True, hide_index=True)
            selected = st.selectbox("Select teacher to edit", teachers, format_func=lambda t: f"{t['employee_no']} — {t['full_name']}", key="edit_teacher_choice")
            with st.form("edit_teacher_form"):
                x1, x2 = st.columns(2)
                with x1:
                    emp = st.text_input("Employee number", value=selected["employee_no"], key=f"edit_teacher_employee_{selected['id']}")
                    name = st.text_input("Full name", value=selected["full_name"], key=f"edit_teacher_name_{selected['id']}")
                    sub = st.text_input("Subject", value=selected["subject"], key=f"edit_teacher_subject_{selected['id']}")
                with x2:
                    phone = st.text_input("Phone", value=selected["phone"], key=f"edit_teacher_phone_{selected['id']}")
                    email = st.text_input("Email", value=selected["email"], key=f"edit_teacher_email_{selected['id']}")
                    status = st.selectbox("Status", ["Active", "Inactive"], index=0 if selected["status"] == "Active" else 1, key=f"edit_teacher_status_{selected['id']}")
                save = st.form_submit_button("Save teacher changes", use_container_width=True)
            if save:
                data = {"employee_no": emp, "full_name": name, "subject": sub, "phone": phone, "email": email, "status": status}
                safe_action(lambda: school.update_teacher(user["id"], selected["id"], data), "Teacher record updated.")
            with st.expander("Reset teacher password"):
                with st.form("reset_teacher_password_form", clear_on_submit=True):
                    p1 = st.text_input("New temporary password", type="password", key=f"reset_teacher_password_{selected['id']}")
                    p2 = st.text_input("Confirm temporary password", type="password", key=f"reset_teacher_confirm_{selected['id']}")
                    do_reset = st.form_submit_button("Reset teacher password")
                if do_reset:
                    if p1 != p2:
                        st.error("The passwords do not match.")
                    else:
                        safe_action(lambda: school.reset_password(user["id"], selected["linked_user_id"], p1), "Password reset. The teacher must change it after signing in.")


# ---------- Courses ----------
def course_management(user: dict) -> None:
    show_page_header("Courses", "Set up courses and assign them to teacher accounts. Teacher access is based on these assignments.")
    teachers = school.list_teachers(active_only=True)
    if user["role"] == "admin":
        with st.expander("Add a course", expanded=not bool(school.list_courses())):
            with st.form("add_course_form"):
                c1, c2 = st.columns(2)
                with c1:
                    code = st.text_input("Course code *", placeholder="e.g. MATH-09", key="new_course_code")
                    name = st.text_input("Course name *", key="new_course_name")
                    cls = st.text_input("Class *", placeholder="Must match the class on student records", key="new_course_class")
                with c2:
                    subject = st.text_input("Subject *", key="new_course_subject")
                    teacher = st.selectbox("Assigned teacher", [None] + teachers, format_func=lambda t: "Unassigned" if t is None else f"{t['full_name']} ({t['employee_no']})", key="new_course_teacher")
                    status = st.selectbox("Status", ["Active", "Inactive"], key="new_course_status")
                submitted = st.form_submit_button("Save course", use_container_width=True)
            if submitted:
                data = {"course_code": code, "course_name": name, "class_name": cls, "subject": subject, "teacher_id": teacher["id"] if teacher else None, "status": status}
                safe_action(lambda: school.create_course(user["id"], data), "Course created.")
    courses = school.list_courses(active_only=(user["role"] != "admin"), teacher_user_id=user["id"] if user["role"] == "teacher" else None)
    if not courses:
        st.info("No courses to display. Administrators can add courses and assign teachers.")
        return
    df = pd.DataFrame(courses)
    st.dataframe(df[["course_code", "course_name", "class_name", "subject", "teacher_name", "status"]], use_container_width=True, hide_index=True)
    if user["role"] == "admin":
        with st.expander("Edit a course"):
            selected = st.selectbox("Course", courses, format_func=lambda c: f"{c['course_code']} — {c['course_name']}", key="edit_course_choice")
            current_teacher = next((t for t in teachers if t["id"] == selected["teacher_id"]), None)
            with st.form("edit_course_form"):
                x1, x2 = st.columns(2)
                with x1:
                    code = st.text_input("Course code", value=selected["course_code"], key=f"edit_course_code_{selected['id']}")
                    name = st.text_input("Course name", value=selected["course_name"], key=f"edit_course_name_{selected['id']}")
                    cls = st.text_input("Class", value=selected["class_name"], key=f"edit_course_class_{selected['id']}")
                with x2:
                    subject = st.text_input("Subject", value=selected["subject"], key=f"edit_course_subject_{selected['id']}")
                    teacher = st.selectbox("Assigned teacher", [None] + teachers, index=(([None] + teachers).index(current_teacher) if current_teacher in teachers else 0), format_func=lambda t: "Unassigned" if t is None else f"{t['full_name']} ({t['employee_no']})", key=f"edit_course_teacher_{selected['id']}")
                    status = st.selectbox("Status", ["Active", "Inactive"], index=0 if selected["status"] == "Active" else 1, key=f"edit_course_status_{selected['id']}")
                save = st.form_submit_button("Save course changes", use_container_width=True)
            if save:
                data = {"course_code": code, "course_name": name, "class_name": cls, "subject": subject, "teacher_id": teacher["id"] if teacher else None, "status": status}
                safe_action(lambda: school.update_course(user["id"], selected["id"], data), "Course updated.")


# ---------- Attendance ----------
def attendance_page(user: dict) -> None:
    show_page_header("Attendance", "Record attendance by class and date, then review or export attendance records.")
    classes = school.get_allowed_classes(user)
    if not classes:
        st.info("No class is available for your account. Add students and courses first; teachers must be assigned an active course.")
        return
    mark_tab, report_tab = st.tabs(["Mark attendance", "Attendance report"])
    with mark_tab:
        left, right = st.columns(2)
        with left:
            class_name = st.selectbox("Class", classes, key="attendance_class")
        with right:
            day = st.date_input("Attendance date", value=date.today(), key="attendance_date")
        roster = get_student_options(class_name)
        if not roster:
            st.info("No active students in this class yet. Add students with this exact class name first.")
        else:
            existing = {r["id"]: r["status"] for r in school.list_attendance(day.isoformat(), class_name)}
            st.caption(f"{len(roster)} active student(s) · Existing marks for this date are preselected.")
            with st.form("bulk_attendance_form"):
                statuses: dict[int, str] = {}
                for offset in range(0, len(roster), 2):
                    cols = st.columns(2)
                    for j, col in enumerate(cols):
                        if offset + j >= len(roster):
                            continue
                        student = roster[offset + j]
                        with col:
                            st.markdown(f"**{student['roll_no'] + ' · ' if student['roll_no'] else ''}{student['full_name']}**")
                            options = ["Present", "Absent", "Late", "Excused"]
                            default = existing.get(student["id"], "Present")
                            statuses[student["id"]] = st.selectbox("Status", options, index=options.index(default), key=f"att_{student['id']}_{day.isoformat()}")
                save = st.form_submit_button("Save attendance", use_container_width=True)
            if save:
                safe_action(lambda: school.save_attendance_bulk(user["id"], class_name, day.isoformat(), statuses), f"Attendance saved for {len(statuses)} student(s).")
    with report_tab:
        c1, c2 = st.columns(2)
        with c1:
            report_class = st.selectbox("Report class", classes, key="att_report_class")
        with c2:
            report_day = st.date_input("Report date", value=date.today(), key="att_report_day")
        rows = school.list_attendance(report_day.isoformat(), report_class)
        if rows:
            df = pd.DataFrame(rows)
            show = df[["admission_no", "full_name", "class_name", "section", "attendance_date", "status", "notes"]]
            st.dataframe(show, use_container_width=True, hide_index=True)
            dataframe_download(show.to_dict("records"), f"attendance_{report_day.isoformat()}.csv")
            counts = df["status"].value_counts().to_dict()
            st.write(" · ".join(f"**{k}:** {v}" for k, v in counts.items()))
        else:
            st.info("No attendance entries match this class and date.")


# ---------- Exams and grades ----------
def exams_grades_page(user: dict) -> None:
    show_page_header("Exams & Grades", "Create assessments and enter marks. A student's marks cannot exceed the exam's maximum score.")
    allowed_classes = school.get_allowed_classes(user) if user["role"] == "teacher" else None
    if user["role"] == "admin":
        with st.expander("Create exam", expanded=not bool(school.list_exams())):
            with st.form("create_exam_form"):
                c1, c2 = st.columns(2)
                with c1:
                    exam_name = st.text_input("Exam name *", placeholder="e.g. Unit Test 1")
                    class_name = st.text_input("Class *")
                    subject = st.text_input("Subject *")
                with c2:
                    exam_date = st.date_input("Exam date", value=date.today())
                    max_marks = st.number_input("Maximum marks", min_value=1.0, max_value=10000.0, value=100.0, step=1.0)
                submitted = st.form_submit_button("Create exam", use_container_width=True)
            if submitted:
                data = {"exam_name": exam_name, "class_name": class_name, "subject": subject, "exam_date": exam_date.isoformat(), "max_marks": max_marks}
                safe_action(lambda: school.create_exam(user["id"], data), "Exam created.")
    elif user["role"] == "teacher":
        if allowed_classes:
            with st.expander("Create exam for an assigned class"):
                with st.form("teacher_create_exam_form"):
                    exam_name = st.text_input("Exam name *")
                    class_name = st.selectbox("Assigned class", allowed_classes)
                    subject = st.text_input("Subject *")
                    exam_date = st.date_input("Exam date", value=date.today())
                    max_marks = st.number_input("Maximum marks", min_value=1.0, max_value=10000.0, value=100.0, step=1.0)
                    submitted = st.form_submit_button("Create exam", use_container_width=True)
                if submitted:
                    data = {"exam_name": exam_name, "class_name": class_name, "subject": subject, "exam_date": exam_date.isoformat(), "max_marks": max_marks}
                    safe_action(lambda: school.create_exam(user["id"], data), "Exam created.")
        else:
            st.info("The administrator must assign an active course to your account before you can manage grades.")
    exams = school.list_exams(allowed_classes if user["role"] == "teacher" else None)
    st.subheader("Assessments")
    if exams:
        st.dataframe(pd.DataFrame(exams)[["exam_name", "class_name", "subject", "exam_date", "max_marks"]], use_container_width=True, hide_index=True)
        st.divider()
        st.subheader("Enter or update a student's marks")
        selected_exam = st.selectbox("Exam", exams, format_func=exam_label, key="grade_exam_choice")
        students = get_student_options(selected_exam["class_name"])
        if not students:
            st.info("No active students match the exam's class name. Add student records with this class first.")
        else:
            with st.form("save_grade_form"):
                student = st.selectbox("Student", students, format_func=student_label)
                marks = st.number_input("Marks", min_value=0.0, max_value=float(selected_exam["max_marks"]), value=0.0, step=0.5)
                submitted = st.form_submit_button("Save marks", use_container_width=True)
            if submitted:
                if user["role"] == "teacher" and selected_exam["class_name"] not in (allowed_classes or []):
                    st.error("You can only manage exams for classes assigned to your account.")
                else:
                    safe_action(lambda: school.save_grade(user["id"], student["id"], selected_exam["id"], marks), "Marks saved.")
        grades = school.list_grades(class_names=allowed_classes if user["role"] == "teacher" else None)
        st.subheader("Gradebook")
        if grades:
            df = pd.DataFrame(grades)
            columns = ["admission_no", "full_name", "class_name", "exam_name", "subject", "exam_date", "marks", "max_marks", "percentage"]
            st.dataframe(df[columns], use_container_width=True, hide_index=True)
            dataframe_download(df[columns].to_dict("records"), "gradebook.csv")
        else:
            st.info("No marks have been entered yet.")
    else:
        st.info("No exams exist for the available classes yet.")


# ---------- Fees ----------
def fees_page(user: dict) -> None:
    show_page_header("Fee management", "Create fee records, track payments, and export the fee register.")
    students = school.list_students()
    if not students:
        st.info("Add student records before entering fees.")
        return
    add_tab, manage_tab = st.tabs(["Add fee", "Manage payments"])
    with add_tab:
        selected = st.selectbox("Student", students, format_func=student_label, key="fee_student_choice")
        with st.form("add_fee_form"):
            fee_type = st.text_input("Fee type *", placeholder="e.g. Term 1 tuition")
            amount = st.number_input("Amount (₹)", min_value=0.0, max_value=100000000.0, value=0.0, step=100.0)
            due_date = st.date_input("Due date", value=date.today())
            notes = st.text_area("Notes (optional)")
            submitted = st.form_submit_button("Create fee record", use_container_width=True)
        if submitted:
            safe_action(lambda: school.create_fee(user["id"], selected["id"], fee_type, amount, due_date.isoformat(), notes), "Fee record created.")
    with manage_tab:
        unpaid = school.list_fees(unpaid_only=True)
        all_fees = school.list_fees()
        if not all_fees:
            st.info("No fee records yet.")
        else:
            view = pd.DataFrame(all_fees)
            view["amount"] = view["amount"].map(lambda a: f"₹{float(a):,.2f}")
            st.dataframe(view[["admission_no", "full_name", "class_name", "fee_type", "amount", "due_date", "status", "paid_on"]], use_container_width=True, hide_index=True)
            dataframe_download([{**r, "amount": f"{float(r['amount']):.2f}"} for r in all_fees], "fees.csv")
            if unpaid:
                selected_fee = st.selectbox("Select an unpaid fee", unpaid, format_func=lambda f: f"{f['admission_no']} · {f['full_name']} · {f['fee_type']} · ₹{f['amount']:.2f} · due {f['due_date']}", key="unpaid_fee_choice")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Mark as paid", use_container_width=True):
                        safe_action(lambda: school.mark_fee_paid(user["id"], selected_fee["id"]), "Fee marked as paid.")
                with c2:
                    if st.button("Waive fee", use_container_width=True):
                        safe_action(lambda: school.waive_fee(user["id"], selected_fee["id"]), "Fee marked as waived.")
            else:
                st.success("There are no unpaid fee records.")


# ---------- Notices ----------
def notices_page(user: dict) -> None:
    show_page_header("Notice board", "Share official school announcements with the appropriate audience.")
    if user["role"] == "admin":
        with st.expander("Publish a notice", expanded=not bool(school.list_notices("admin", include_unpublished=True))):
            with st.form("create_notice_form"):
                title = st.text_input("Notice title *")
                body = st.text_area("Message *", height=140)
                audience = st.selectbox("Audience", ["Everyone", "Students", "Teachers"])
                published = st.checkbox("Publish immediately", value=True)
                submitted = st.form_submit_button("Save notice", use_container_width=True)
            if submitted:
                safe_action(lambda: school.create_notice(user["id"], title, body, audience, published), "Notice saved.")
    notices = school.list_notices(user["role"], include_unpublished=(user["role"] == "admin"))
    if not notices:
        st.info("No notices to display.")
        return
    for notice in notices:
        with st.container(border=True):
            top1, top2 = st.columns([4, 1])
            with top1:
                st.markdown(f"### {notice['title']}")
                st.caption(f"Audience: {notice['audience']} · Posted {notice['created_at']} · By {notice['author_username']}")
            with top2:
                if user["role"] == "admin":
                    st.caption("Published" if notice["is_published"] else "Draft")
                    if notice["is_published"]:
                        if st.button("Unpublish", key=f"unpub_{notice['id']}"):
                            safe_action(lambda nid=notice["id"]: school.set_notice_published(user["id"], nid, False), "Notice unpublished.")
                    else:
                        if st.button("Publish", key=f"pub_{notice['id']}"):
                            safe_action(lambda nid=notice["id"]: school.set_notice_published(user["id"], nid, True), "Notice published.")
            st.write(notice["body"])


# ---------- Student-only pages ----------
def student_attendance_page(user: dict) -> None:
    show_page_header("My attendance", "Your attendance history and current summary.")
    student = school.get_student_for_user(user["id"])
    if not student:
        st.info("Your account is not linked to a student record. Contact the administrator.")
        return
    rows = school.get_student_attendance(student["id"])
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df[["attendance_date", "status", "notes"]], use_container_width=True, hide_index=True)
        dataframe_download(df[["attendance_date", "status", "notes"]].to_dict("records"), "my_attendance.csv")
        attended = int(df["status"].isin(["Present", "Late"]).sum())
        st.metric("Attendance rate", f"{attended / len(df) * 100:.1f}%")
    else:
        st.info("No attendance has been entered for your student record yet.")


def student_grades_page(user: dict) -> None:
    show_page_header("My grades", "Assessment results recorded by your school.")
    student = school.get_student_for_user(user["id"])
    if not student:
        st.info("Your account is not linked to a student record.")
        return
    grades = school.list_grades(student_id=student["id"])
    if grades:
        df = pd.DataFrame(grades)
        st.dataframe(df[["exam_name", "subject", "exam_date", "marks", "max_marks", "percentage"]], use_container_width=True, hide_index=True)
        dataframe_download(df.to_dict("records"), "my_grades.csv")
    else:
        st.info("No grades have been entered for you yet.")


def student_fees_page(user: dict) -> None:
    show_page_header("My fees", "View fee records entered by your school. Payments are updated by school staff.")
    student = school.get_student_for_user(user["id"])
    if not student:
        st.info("Your account is not linked to a student record.")
        return
    fees = school.list_fees(student_id=student["id"])
    if fees:
        total_unpaid = sum(r["amount"] for r in fees if r["status"] == "Unpaid")
        st.metric("Outstanding amount", f"₹{total_unpaid:,.2f}")
        df = pd.DataFrame(fees)
        df["amount"] = df["amount"].map(lambda a: f"₹{float(a):,.2f}")
        st.dataframe(df[["fee_type", "amount", "due_date", "status", "paid_on", "notes"]], use_container_width=True, hide_index=True)
    else:
        st.info("No fee records are linked to your student profile yet.")


def student_profile_page(user: dict) -> None:
    show_page_header("My profile", "The profile information entered by the school administrator.")
    student = school.get_student_for_user(user["id"])
    if not student:
        st.info("Your account is not linked to a student record.")
        return
    cols = st.columns(3)
    for col, label, key in [
        (cols[0], "Full name", "full_name"), (cols[1], "Admission number", "admission_no"),
        (cols[2], "Username", "username"), (cols[0], "Class", "class_name"),
        (cols[1], "Section", "section"), (cols[2], "Roll number", "roll_no"),
        (cols[0], "Parent/guardian", "guardian_name"), (cols[1], "Guardian phone", "guardian_phone"),
        (cols[2], "Guardian email", "guardian_email"), (cols[0], "Date of birth", "date_of_birth"),
        (cols[1], "Address", "address"), (cols[2], "Record status", "status")]:
        col.markdown(f"**{label}**")
        col.write(student.get(key) or "—")
        col.markdown(" ")


# ---------- Reports ----------
def reports_page() -> None:
    show_page_header("Reports & exports", "Download current school data as CSV files for your own reporting or backup workflow.")
    report_name = st.selectbox("Choose report", ["Students", "Attendance", "Grades", "Fees"])
    rows = school.report_rows(report_name)
    st.caption(f"{len(rows):,} record(s) in this report.")
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
        dataframe_download(rows, f"{report_name.lower()}_report.csv", "Download report as CSV")
    else:
        st.info("No records available for this report yet. Add real school data to populate it.")


# ---------- Application routing ----------
def main() -> None:
    flash_message = st.session_state.pop("_flash_message", None)
    flash_type = st.session_state.pop("_flash_type", "success")
    if flash_message:
        if flash_type == "success":
            st.success(flash_message)
        else:
            st.info(flash_message)
    if school.user_count() == 0:
        setup_page()
        return

    session_user = st.session_state.get("auth_user")
    if not session_user:
        login_page()
        return

    current = school.get_user(session_user["id"])
    if not current or not current["is_active"]:
        st.session_state.pop("auth_user", None)
        st.warning("This account is inactive or no longer available. Please contact the administrator.")
        st.rerun()
        return
    st.session_state.auth_user = current
    user = current

    if user.get("must_change_password"):
        with st.sidebar:
            st.markdown("## School OS")
            st.caption(f"Signed in: {user['username']}")
            if st.button("Sign out", use_container_width=True):
                st.session_state.pop("auth_user", None)
                st.rerun()
        account_page(user, force_change=True)
        return

    with st.sidebar:
        st.markdown("# EDU<span style='color:#b22fe5'>•</span>OS", unsafe_allow_html=True)
        st.caption("School Management System")
        st.divider()
        st.markdown(f"**{user['username']}**")
        st.caption(user["role"].title() + " account")
        if user["role"] == "admin":
            pages = ["Dashboard", "Students", "Teachers", "Courses", "Attendance", "Exams & Grades", "Fees", "Notice Board", "Reports & Exports", "Account & Security"]
        elif user["role"] == "teacher":
            pages = ["Dashboard", "Students", "Courses", "Attendance", "Exams & Grades", "Notice Board", "Account & Security"]
        else:
            pages = ["My Dashboard", "My Profile", "My Attendance", "My Grades", "My Fees", "Notice Board", "Account & Security"]
        selected_page = st.radio("Navigation", pages, label_visibility="collapsed")
        st.divider()
        if st.button("Sign out", use_container_width=True):
            st.session_state.pop("auth_user", None)
            st.rerun()
        st.caption("Your school data stays in the configured database file.")

    if selected_page == "Dashboard":
        admin_dashboard(user) if user["role"] == "admin" else teacher_dashboard(user)
    elif selected_page == "My Dashboard":
        student_dashboard(user)
    elif selected_page == "Students":
        if user["role"] == "admin":
            student_management(user)
        elif user["role"] == "teacher":
            allowed = school.get_allowed_classes(user)
            rows = [r for r in school.list_students(active_only=True) if r["class_name"] in allowed]
            show_page_header("Students", "Student directory for your assigned classes.")
            if rows:
                df = pd.DataFrame(rows)
                st.dataframe(df[["admission_no", "full_name", "class_name", "section", "roll_no", "status"]], use_container_width=True, hide_index=True)
            else:
                st.info("No students are available in your assigned classes.")
    elif selected_page == "Teachers":
        teacher_management(user)
    elif selected_page == "Courses":
        course_management(user)
    elif selected_page == "Attendance":
        attendance_page(user)
    elif selected_page == "Exams & Grades":
        exams_grades_page(user)
    elif selected_page == "Fees":
        fees_page(user)
    elif selected_page == "Notice Board":
        notices_page(user)
    elif selected_page == "Reports & Exports":
        reports_page()
    elif selected_page == "My Profile":
        student_profile_page(user)
    elif selected_page == "My Attendance":
        student_attendance_page(user)
    elif selected_page == "My Grades":
        student_grades_page(user)
    elif selected_page == "My Fees":
        student_fees_page(user)
    elif selected_page == "Account & Security":
        account_page(user)


if __name__ == "__main__":
    main()
