"""Application data services for the school management system."""
from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from core.database import db_session, row_to_dict, rows_to_dicts
from core.security import hash_password, verify_password, validate_password


class SchoolError(Exception):
    """Expected, user-facing validation or database error."""


def _audit(conn: sqlite3.Connection, actor_id: int | None, action: str,
           entity_type: str = "", entity_id: Any = "", details: str = "") -> None:
    conn.execute(
        "INSERT INTO audit_logs(actor_user_id, action, entity_type, entity_id, details) VALUES (?, ?, ?, ?, ?)",
        (actor_id, action, entity_type, str(entity_id), details[:500]),
    )


def _create_user(conn: sqlite3.Connection, username: str, password: str, role: str,
                 must_change: bool = False) -> int:
    username = username.strip()
    if not username or len(username) < 3 or len(username) > 60:
        raise SchoolError("Username must be between 3 and 60 characters.")
    if any(ch.isspace() for ch in username):
        raise SchoolError("Username cannot contain spaces.")
    password_error = validate_password(password)
    if password_error:
        raise SchoolError(password_error)
    try:
        cur = conn.execute(
            "INSERT INTO users(username, password_hash, role, must_change_password) VALUES (?, ?, ?, ?)",
            (username, hash_password(password), role, int(must_change)),
        )
    except sqlite3.IntegrityError as exc:
        if "username" in str(exc).lower():
            raise SchoolError("That username is already in use. Choose another one.") from exc
        raise SchoolError("Could not create the account. Check the entered details.") from exc
    return int(cur.lastrowid)


def user_count() -> int:
    with db_session() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])


def create_initial_admin(username: str, password: str) -> None:
    with db_session() as conn:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] != 0:
            raise SchoolError("Initial setup has already been completed. Please sign in.")
        user_id = _create_user(conn, username, password, "admin", False)
        _audit(conn, user_id, "created_initial_admin", "user", user_id)


def authenticate(username: str, password: str) -> dict | None:
    with db_session() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username.strip(),)).fetchone()
        if not row or not row["is_active"] or not verify_password(password, row["password_hash"]):
            return None
        _audit(conn, row["id"], "login", "user", row["id"])
        return {k: row[k] for k in ("id", "username", "role", "is_active", "must_change_password")}


def get_user(user_id: int) -> dict | None:
    with db_session() as conn:
        return row_to_dict(conn.execute("SELECT id, username, role, is_active, must_change_password FROM users WHERE id=?", (user_id,)).fetchone())


def update_password(user_id: int, current_password: str, new_password: str) -> None:
    error = validate_password(new_password)
    if error:
        raise SchoolError(error)
    with db_session() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id=? AND is_active=1", (user_id,)).fetchone()
        if not row or not verify_password(current_password, row["password_hash"]):
            raise SchoolError("Current password is incorrect.")
        conn.execute("UPDATE users SET password_hash=?, must_change_password=0, updated_at=CURRENT_TIMESTAMP WHERE id=?", (hash_password(new_password), user_id))
        _audit(conn, user_id, "changed_password", "user", user_id)


def reset_password(actor_id: int, target_user_id: int, new_password: str) -> None:
    error = validate_password(new_password)
    if error:
        raise SchoolError(error)
    with db_session() as conn:
        target = conn.execute("SELECT id, role FROM users WHERE id=?", (target_user_id,)).fetchone()
        if not target:
            raise SchoolError("Account not found.")
        if target["role"] == "admin" and actor_id != target_user_id:
            raise SchoolError("An administrator cannot reset another administrator's password from this screen.")
        conn.execute("UPDATE users SET password_hash=?, must_change_password=1, updated_at=CURRENT_TIMESTAMP WHERE id=?", (hash_password(new_password), target_user_id))
        _audit(conn, actor_id, "reset_password", "user", target_user_id)


def _ensure_active_actor(conn: sqlite3.Connection, actor_id: int) -> None:
    row = conn.execute("SELECT role, is_active FROM users WHERE id=?", (actor_id,)).fetchone()
    if not row or not row["is_active"]:
        raise SchoolError("Your account is inactive. Contact the administrator.")


def list_students(active_only: bool = False, class_name: str | None = None) -> list[dict]:
    sql = """SELECT s.*, u.username, u.is_active AS account_active
             FROM students s JOIN users u ON u.id=s.user_id WHERE 1=1"""
    args: list[Any] = []
    if active_only:
        sql += " AND s.status='Active' AND u.is_active=1"
    if class_name:
        sql += " AND s.class_name=?"
        args.append(class_name)
    sql += " ORDER BY s.class_name, s.section, s.roll_no, s.full_name"
    with db_session() as conn:
        return rows_to_dicts(conn.execute(sql, args).fetchall())


def get_student(student_id: int) -> dict | None:
    with db_session() as conn:
        return row_to_dict(conn.execute("""SELECT s.*, u.username, u.is_active AS account_active,
              u.id AS linked_user_id FROM students s JOIN users u ON s.user_id=u.id WHERE s.id=?""", (student_id,)).fetchone())


def get_student_for_user(user_id: int) -> dict | None:
    with db_session() as conn:
        return row_to_dict(conn.execute("SELECT * FROM students WHERE user_id=?", (user_id,)).fetchone())


def create_student(actor_id: int, data: dict, username: str, password: str) -> int:
    required = {"admission_no": "Admission number", "full_name": "Student name", "class_name": "Class"}
    for key, label in required.items():
        if not str(data.get(key, "")).strip():
            raise SchoolError(f"{label} is required.")
    with db_session() as conn:
        _ensure_active_actor(conn, actor_id)
        user_id = _create_user(conn, username, password, "student", False)
        try:
            cur = conn.execute("""INSERT INTO students(
              user_id, admission_no, full_name, gender, date_of_birth, class_name, section,
              roll_no, guardian_name, guardian_phone, guardian_email, address, status)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (user_id, data["admission_no"].strip(), data["full_name"].strip(), data.get("gender", ""),
               data.get("date_of_birth", ""), data["class_name"].strip(), data.get("section", "").strip(),
               data.get("roll_no", "").strip(), data.get("guardian_name", "").strip(),
               data.get("guardian_phone", "").strip(), data.get("guardian_email", "").strip(),
               data.get("address", "").strip(), data.get("status", "Active")))
        except sqlite3.IntegrityError as exc:
            message = str(exc).lower()
            if "admission_no" in message:
                raise SchoolError("That admission number already exists.") from exc
            raise SchoolError("Student could not be saved. Check admission number and required fields.") from exc
        student_id = int(cur.lastrowid)
        _audit(conn, actor_id, "created_student", "student", student_id, f"Admission number: {data['admission_no']}")
        return student_id


def update_student(actor_id: int, student_id: int, data: dict) -> None:
    for key in ("admission_no", "full_name", "class_name"):
        if not str(data.get(key, "")).strip():
            raise SchoolError(f"{key.replace('_', ' ').title()} is required.")
    with db_session() as conn:
        try:
            conn.execute("""UPDATE students SET admission_no=?, full_name=?, gender=?, date_of_birth=?,
              class_name=?, section=?, roll_no=?, guardian_name=?, guardian_phone=?, guardian_email=?,
              address=?, status=? WHERE id=?""",
              (data["admission_no"].strip(), data["full_name"].strip(), data.get("gender", ""),
               data.get("date_of_birth", ""), data["class_name"].strip(), data.get("section", "").strip(),
               data.get("roll_no", "").strip(), data.get("guardian_name", "").strip(),
               data.get("guardian_phone", "").strip(), data.get("guardian_email", "").strip(),
               data.get("address", "").strip(), data.get("status", "Active"), student_id))
            if conn.execute("SELECT changes()").fetchone()[0] == 0:
                raise SchoolError("Student not found.")
            student = conn.execute("SELECT user_id, status FROM students WHERE id=?", (student_id,)).fetchone()
            conn.execute("UPDATE users SET is_active=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(student["status"] == "Active"), student["user_id"]))
        except sqlite3.IntegrityError as exc:
            raise SchoolError("That admission number is already in use.") from exc
        _audit(conn, actor_id, "updated_student", "student", student_id)


def set_student_account_active(actor_id: int, student_id: int, active: bool) -> None:
    with db_session() as conn:
        row = conn.execute("SELECT user_id FROM students WHERE id=?", (student_id,)).fetchone()
        if not row:
            raise SchoolError("Student not found.")
        conn.execute("UPDATE users SET is_active=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(active), row["user_id"]))
        conn.execute("UPDATE students SET status=? WHERE id=?", ("Active" if active else "Inactive", student_id))
        _audit(conn, actor_id, "activated_student" if active else "deactivated_student", "student", student_id)


def list_teachers(active_only: bool = False) -> list[dict]:
    sql = "SELECT t.*, u.username, u.id AS linked_user_id, u.is_active AS account_active FROM teachers t JOIN users u ON u.id=t.user_id"
    if active_only:
        sql += " WHERE t.status='Active' AND u.is_active=1"
    sql += " ORDER BY t.full_name"
    with db_session() as conn:
        return rows_to_dicts(conn.execute(sql).fetchall())


def get_teacher_for_user(user_id: int) -> dict | None:
    with db_session() as conn:
        return row_to_dict(conn.execute("SELECT * FROM teachers WHERE user_id=?", (user_id,)).fetchone())


def create_teacher(actor_id: int, data: dict, username: str, password: str) -> int:
    if not data.get("employee_no", "").strip() or not data.get("full_name", "").strip():
        raise SchoolError("Employee number and teacher name are required.")
    with db_session() as conn:
        user_id = _create_user(conn, username, password, "teacher", False)
        try:
            cur = conn.execute("INSERT INTO teachers(user_id, employee_no, full_name, subject, phone, email, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                               (user_id, data["employee_no"].strip(), data["full_name"].strip(), data.get("subject", "").strip(), data.get("phone", "").strip(), data.get("email", "").strip(), data.get("status", "Active")))
        except sqlite3.IntegrityError as exc:
            raise SchoolError("That employee number already exists.") from exc
        teacher_id = int(cur.lastrowid)
        _audit(conn, actor_id, "created_teacher", "teacher", teacher_id)
        return teacher_id


def update_teacher(actor_id: int, teacher_id: int, data: dict) -> None:
    with db_session() as conn:
        try:
            row = conn.execute("SELECT user_id FROM teachers WHERE id=?", (teacher_id,)).fetchone()
            if not row:
                raise SchoolError("Teacher not found.")
            conn.execute("UPDATE teachers SET employee_no=?, full_name=?, subject=?, phone=?, email=?, status=? WHERE id=?",
                         (data["employee_no"].strip(), data["full_name"].strip(), data.get("subject", "").strip(), data.get("phone", "").strip(), data.get("email", "").strip(), data.get("status", "Active"), teacher_id))
            conn.execute("UPDATE users SET is_active=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(data.get("status", "Active") == "Active"), row["user_id"]))
        except sqlite3.IntegrityError as exc:
            raise SchoolError("That employee number is already in use.") from exc
        _audit(conn, actor_id, "updated_teacher", "teacher", teacher_id)


def get_classes() -> list[str]:
    with db_session() as conn:
        rows = conn.execute("SELECT class_name FROM students WHERE status='Active' UNION SELECT class_name FROM courses WHERE status='Active' ORDER BY class_name").fetchall()
    return [r[0] for r in rows]


def get_allowed_classes(user: dict) -> list[str]:
    if user["role"] == "admin":
        return get_classes()
    if user["role"] == "teacher":
        with db_session() as conn:
            rows = conn.execute("""SELECT DISTINCT c.class_name FROM courses c JOIN teachers t ON t.id=c.teacher_id
                     WHERE t.user_id=? AND c.status='Active' AND t.status='Active' ORDER BY c.class_name""", (user["id"],)).fetchall()
        return [r[0] for r in rows]
    student = get_student_for_user(user["id"])
    return [student["class_name"]] if student else []


def list_courses(active_only: bool = False, teacher_user_id: int | None = None) -> list[dict]:
    sql = """SELECT c.*, t.full_name AS teacher_name FROM courses c LEFT JOIN teachers t ON t.id=c.teacher_id WHERE 1=1"""
    args: list[Any] = []
    if active_only:
        sql += " AND c.status='Active'"
    if teacher_user_id is not None:
        sql += " AND t.user_id=?"
        args.append(teacher_user_id)
    sql += " ORDER BY c.class_name, c.subject, c.course_name"
    with db_session() as conn:
        return rows_to_dicts(conn.execute(sql, args).fetchall())


def create_course(actor_id: int, data: dict) -> int:
    if not all(str(data.get(k, "")).strip() for k in ("course_code", "course_name", "class_name", "subject")):
        raise SchoolError("Course code, course name, class, and subject are required.")
    with db_session() as conn:
        try:
            cur = conn.execute("INSERT INTO courses(course_code, course_name, class_name, subject, teacher_id, status) VALUES (?, ?, ?, ?, ?, ?)",
                               (data["course_code"].strip(), data["course_name"].strip(), data["class_name"].strip(), data["subject"].strip(), data.get("teacher_id") or None, data.get("status", "Active")))
        except sqlite3.IntegrityError as exc:
            raise SchoolError("That course code already exists, or the selected teacher is invalid.") from exc
        course_id = int(cur.lastrowid)
        _audit(conn, actor_id, "created_course", "course", course_id)
        return course_id


def update_course(actor_id: int, course_id: int, data: dict) -> None:
    with db_session() as conn:
        try:
            conn.execute("UPDATE courses SET course_code=?, course_name=?, class_name=?, subject=?, teacher_id=?, status=? WHERE id=?",
                         (data["course_code"].strip(), data["course_name"].strip(), data["class_name"].strip(), data["subject"].strip(), data.get("teacher_id") or None, data.get("status", "Active"), course_id))
        except sqlite3.IntegrityError as exc:
            raise SchoolError("That course code is already in use.") from exc
        if conn.execute("SELECT changes()").fetchone()[0] == 0:
            raise SchoolError("Course not found.")
        _audit(conn, actor_id, "updated_course", "course", course_id)


def list_attendance(attendance_date: str | None = None, class_name: str | None = None, student_id: int | None = None) -> list[dict]:
    sql = """SELECT a.*, s.admission_no, s.full_name, s.class_name, s.section, s.roll_no, u.username AS marked_by_username
             FROM attendance a JOIN students s ON s.id=a.student_id JOIN users u ON u.id=a.marked_by WHERE 1=1"""
    args: list[Any] = []
    if attendance_date:
        sql += " AND a.attendance_date=?"; args.append(attendance_date)
    if class_name:
        sql += " AND s.class_name=?"; args.append(class_name)
    if student_id is not None:
        sql += " AND s.id=?"; args.append(student_id)
    sql += " ORDER BY s.class_name, s.section, s.roll_no, s.full_name"
    with db_session() as conn:
        return rows_to_dicts(conn.execute(sql, args).fetchall())


def save_attendance_bulk(actor_id: int, class_name: str, attendance_date: str, statuses: dict[int, str]) -> int:
    if not class_name:
        raise SchoolError("Select a class first.")
    if not attendance_date:
        raise SchoolError("Attendance date is required.")
    valid_statuses = {"Present", "Absent", "Late", "Excused"}
    with db_session() as conn:
        for student_id, status in statuses.items():
            if status not in valid_statuses:
                raise SchoolError("Invalid attendance status.")
            exists = conn.execute("SELECT id FROM students WHERE id=? AND class_name=? AND status='Active'", (student_id, class_name)).fetchone()
            if not exists:
                continue
            conn.execute("""INSERT INTO attendance(student_id, attendance_date, status, marked_by)
              VALUES (?, ?, ?, ?) ON CONFLICT(student_id, attendance_date) DO UPDATE SET
              status=excluded.status, marked_by=excluded.marked_by, updated_at=CURRENT_TIMESTAMP""",
              (student_id, attendance_date, status, actor_id))
        _audit(conn, actor_id, "saved_attendance", "attendance", attendance_date, f"Class: {class_name}; records: {len(statuses)}")
    return len(statuses)


def list_exams(class_names: list[str] | None = None) -> list[dict]:
    sql = "SELECT * FROM exams"
    args: list[Any] = []
    if class_names is not None:
        if not class_names:
            return []
        marks = ",".join("?" for _ in class_names)
        sql += f" WHERE class_name IN ({marks})"
        args.extend(class_names)
    sql += " ORDER BY exam_date DESC, exam_name"
    with db_session() as conn:
        return rows_to_dicts(conn.execute(sql, args).fetchall())


def create_exam(actor_id: int, data: dict) -> int:
    if not all(str(data.get(k, "")).strip() for k in ("exam_name", "class_name", "subject", "exam_date")):
        raise SchoolError("Exam name, class, subject, and date are required.")
    max_marks = float(data.get("max_marks", 0))
    if max_marks <= 0:
        raise SchoolError("Maximum marks must be greater than zero.")
    with db_session() as conn:
        cur = conn.execute("INSERT INTO exams(exam_name, class_name, subject, exam_date, max_marks, created_by) VALUES (?, ?, ?, ?, ?, ?)",
                           (data["exam_name"].strip(), data["class_name"].strip(), data["subject"].strip(), data["exam_date"], max_marks, actor_id))
        exam_id = int(cur.lastrowid)
        _audit(conn, actor_id, "created_exam", "exam", exam_id)
        return exam_id


def list_grades(exam_id: int | None = None, student_id: int | None = None, class_names: list[str] | None = None) -> list[dict]:
    sql = """SELECT g.*, s.admission_no, s.full_name, s.class_name, s.section,
             e.exam_name, e.subject, e.exam_date, e.max_marks,
             ROUND((g.marks / e.max_marks) * 100, 2) AS percentage
             FROM grades g JOIN students s ON s.id=g.student_id JOIN exams e ON e.id=g.exam_id WHERE 1=1"""
    args: list[Any] = []
    if exam_id is not None:
        sql += " AND g.exam_id=?"; args.append(exam_id)
    if student_id is not None:
        sql += " AND g.student_id=?"; args.append(student_id)
    if class_names is not None:
        if not class_names:
            return []
        marks = ",".join("?" for _ in class_names)
        sql += f" AND s.class_name IN ({marks})"; args.extend(class_names)
    sql += " ORDER BY e.exam_date DESC, s.class_name, s.full_name"
    with db_session() as conn:
        return rows_to_dicts(conn.execute(sql, args).fetchall())


def save_grade(actor_id: int, student_id: int, exam_id: int, marks: float) -> None:
    with db_session() as conn:
        exam = conn.execute("SELECT max_marks, class_name FROM exams WHERE id=?", (exam_id,)).fetchone()
        student = conn.execute("SELECT class_name FROM students WHERE id=? AND status='Active'", (student_id,)).fetchone()
        if not exam or not student:
            raise SchoolError("Select a valid exam and active student.")
        if student["class_name"] != exam["class_name"]:
            raise SchoolError("The student must belong to the exam's class.")
        if marks < 0 or marks > exam["max_marks"]:
            raise SchoolError(f"Marks must be from 0 to {exam['max_marks']:g}.")
        conn.execute("INSERT INTO grades(student_id, exam_id, marks) VALUES (?, ?, ?) ON CONFLICT(student_id, exam_id) DO UPDATE SET marks=excluded.marks, created_at=CURRENT_TIMESTAMP", (student_id, exam_id, marks))
        _audit(conn, actor_id, "saved_grade", "grade", f"{student_id}:{exam_id}")


def list_fees(student_id: int | None = None, unpaid_only: bool = False) -> list[dict]:
    sql = """SELECT f.*, s.admission_no, s.full_name, s.class_name, s.section,
             (f.amount_cents / 100.0) AS amount FROM fee_records f JOIN students s ON s.id=f.student_id WHERE 1=1"""
    args: list[Any] = []
    if student_id is not None:
        sql += " AND f.student_id=?"; args.append(student_id)
    if unpaid_only:
        sql += " AND f.status='Unpaid'"
    sql += " ORDER BY f.due_date DESC, s.full_name"
    with db_session() as conn:
        return rows_to_dicts(conn.execute(sql, args).fetchall())


def create_fee(actor_id: int, student_id: int, fee_type: str, amount: float, due_date: str, notes: str = "") -> int:
    if not fee_type.strip():
        raise SchoolError("Fee type is required.")
    if amount < 0:
        raise SchoolError("Fee amount cannot be negative.")
    with db_session() as conn:
        if not conn.execute("SELECT id FROM students WHERE id=?", (student_id,)).fetchone():
            raise SchoolError("Student not found.")
        cur = conn.execute("INSERT INTO fee_records(student_id, fee_type, amount_cents, due_date, notes, created_by) VALUES (?, ?, ?, ?, ?, ?)", (student_id, fee_type.strip(), int(round(amount * 100)), due_date, notes.strip(), actor_id))
        fee_id = int(cur.lastrowid)
        _audit(conn, actor_id, "created_fee", "fee", fee_id)
        return fee_id


def mark_fee_paid(actor_id: int, fee_id: int) -> None:
    with db_session() as conn:
        conn.execute("UPDATE fee_records SET status='Paid', paid_on=? WHERE id=? AND status='Unpaid'", (date.today().isoformat(), fee_id))
        if conn.execute("SELECT changes()").fetchone()[0] == 0:
            raise SchoolError("Unpaid fee record not found, or it has already been updated.")
        _audit(conn, actor_id, "marked_fee_paid", "fee", fee_id)


def waive_fee(actor_id: int, fee_id: int) -> None:
    with db_session() as conn:
        conn.execute("UPDATE fee_records SET status='Waived' WHERE id=? AND status='Unpaid'", (fee_id,))
        if conn.execute("SELECT changes()").fetchone()[0] == 0:
            raise SchoolError("Unpaid fee record not found, or it has already been updated.")
        _audit(conn, actor_id, "waived_fee", "fee", fee_id)


def create_notice(actor_id: int, title: str, body: str, audience: str, published: bool = True) -> int:
    if not title.strip() or not body.strip():
        raise SchoolError("Notice title and message are required.")
    if audience not in {"Everyone", "Students", "Teachers"}:
        raise SchoolError("Select a valid audience.")
    with db_session() as conn:
        cur = conn.execute("INSERT INTO notices(title, body, audience, is_published, created_by) VALUES (?, ?, ?, ?, ?)", (title.strip(), body.strip(), audience, int(published), actor_id))
        notice_id = int(cur.lastrowid)
        _audit(conn, actor_id, "created_notice", "notice", notice_id)
        return notice_id


def list_notices(role: str, include_unpublished: bool = False) -> list[dict]:
    sql = "SELECT n.*, u.username AS author_username FROM notices n JOIN users u ON u.id=n.created_by WHERE 1=1"
    args: list[Any] = []
    if not include_unpublished:
        sql += " AND n.is_published=1"
    if role == "student":
        sql += " AND n.audience IN ('Everyone', 'Students')"
    elif role == "teacher":
        sql += " AND n.audience IN ('Everyone', 'Teachers')"
    sql += " ORDER BY n.created_at DESC, n.id DESC"
    with db_session() as conn:
        return rows_to_dicts(conn.execute(sql, args).fetchall())


def set_notice_published(actor_id: int, notice_id: int, published: bool) -> None:
    with db_session() as conn:
        conn.execute("UPDATE notices SET is_published=? WHERE id=?", (int(published), notice_id))
        if conn.execute("SELECT changes()").fetchone()[0] == 0:
            raise SchoolError("Notice not found.")
        _audit(conn, actor_id, "published_notice" if published else "unpublished_notice", "notice", notice_id)


def dashboard_metrics(role: str, user_id: int) -> dict:
    with db_session() as conn:
        if role == "student":
            student = conn.execute("SELECT id FROM students WHERE user_id=?", (user_id,)).fetchone()
            if not student:
                return {"attendance_pct": None, "average_pct": None, "outstanding_cents": 0, "grades_count": 0, "attendance_count": 0}
            sid = student["id"]
            attendance = conn.execute("SELECT COUNT(*) AS total, SUM(CASE WHEN status IN ('Present','Late') THEN 1 ELSE 0 END) AS attended FROM attendance WHERE student_id=?", (sid,)).fetchone()
            grades = conn.execute("SELECT COUNT(*) AS n, AVG(g.marks / e.max_marks * 100.0) AS avg_pct FROM grades g JOIN exams e ON e.id=g.exam_id WHERE g.student_id=?", (sid,)).fetchone()
            fees = conn.execute("SELECT COALESCE(SUM(amount_cents),0) FROM fee_records WHERE student_id=? AND status='Unpaid'", (sid,)).fetchone()[0]
            total = attendance["total"] or 0
            return {"attendance_pct": round((attendance["attended"] or 0) * 100 / total, 1) if total else None,
                    "average_pct": round(grades["avg_pct"], 1) if grades["avg_pct"] is not None else None,
                    "outstanding_cents": int(fees), "grades_count": int(grades["n"] or 0), "attendance_count": int(total)}
        students = conn.execute("SELECT COUNT(*) FROM students WHERE status='Active'").fetchone()[0]
        teachers = conn.execute("SELECT COUNT(*) FROM teachers WHERE status='Active'").fetchone()[0]
        courses = conn.execute("SELECT COUNT(*) FROM courses WHERE status='Active'").fetchone()[0]
        today = date.today().isoformat()
        attendance = conn.execute("SELECT COUNT(*) FROM attendance WHERE attendance_date=?", (today,)).fetchone()[0]
        unpaid_cents = conn.execute("SELECT COALESCE(SUM(amount_cents),0) FROM fee_records WHERE status='Unpaid'").fetchone()[0]
        if role == "teacher":
            teacher = conn.execute("SELECT id FROM teachers WHERE user_id=?", (user_id,)).fetchone()
            if not teacher:
                return {"students": students, "teachers": teachers, "courses": courses, "attendance_today": attendance, "unpaid_cents": int(unpaid_cents)}
            assigned_classes = conn.execute("SELECT DISTINCT class_name FROM courses WHERE teacher_id=? AND status='Active'", (teacher["id"],)).fetchall()
            names = [r[0] for r in assigned_classes]
            if names:
                placeholders = ",".join("?" for _ in names)
                students = conn.execute(f"SELECT COUNT(*) FROM students WHERE status='Active' AND class_name IN ({placeholders})", names).fetchone()[0]
            else:
                students = 0
        return {"students": int(students), "teachers": int(teachers), "courses": int(courses), "attendance_today": int(attendance), "unpaid_cents": int(unpaid_cents)}


def get_student_attendance(student_id: int) -> list[dict]:
    return list_attendance(student_id=student_id)


def get_audit_logs(limit: int = 100) -> list[dict]:
    with db_session() as conn:
        return rows_to_dicts(conn.execute("""SELECT a.*, u.username FROM audit_logs a LEFT JOIN users u ON u.id=a.actor_user_id
            ORDER BY a.id DESC LIMIT ?""", (max(1, min(int(limit), 500)),)).fetchall())


def report_rows(report_name: str) -> list[dict]:
    with db_session() as conn:
        if report_name == "Students":
            return rows_to_dicts(conn.execute("SELECT admission_no, full_name, gender, date_of_birth, class_name, section, roll_no, guardian_name, guardian_phone, guardian_email, address, status, created_at FROM students ORDER BY class_name, section, roll_no").fetchall())
        if report_name == "Attendance":
            return rows_to_dicts(conn.execute("SELECT s.admission_no, s.full_name, s.class_name, s.section, a.attendance_date, a.status, a.notes FROM attendance a JOIN students s ON s.id=a.student_id ORDER BY a.attendance_date DESC, s.class_name, s.full_name").fetchall())
        if report_name == "Grades":
            return rows_to_dicts(conn.execute("SELECT s.admission_no, s.full_name, s.class_name, e.exam_name, e.subject, e.exam_date, g.marks, e.max_marks, ROUND(g.marks/e.max_marks*100,2) AS percentage FROM grades g JOIN students s ON s.id=g.student_id JOIN exams e ON e.id=g.exam_id ORDER BY e.exam_date DESC, s.full_name").fetchall())
        if report_name == "Fees":
            return rows_to_dicts(conn.execute("SELECT s.admission_no, s.full_name, s.class_name, f.fee_type, f.amount_cents/100.0 AS amount, f.due_date, f.status, f.paid_on, f.notes FROM fee_records f JOIN students s ON s.id=f.student_id ORDER BY f.due_date DESC").fetchall())
        raise SchoolError("Unknown report type.")
