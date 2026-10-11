# StudentMS

StudentMS is an existing Django application for managing student records and
college academic activity. It uses Django authentication, SQLite by default,
server-rendered templates, and a shared navy-blue responsive navigation layout.

## Current features

- Role-aware dashboards and protected routes for Admin, Teacher, and Student
  accounts.
- The login page's **Staff** choice accepts Admin accounts and Teacher
  accounts; it routes each to its own dashboard. The explicit **Teacher**
  choice accepts only Teacher-group accounts.
- Student listing, Student ID search, filters, adjustable pagination,
  complete CSV export, details, and admin create/edit.
- Student ID-based login account generation, Student role assignment, and a
  forced password-change flow for new accounts using their default Student ID
  password.
- Department, course, semester, and section administration.
- Attendance records with per-student/date uniqueness and date-based updates.
- Marks with a 100-point total, grades, and results. The sample pack uses
  component input maxima 20 + 20 + 20 + 70; existing grade and pass thresholds
  are unchanged.
- Teacher-scoped student, attendance, marks, and report views based on assigned
  courses.
- Student-only profile, attendance, and results pages for the linked student.
- Reports and live dashboard statistics from the database.
- Django Admin integration for accounts with the required Django permissions.

The Student model includes a unique Student ID field. Existing sample-imported
records are backfilled from exact email matches to the sample CSV by an
additive migration. Existing linked users are renamed to their Student IDs by
the account command without resetting passwords. Student gender, year, and
created date are not fields on this model and are not displayed.

Existing student department/course values are text fields. Teacher course
authorization therefore matches those values against assigned `Course.name`
records. Keep these names consistent when updating academic records.

## Technology

- Python 3.14 (or a supported Python version for the selected Django release)
- Django 6.1
- SQLite by default
- HTML, CSS, and JavaScript; no frontend framework is required

## Setup on Windows

Run commands from the project directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell prevents local activation, invoke the environment executable
directly instead, for example `.\venv\Scripts\python.exe manage.py check`.
After activation, use `python` (or the explicit virtual-environment executable)
for project commands. Do not use `py manage.py ...`: the Windows `py` launcher
can select a global Python interpreter instead of the active virtual
environment, which may not have the project's dependencies installed.

For Windows Command Prompt with the existing `venv` folder:

```bat
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe manage.py check
venv\Scripts\python.exe manage.py runserver
```

### Configuration

Development defaults use SQLite at `db.sqlite3`, local allowed hosts, and
`DEBUG=True`. Configure deployment settings through environment variables:

```powershell
$env:DJANGO_SECRET_KEY = "replace-with-a-long-random-secret"
$env:DJANGO_DEBUG = "false"
$env:DJANGO_ALLOWED_HOSTS = "studentms.example.edu"
```

`DJANGO_SECRET_KEY` is required when debug mode is disabled. Do not commit
production secrets or `.env` files. Production deployment should use HTTPS,
restrict `DJANGO_ALLOWED_HOSTS`, configure backups, and use a production-grade
database for multi-worker deployments.

### Database and initial administrator

The database and migration history are preserved in the existing checkout.
Apply pending migrations when setting up a fresh database or after reviewing
the migration files:

```powershell
python manage.py migrate
python manage.py createsuperuser
```

A Django superuser is treated as an Admin by StudentMS. Regular accounts and
their roles can be created from **Manage Users** by an authorized Admin. A
Student account must be linked to an existing student record; Teacher accounts
are created with a department and assigned courses.

### Run

```powershell
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. The local SQLite database and backup are ignored
by Git to avoid accidentally publishing personal records.

## Validation

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

## Import the fictional sample data pack

The importer uses the existing StudentMS models and groups, preserves
conflicting profile and attendance data, and is safe to rerun. It imports
student/teacher accounts, student profiles, departments, courses, semesters,
sections, teacher-course assignments, student attendance, and marks. It does
not import teacher attendance: the current schema has no teacher-attendance
model. The source data also contains date of birth, gender, year, and address columns
that the current `Student` model cannot store; the command reports those
columns rather than discarding them silently.

The marks pack has 300 records, all totaling 100, but its component values do
not fit the former per-field limits. The mark form now accepts the pack's
observed component ranges while rejecting totals above 100. Total, percentage,
grade cutoffs, and pass/fail rules remain unchanged.

Student sample accounts use the Student ID as the username and initial
password. Newly created student accounts are active, receive only the Student
group, and must change that temporary password before accessing the portal.
Teacher sample accounts continue to use `demo_<teacher-id>` usernames and a
separate generated temporary password. Existing account passwords are never
reset by the sample importer or account-generation command.

### Create student accounts and sign in (Windows CMD)

The live database was backed up before this feature was applied. For a future
deployment, take a verified database backup before running the additive
migration:

```bat
cd /d "C:\Users\gokulbharathi\Downloads\Project\project-2\StudentManagementSystem"
venv\Scripts\python.exe manage.py check
venv\Scripts\python.exe manage.py migrate
venv\Scripts\python.exe manage.py create_student_accounts
venv\Scripts\python.exe manage.py test students
```

The account command processes every profile, prints per-record progress, and
reports created, updated, unchanged, and conflicting accounts. It does not
reset an existing password or attach an account whose ID, email, or role cannot
be verified. Student profiles created through the application or Django Admin
with a Student ID also receive an account automatically.

For a newly created account whose password is still the default, sign in at
`/login/`, choose the **Student** role, and enter the Student ID for both
username and initial password (for example, `STU0001` / `STU0001`). The student
portal then requires a password change. Existing linked accounts keep their
password; continue using the account's existing password.

Admins can browse all student records at `/students/`. Search and filters also
apply to the CSV export. **Export complete list to CSV** exports all matching
records regardless of pagination; no passwords are included. **Generate
missing accounts** is an admin-only POST action.

### Private student and teacher credentials report (Windows CMD)

The Django Admin credentials page at
`http://127.0.0.1:8000/admin/studentms-credentials/` processes missing student
and teacher accounts and downloads the complete
`student_teacher_login_credentials.csv`. Access requires an active Django
staff account with the `students | initial login credential | Can generate
and download student/teacher login credentials` permission; superusers have
this permission automatically. StudentMS Admin-group membership alone does
not grant access. Assign the permission through Django Admin to a trusted
staff account. The page and download reject other users and disable response
caching.

The report never derives passwords from Django hashes. Passwords for older
accounts are `Changed or unknown`. For accounts created while the encryption
key is configured, the report can show the temporary password only while it
still matches the current password hash; changing the account password
invalidates the stored report credential. The encryption key is independent
from `DJANGO_SECRET_KEY` and must remain available for future reports. If it is
not configured when an account is created, account creation still works, but
the initial password will not be recoverable through the report. No existing
password is reset by account generation.

The Teacher model has no Teacher ID. Newly created teacher accounts use
`teacher_<normalized-email-prefix>_<10-character-email-hash>` as both username
and initial password. Existing teacher usernames and passwords are preserved.
Student accounts use Student ID for both values. Only matching Student or
Teacher groups are assigned; conflicts are listed for manual review.

Before applying the additive credentials-ledger migration to a live database,
make and verify a copy of `db.sqlite3`. Then from CMD, configure a Fernet key
once for the current and future terminals (store it in a protected location;
do not commit it or share it):

```bat
cd /d "C:\Users\gokulbharathi\Downloads\Project\project-2\StudentManagementSystem"
for /f %K in ('venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"') do set "STUDENTMS_CREDENTIAL_ENCRYPTION_KEY=%K"
setx STUDENTMS_CREDENTIAL_ENCRYPTION_KEY "%STUDENTMS_CREDENTIAL_ENCRYPTION_KEY%"
```

Keep the current CMD window open: `setx` persists the variable for future
windows but does not update the current one. In each later CMD window, reopen
the project directory and set the variable from your protected secret store
before running account generation or the server. Never generate a replacement
key after credentials have been stored, or those encrypted passwords can no
longer be decrypted.

Back up the database, check and apply migrations, run the targeted tests, then
process accounts:

```bat
copy /b "db.sqlite3" "db_backup_before_credentials_report.sqlite3"
certutil -hashfile "db.sqlite3" SHA256
certutil -hashfile "db_backup_before_credentials_report.sqlite3" SHA256
venv\Scripts\python.exe manage.py check
venv\Scripts\python.exe manage.py makemigrations --check --dry-run
venv\Scripts\python.exe manage.py test students
venv\Scripts\python.exe manage.py migrate
venv\Scripts\python.exe manage.py create_student_teacher_accounts
venv\Scripts\python.exe manage.py runserver
```

The account command does not print passwords. It reports totals, creations,
existing accounts, and conflicts; download the private CSV from the Admin page
to see any still-valid recorded initial credentials. Verify the backup hashes
match before proceeding with a live migration.

To generate the six-column `all_login_credentials.csv` beside `manage.py`,
process any missing accounts, and leave unknown initial passwords blank, run:

```bat
venv\Scripts\python.exe manage.py generate_all_login_credentials
```

This CSV contains private credential information. Store it securely and do
not publish or share it. Existing account passwords are never reset or inferred.

To inspect account links, active status, usable-password-hash status, exact
role-group membership, and CSV username matches without changing data or
printing passwords, run:

```bat
venv\Scripts\python.exe manage.py diagnose_login_accounts
```

Legacy account passwords cannot be recovered from their hashes. If an
administrator decides to reset eligible role-account passwords, the separate
command below requires the exact confirmation token, creates a SQLite backup
before changes, and requires `STUDENTMS_CREDENTIAL_ENCRYPTION_KEY` so the new
temporary credentials are encrypted for the protected report. Student
passwords become their Student IDs and their next portal access requires a
password change. Teachers keep their existing usernames; without a Teacher ID,
the temporary password follows the documented email-derived username rule.
Only linked, active, non-staff accounts with the exact matching role group and
no conflicting role are eligible. Ineligible accounts are skipped for review.
Do not run this reset command unless you intentionally want to replace those
passwords:

```bat
venv\Scripts\python.exe manage.py reset_student_teacher_passwords --confirm RESET-STUDENT-TEACHER-PASSWORDS
```

The following commands are for **Windows Command Prompt (CMD)**. Begin in the
project root and make a uniquely named, verified copy of the live database:

```bat
cd /d "C:\Users\gokulbharathi\Downloads\Project\project-2\StudentManagementSystem"
for /f %i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%i"
copy /b "db.sqlite3" "db_backup_before_sample_import_%STAMP%.sqlite3"
certutil -hashfile "db.sqlite3" SHA256
certutil -hashfile "db_backup_before_sample_import_%STAMP%.sqlite3" SHA256
```

First run the real dataset against a disposable copy of that backup. The
`DJANGO_DB_NAME` override directs Django to the validation copy rather than
the live database:

```bat
copy /b "db_backup_before_sample_import_%STAMP%.sqlite3" "db_sample_import_validation.sqlite3"
set "DJANGO_DB_NAME=%CD%\db_sample_import_validation.sqlite3"
venv\Scripts\python.exe manage.py check
venv\Scripts\python.exe manage.py import_sample_data --data-dir "C:\Users\gokulbharathi\Downloads\StudentMS_complete_sample_data_pack" --dry-run
venv\Scripts\python.exe manage.py import_sample_data --data-dir "C:\Users\gokulbharathi\Downloads\StudentMS_complete_sample_data_pack"
venv\Scripts\python.exe manage.py shell -c "from django.contrib.auth import get_user_model; from students.models import Student,Teacher,Department,Course,Semester,Section,Attendance,Mark; U=get_user_model(); print({'students':Student.objects.count(),'student_ids':Student.objects.exclude(student_id__isnull=True).count(),'teachers':Teacher.objects.count(),'departments':Department.objects.count(),'courses':Course.objects.count(),'semesters':Semester.objects.count(),'sections':Section.objects.count(),'student_attendance':Attendance.objects.count(),'marks':Mark.objects.count(),'student_accounts':U.objects.filter(groups__name='Student').distinct().count(),'demo_teachers':U.objects.filter(username__startswith='demo_tch').count()})"
set "DJANGO_DB_NAME="
```

Review the summary and login checks on the validation copy before importing to
the live database. To populate the live database, run the import command again
after clearing `DJANGO_DB_NAME` (while still in the project root):

```bat
venv\Scripts\python.exe manage.py import_sample_data --data-dir "C:\Users\gokulbharathi\Downloads\StudentMS_complete_sample_data_pack"
```

The one-time temporary password is printed only for newly created teacher
accounts; student accounts use their Student IDs as initial passwords. On a
later idempotent run, reused account passwords are not reset or shown. Demo
student and teacher accounts use the `Student` and `Teacher` groups,
respectively. The existing administrator account is not changed.
Teacher-attendance rows are validated and reported as not imported until a
separate teacher-attendance schema change is explicitly approved.

## Deployment checklist

- Set `DJANGO_DEBUG=false`, a unique `DJANGO_SECRET_KEY`, and production
  `DJANGO_ALLOWED_HOSTS`.
- Serve the site over HTTPS and configure the reverse proxy and security
  headers appropriately.
- Run migrations during a controlled release and back up the database first.
- Configure static-file collection/serving and a production database.
- Create least-privilege Django permissions for accounts that need Django Admin.
- Monitor application errors and test role-specific access after deployment.
