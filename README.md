# School Management System

A Streamlit + SQLite school administration app. The project is inspired by the uploaded school dashboard reference, but it is an original implementation.

## Included modules

- First-run administrator setup (there is no default username or password)
- Administrator-managed student records and student login accounts
- Teacher records and teacher login accounts
- Course setup and teacher assignments
- Class/date-based attendance with CSV export
- Exam creation, gradebook entry, marks validation, and student grade view
- Fee records, payment status, waived fees, and CSV export
- Notice board with Everyone / Students / Teachers audiences
- Role-specific pages for administrators, teachers, and students
- Password hashing, forced password change after an administrator reset, account deactivation, and basic audit logs
- CSV reports for students, attendance, grades, and fees

## No demo data

The app creates database tables only. It **does not seed demo students, demo teachers, sample courses, or test grades**. When opened for the first time, it asks you to create your own administrator account. After signing in, the administrator enters the school's real records.

## Requirements

- Python 3.10 or newer
- Internet connection on first use if Python packages are not already installed

## Run on macOS

1. Extract the ZIP file.
2. Open Terminal and move into the extracted folder:

   ```bash
   cd school_management_system
   ```

3. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. Install packages:

   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

5. Start the application:

   ```bash
   streamlit run app.py
   ```

Streamlit prints a local address (usually `http://localhost:8501`). Open it in your browser.

## Windows

```powershell
cd school_management_system
py -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

## First login and student accounts

1. On first run, create the administrator account on the setup screen.
2. Open **Students → Add student**.
3. Enter the student's school details, a unique username, and an initial password. The student record and login account are created together.
4. Give the credentials to the student using your school's secure process. The app never displays or stores a readable copy of the password.
5. Students sign in on the same login screen and can see their own profile, attendance, grades, fee records, and published notices.
6. Students and teachers can change their password under **Account & Security**. If an admin resets a password, the user must change it at the next sign-in.

## Suggested setup order

1. Add teacher accounts.
2. Add student accounts and enter class names consistently (for example, use `9` for every student in Class 9).
3. Add courses, using the same class name and assigning each course to its teacher. Teacher permissions are based on those assignments.
4. Mark attendance and create exams/grades.
5. Add fee records and publish notices.

## Database and backups

By default, data is stored in `data/school.db`, created the first time the app starts. The folder is excluded from version control by `.gitignore`. Back up the database by stopping the app and copying the `data` folder to a protected location. Treat the database and CSV exports as confidential student information.

To put the database somewhere else, set `SCHOOL_DB_PATH` before starting Streamlit:

```bash
export SCHOOL_DB_PATH="$HOME/school-private/school.db"
streamlit run app.py
```

## Important limitations before real-world deployment

This is a functional local prototype, not a security-certified production SIS. Before storing sensitive data for a real school or hosting it on the public internet, have a qualified developer review deployment security, HTTPS, session controls, backup recovery, access policies, audit retention, data-protection requirements, and load handling. SQLite is convenient for a single-machine prototype; a multi-user school-wide deployment serving thousands of concurrent users should move to a managed PostgreSQL database and a production hosting architecture. Avoid exposing this Streamlit development server directly to the public internet.

## Troubleshooting

- If `streamlit: command not found`, activate `.venv` and run `python -m pip install -r requirements.txt`.
- If the page shows no student records, that is expected until the administrator adds them.
- If teacher attendance/classes are unavailable, an administrator must assign the teacher to an active course. Course class names must match the class names on student records.
- If a username is taken, choose a different username. Usernames are case-insensitive.
- If a password is forgotten, the administrator can assign a temporary password from the student or teacher management page.
