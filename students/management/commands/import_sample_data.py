import csv
import io
import os
import secrets
import zipfile
from collections import Counter
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction
from django.db.utils import IntegrityError
from django.utils.dateparse import parse_date

from students.account_services import ensure_student_account
from students.credential_vault import record_initial_password
from students.forms import MarkForm
from students.models import (
    Attendance,
    Course,
    Department,
    Mark,
    Section,
    Semester,
    Student,
    Teacher,
)


REQUIRED_FILES = {
    "students.csv": {
        "student_id", "name", "email", "phone", "department", "course",
        "semester", "section",
    },
    "teachers.csv": {
        "teacher_id", "name", "email", "phone", "department", "courses",
    },
    "student_attendance.csv": {"student_id", "date", "status"},
    "student_marks.csv": {
        "student_id", "subject", "internal_marks", "assignment_marks",
        "practical_marks", "exam_marks",
    },
    "teacher_courses.csv": {"teacher_id", "course"},
}
TEACHER_ATTENDANCE_HEADERS = {"teacher_id", "date", "status"}
VALID_STATUSES = {choice[0] for choice in Attendance.STATUS_CHOICES}
ROLE_NAMES = {"Admin", "Teacher", "Student"}
User = get_user_model()


class SampleDataError(Exception):
    pass


def _clean_row(row):
    return {
        (key or "").strip().casefold(): (value or "").strip()
        for key, value in row.items()
        if key is not None
    }


def _read_csv_stream(stream, filename):
    try:
        reader = csv.DictReader(stream)
        headers = [
            (header or "").strip().casefold()
            for header in (reader.fieldnames or [])
        ]
        if not headers:
            raise CommandError(f"{filename}: CSV is empty or has no header row.")
        if len(headers) != len(set(headers)):
            raise CommandError(f"{filename}: duplicate column headers found.")
        rows = []
        for line_number, row in enumerate(reader, start=2):
            cleaned = _clean_row(row)
            if not any(cleaned.values()):
                continue
            cleaned["_line"] = str(line_number)
            rows.append(cleaned)
        return headers, rows
    except (csv.Error, UnicodeError) as exc:
        raise CommandError(f"{filename}: could not parse CSV: {exc}") from exc


def _load_csv(path, filename):
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return _read_csv_stream(stream, filename)
    except OSError as exc:
        raise CommandError(f"Could not read {filename}: {exc}") from exc


def _load_csv_bytes(data, filename):
    with io.TextIOWrapper(
        io.BytesIO(data), encoding="utf-8-sig", newline=""
    ) as stream:
        return _read_csv_stream(stream, filename)


def _safe_parse_date(value):
    try:
        return parse_date(value)
    except ValueError:
        return None


class Command(BaseCommand):
    help = "Safely import the fictional StudentMS sample data pack."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir",
            required=True,
            help="Directory containing the extracted sample CSV files.",
        )
        parser.add_argument(
            "--archive",
            help="Optional ZIP path used to find teacher_attendance.csv.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and run the import, then roll back all changes.",
        )
        parser.add_argument(
            "--demo-password-env",
            default="STUDENTMS_DEMO_PASSWORD",
            help="Environment variable for the temporary password of new demo accounts.",
        )

    def handle(self, *args, **options):
        source_dir = Path(options["data_dir"]).expanduser()
        if not source_dir.is_dir():
            raise CommandError(f"Sample data directory does not exist: {source_dir}")

        data = {}
        for filename, required_headers in REQUIRED_FILES.items():
            path = source_dir / filename
            if not path.is_file():
                raise CommandError(f"Required sample file is missing: {path}")
            headers, rows = _load_csv(path, filename)
            missing = sorted(required_headers - set(headers))
            if missing:
                raise CommandError(
                    f"{filename}: missing required column(s): {', '.join(missing)}"
                )
            data[filename] = rows

        teacher_attendance_rows, teacher_attendance_source = (
            self._load_teacher_attendance(source_dir, options.get("archive"))
        )
        if teacher_attendance_rows is not None:
            headers, rows = teacher_attendance_rows
            missing = sorted(TEACHER_ATTENDANCE_HEADERS - set(headers))
            if missing:
                raise CommandError(
                    "teacher_attendance.csv: missing required column(s): "
                    + ", ".join(missing)
                )
            data["teacher_attendance.csv"] = rows

        errors = self._validate_data(data)
        if errors:
            self.stdout.write(
                self.style.WARNING(
                    f"Validation summary: rejected {len(errors)} issue(s); "
                    "no database changes were made."
                )
            )
            for message in errors[:25]:
                self.stderr.write(f"  {message}")
            if len(errors) > 25:
                self.stderr.write(f"  ...and {len(errors) - 25} more issue(s).")
            raise CommandError("Sample data validation failed.")

        dry_run = options["dry_run"]
        password, generated_password = self._get_demo_password(
            options["demo_password_env"],
            dry_run=dry_run,
        )
        if not dry_run:
            self._validate_demo_password(password, data)

        try:
            with transaction.atomic():
                summary = self._import_rows(data, password)
                if dry_run:
                    transaction.set_rollback(True)
        except (SampleDataError, ValidationError, IntegrityError) as exc:
            raise CommandError(
                f"Import rolled back because existing data conflicts: {exc}"
            ) from exc

        teacher_attendance_count = len(data.get("teacher_attendance.csv", []))
        self._print_summary(
            summary,
            dry_run=dry_run,
            teacher_attendance_count=teacher_attendance_count,
            teacher_attendance_source=teacher_attendance_source,
            generated_password=(
                password if generated_password and summary["accounts_created"] else None
            ),
        )

    def _load_teacher_attendance(self, source_dir, archive_option):
        extracted = source_dir / "teacher_attendance.csv"
        if extracted.is_file():
            return _load_csv(extracted, "teacher_attendance.csv"), str(extracted)

        archive_path = (
            Path(archive_option).expanduser()
            if archive_option
            else source_dir.parent / f"{source_dir.name}.zip"
        )
        if not archive_path.is_file():
            return None, None
        try:
            with zipfile.ZipFile(archive_path) as archive:
                try:
                    content = archive.read("teacher_attendance.csv")
                except KeyError:
                    return None, str(archive_path)
            return _load_csv_bytes(content, "teacher_attendance.csv"), str(archive_path)
        except (OSError, zipfile.BadZipFile) as exc:
            raise CommandError(
                f"Could not read sample archive {archive_path}: {exc}"
            ) from exc

    def _validate_data(self, data):
        errors = []
        for filename in REQUIRED_FILES:
            if not data[filename]:
                errors.append(f"{filename}: file contains no data rows.")
        students = {}
        student_emails = set()
        for row in data["students.csv"]:
            line = row["_line"]
            student_id = row.get("student_id", "")
            email = row.get("email", "")
            required = (
                "student_id", "name", "email", "department", "course",
                "semester", "section",
            )
            missing = [field for field in required if not row.get(field)]
            if missing:
                errors.append(
                    f"students.csv:{line}: blank required value(s): "
                    f"{', '.join(missing)}"
                )
                continue
            if student_id in students:
                errors.append(
                    f"students.csv:{line}: duplicate student_id {student_id}."
                )
                continue
            try:
                validate_email(email)
            except ValidationError:
                errors.append(f"students.csv:{line}: invalid email {email!r}.")
                continue
            if email.casefold() in student_emails:
                errors.append(f"students.csv:{line}: duplicate email {email!r}.")
                continue
            try:
                semester_number = int(row["semester"])
                if semester_number < 1:
                    raise ValueError
            except ValueError:
                errors.append(
                    f"students.csv:{line}: semester must be a positive integer."
                )
                continue
            if len(row["name"]) > 100 or len(row.get("phone", "")) > 15:
                errors.append(f"students.csv:{line}: name or phone exceeds model limits.")
                continue
            if len(row["department"]) > 100 or len(row["course"]) > 100:
                errors.append(
                    f"students.csv:{line}: department or course exceeds model limits."
                )
                continue
            if len(row["section"]) > 10:
                errors.append(f"students.csv:{line}: section exceeds 10 characters.")
                continue
            row["_semester_number"] = semester_number
            students[student_id] = row
            student_emails.add(email.casefold())

        teachers = {}
        teacher_emails = set()
        for row in data["teachers.csv"]:
            line = row["_line"]
            teacher_id = row.get("teacher_id", "")
            required = ("teacher_id", "name", "email", "department")
            missing = [field for field in required if not row.get(field)]
            if missing:
                errors.append(
                    f"teachers.csv:{line}: blank required value(s): "
                    f"{', '.join(missing)}"
                )
                continue
            if teacher_id in teachers:
                errors.append(
                    f"teachers.csv:{line}: duplicate teacher_id {teacher_id}."
                )
                continue
            try:
                validate_email(row["email"])
            except ValidationError:
                errors.append(f"teachers.csv:{line}: invalid email {row['email']!r}.")
                continue
            if row["email"].casefold() in teacher_emails:
                errors.append(
                    f"teachers.csv:{line}: duplicate email {row['email']!r}."
                )
                continue
            if (
                len(row["name"]) > 100
                or len(row.get("phone", "")) > 15
                or len(row["department"]) > 100
            ):
                errors.append(f"teachers.csv:{line}: value exceeds a model field limit.")
                continue
            row["_courses"] = [
                course.strip()
                for course in row.get("courses", "").split(";")
                if course.strip()
            ]
            teachers[teacher_id] = row
            teacher_emails.add(row["email"].casefold())

        assignments = set()
        for row in data["teacher_courses.csv"]:
            line = row["_line"]
            teacher_id = row.get("teacher_id", "")
            course = row.get("course", "")
            if not teacher_id or not course:
                errors.append(
                    f"teacher_courses.csv:{line}: teacher_id and course are required."
                )
                continue
            if teacher_id not in teachers:
                errors.append(
                    f"teacher_courses.csv:{line}: unknown teacher_id {teacher_id!r}."
                )
                continue
            key = (teacher_id, course.casefold())
            if key in assignments:
                errors.append(
                    f"teacher_courses.csv:{line}: duplicate assignment for "
                    f"{teacher_id} / {course}."
                )
                continue
            declared = {
                item.casefold() for item in teachers[teacher_id]["_courses"]
            }
            if course.casefold() not in declared:
                errors.append(
                    f"teacher_courses.csv:{line}: course is absent from the "
                    "teacher's courses column."
                )
                continue
            assignments.add(key)
            row["_course"] = course

        declared_assignments = {
            (teacher_id, course.casefold())
            for teacher_id, teacher in teachers.items()
            for course in teacher["_courses"]
        }
        if declared_assignments != assignments:
            errors.append(
                "teachers.csv and teacher_courses.csv contain inconsistent "
                "course assignment lists."
            )
        overlapping_emails = student_emails & teacher_emails
        for email in sorted(overlapping_emails):
            errors.append(
                f"students.csv and teachers.csv both use email {email!r}."
            )

        for filename in ("student_attendance.csv", "student_marks.csv"):
            seen = set()
            for row in data[filename]:
                line = row["_line"]
                student_id = row.get("student_id", "")
                if student_id not in students:
                    errors.append(
                        f"{filename}:{line}: unknown student_id {student_id!r}."
                    )
                    continue
                if filename == "student_attendance.csv":
                    key = (student_id, row.get("date", ""))
                    if not _safe_parse_date(row.get("date", "")):
                        errors.append(
                            f"{filename}:{line}: date must use YYYY-MM-DD format."
                        )
                    if row.get("status") not in VALID_STATUSES:
                        errors.append(
                            f"{filename}:{line}: status must be Present or Absent."
                        )
                else:
                    subject = row.get("subject", "")
                    key = (student_id, subject.casefold())
                    if not subject or len(subject) > 100:
                        errors.append(
                            f"{filename}:{line}: subject is required and must be "
                            "at most 100 characters."
                        )
                    components = {}
                    for field, maximum in MarkForm.component_maxima.items():
                        try:
                            value = int(row.get(field, ""))
                        except ValueError:
                            errors.append(
                                f"{filename}:{line}: {field} must be an integer."
                            )
                            continue
                        if value < 0 or value > maximum:
                            errors.append(
                                f"{filename}:{line}: {field} must be between "
                                f"0 and {maximum}."
                            )
                        components[field] = value
                    if len(components) == len(MarkForm.component_maxima):
                        if sum(components.values()) != 100:
                            errors.append(
                                f"{filename}:{line}: assessment components must total 100."
                            )
                if key in seen:
                    errors.append(
                        f"{filename}:{line}: duplicate record key {key!r}."
                    )
                seen.add(key)

        for row in data.get("teacher_attendance.csv", []):
            line = row["_line"]
            if row.get("teacher_id") not in teachers:
                errors.append(
                    f"teacher_attendance.csv:{line}: unknown teacher_id "
                    f"{row.get('teacher_id')!r}."
                )
            if not _safe_parse_date(row.get("date", "")):
                errors.append(
                    f"teacher_attendance.csv:{line}: date must use YYYY-MM-DD."
                )
            if row.get("status") not in VALID_STATUSES:
                errors.append(
                    f"teacher_attendance.csv:{line}: status must be Present or Absent."
                )
        return errors

    def _get_demo_password(self, env_name, dry_run):
        if dry_run:
            return secrets.token_urlsafe(24), False
        password = os.environ.get(env_name, "")
        if password:
            return password, False
        return secrets.token_urlsafe(24), True

    def _validate_demo_password(self, password, data):
        first_student = data["students.csv"][0]
        username = first_student["student_id"]
        candidate = User(username=username, email=first_student["email"])
        try:
            validate_password(password, user=candidate)
        except ValidationError as exc:
            raise CommandError(
                "The demo password does not meet configured password rules: "
                + "; ".join(exc.messages)
            ) from exc

    def _get_single(self, queryset, description):
        matches = list(queryset[:2])
        if len(matches) > 1:
            raise SampleDataError(f"Multiple existing records match {description}.")
        return matches[0] if matches else None

    def _get_group(self, role):
        group = self._get_single(
            Group.objects.filter(name__iexact=role),
            f"role group {role}",
        )
        if group:
            return group
        return Group.objects.create(name=role)

    def _get_department(self, name, summary):
        department = self._get_single(
            Department.objects.filter(name__iexact=name),
            f"department {name!r}",
        )
        if department:
            summary["departments"]["skipped"] += 1
            return department
        department = Department.objects.create(name=name)
        summary["departments"]["created"] += 1
        return department

    def _get_course(self, name, department, summary):
        course = self._get_single(
            Course.objects.filter(name__iexact=name, department=department),
            f"course {name!r} in {department.name!r}",
        )
        if course:
            summary["courses"]["skipped"] += 1
            return course
        course = Course.objects.create(name=name, department=department)
        summary["courses"]["created"] += 1
        return course

    def _get_semester(self, number, summary):
        semester = self._get_single(
            Semester.objects.filter(number=number),
            f"semester number {number}",
        )
        if semester:
            summary["semesters"]["skipped"] += 1
            return semester
        name = f"Semester {number}"
        if Semester.objects.filter(name__iexact=name).exists():
            raise SampleDataError(
                f"Semester name {name!r} is already used by a different number."
            )
        semester = Semester.objects.create(name=name, number=number)
        summary["semesters"]["created"] += 1
        return semester

    def _get_section(self, name, semester, summary):
        section = self._get_single(
            Section.objects.filter(name__iexact=name, semester=semester),
            f"section {name!r} in {semester.name!r}",
        )
        if section:
            summary["sections"]["skipped"] += 1
            return section
        section = Section.objects.create(name=name, semester=semester)
        summary["sections"]["created"] += 1
        return section

    def _get_demo_user(self, row, role, password, role_group, summary):
        id_field = "student_id" if role == "Student" else "teacher_id"
        username = (
            row[id_field]
            if role == "Student"
            else f"demo_{row[id_field].casefold()}"
        )
        email = row["email"]
        by_username = self._get_single(
            User._default_manager.filter(username__iexact=username),
            f"username {username!r}",
        )
        by_email = self._get_single(
            User._default_manager.filter(email__iexact=email),
            f"email {email!r}",
        )
        if by_username or by_email:
            if role == "Student" and by_username is None and by_email is not None:
                existing_student = self._get_single(
                    Student.objects.filter(
                        user=by_email,
                        email__iexact=email,
                        student_id__iexact=row[id_field],
                    ),
                    f"linked student profile for {email!r}",
                )
                if existing_student is not None:
                    ensure_student_account(existing_student)
                    summary["student_accounts"]["skipped"] += 1
                    return by_email
            if (
                by_username is None
                or by_email is None
                or by_username.pk != by_email.pk
                or by_username.username.casefold() != username.casefold()
                or by_username.email.casefold() != email.casefold()
            ):
                raise SampleDataError(
                    f"Account identity conflict for demo {role.lower()} "
                    f"{row[id_field]} ({email}). Existing account was not changed."
                )
            user = by_username
            memberships = {
                group.name.casefold()
                for group in user.groups.all()
                if group.name.casefold() in {name.casefold() for name in ROLE_NAMES}
            }
            if (
                user.is_superuser
                or user.is_staff
                or role.casefold() not in memberships
                or memberships != {role.casefold()}
            ):
                raise SampleDataError(
                    f"Role conflict for existing account {username!r}; expected "
                    f"only the {role} role. Existing account was not changed."
                )
            summary[f"{role.lower()}_accounts"]["skipped"] += 1
            return user

        if role == "Student":
            password = row["student_id"]
        user = User._default_manager.create_user(
            username=username,
            email=email,
            password=password,
        )
        user.groups.add(role_group)
        record_initial_password(
            user,
            role,
            row["student_id"] if role == "Student" else password,
        )
        if role == "Student":
            user._studentms_default_password = True
        summary[f"{role.lower()}_accounts"]["created"] += 1
        summary["accounts_created"] += 1
        return user

    def _import_rows(self, data, password):
        names = (
            "departments", "courses", "semesters", "sections",
            "student_accounts", "teacher_accounts", "students", "teachers",
            "course_assignments", "student_attendance", "marks",
        )
        summary = {name: Counter() for name in names}
        summary["accounts_created"] = 0
        groups = {
            role: self._get_group(role)
            for role in ("Student", "Teacher")
        }

        departments = {}
        courses = {}
        for row in data["teachers.csv"]:
            department_key = row["department"].casefold()
            department = departments.get(department_key)
            if department is None:
                department = self._get_department(row["department"], summary)
                departments[department_key] = department
            for course_name in row["_courses"]:
                key = (department_key, course_name.casefold())
                if key not in courses:
                    courses[key] = self._get_course(
                        course_name, department, summary
                    )
        for row in data["students.csv"]:
            department_key = row["department"].casefold()
            department = departments.get(department_key)
            if department is None:
                department = self._get_department(row["department"], summary)
                departments[department_key] = department
            key = (department_key, row["course"].casefold())
            if key not in courses:
                courses[key] = self._get_course(row["course"], department, summary)

        semesters = {}
        sections = {}
        for row in data["students.csv"]:
            number = row["_semester_number"]
            semester = semesters.get(number)
            if semester is None:
                semester = self._get_semester(number, summary)
                semesters[number] = semester
            key = (number, row["section"].casefold())
            if key not in sections:
                sections[key] = self._get_section(
                    row["section"], semester, summary
                )

        students_by_id = {}
        for row in data["students.csv"]:
            user = self._get_demo_user(
                row, "Student", password, groups["Student"], summary
            )
            semester = semesters[row["_semester_number"]]
            section = sections[(row["_semester_number"], row["section"].casefold())]
            student = self._get_single(
                Student.objects.filter(email__iexact=row["email"]),
                f"student email {row['email']!r}",
            )
            if student is None:
                student = Student(
                    student_id=row["student_id"],
                    must_change_password=bool(
                        getattr(user, "_studentms_default_password", False)
                    ),
                    user=user,
                    name=row["name"],
                    email=row["email"],
                    phone=row.get("phone", ""),
                    department=row["department"],
                    course=row["course"],
                    semester=semester,
                    section=section,
                )
                student.full_clean()
                student.save()
                summary["students"]["created"] += 1
            else:
                expected = {
                    "student_id": row["student_id"],
                    "name": row["name"],
                    "email": row["email"],
                    "phone": row.get("phone", ""),
                    "department": row["department"],
                    "course": row["course"],
                }
                changed = False
                for field, value in expected.items():
                    current_value = getattr(student, field)
                    if (
                        current_value is not None
                        and current_value.casefold() != value.casefold()
                    ):
                        raise SampleDataError(
                            f"Existing student {row['email']} has a conflicting "
                            f"{field}; profile data was not overwritten."
                        )
                if student.user_id not in (None, user.pk):
                    raise SampleDataError(
                        f"Student {row['email']} is already linked to another account."
                    )
                if student.semester_id not in (None, semester.pk):
                    raise SampleDataError(
                        f"Student {row['email']} has a conflicting semester."
                    )
                if student.section_id not in (None, section.pk):
                    raise SampleDataError(
                        f"Student {row['email']} has a conflicting section."
                    )
                if student.user_id is None:
                    student.user = user
                    changed = True
                if not student.student_id:
                    student.student_id = row["student_id"]
                    changed = True
                if student.semester_id is None:
                    student.semester = semester
                    changed = True
                if student.section_id is None:
                    student.section = section
                    changed = True
                if changed:
                    student.full_clean()
                    student.save()
                    summary["students"]["updated"] += 1
                else:
                    summary["students"]["skipped"] += 1
            students_by_id[row["student_id"]] = student

        teachers_by_id = {}
        for row in data["teachers.csv"]:
            user = self._get_demo_user(
                row, "Teacher", password, groups["Teacher"], summary
            )
            department = departments[row["department"].casefold()]
            teacher = self._get_single(
                Teacher.objects.filter(email__iexact=row["email"]),
                f"teacher email {row['email']!r}",
            )
            if teacher is None:
                teacher = Teacher(
                    user=user,
                    name=row["name"],
                    email=row["email"],
                    phone=row.get("phone", ""),
                    department=department,
                )
                teacher.full_clean()
                teacher.save()
                summary["teachers"]["created"] += 1
            else:
                if teacher.user_id != user.pk:
                    raise SampleDataError(
                        f"Teacher {row['email']} is linked to a different account."
                    )
                for field in ("name", "email", "phone"):
                    if getattr(teacher, field).casefold() != row.get(field, "").casefold():
                        raise SampleDataError(
                            f"Existing teacher {row['email']} has a conflicting "
                            f"{field}; profile data was not overwritten."
                        )
                if teacher.department_id not in (None, department.pk):
                    raise SampleDataError(
                        f"Teacher {row['email']} has a conflicting department."
                    )
                if teacher.department_id is None:
                    teacher.department = department
                    teacher.save(update_fields=["department"])
                    summary["teachers"]["updated"] += 1
                else:
                    summary["teachers"]["skipped"] += 1
            teachers_by_id[row["teacher_id"]] = teacher

        for row in data["teacher_courses.csv"]:
            teacher = teachers_by_id[row["teacher_id"]]
            course = courses[
                (teacher.department.name.casefold(), row["_course"].casefold())
            ]
            if teacher.courses.filter(pk=course.pk).exists():
                summary["course_assignments"]["skipped"] += 1
            else:
                teacher.courses.add(course)
                summary["course_assignments"]["created"] += 1

        for row in data["student_attendance.csv"]:
            student = students_by_id[row["student_id"]]
            day = _safe_parse_date(row["date"])
            attendance, created = Attendance.objects.get_or_create(
                student=student,
                date=day,
                defaults={"status": row["status"]},
            )
            if created:
                summary["student_attendance"]["created"] += 1
            elif attendance.status == row["status"]:
                summary["student_attendance"]["skipped"] += 1
            else:
                raise SampleDataError(
                    f"Attendance conflict for {student.email} on {day}: existing "
                    f"{attendance.status}, sample {row['status']}. Existing data "
                    "was not overwritten."
                )

        for row in data["student_marks.csv"]:
            student = students_by_id[row["student_id"]]
            scores = {
                field: int(row[field])
                for field in MarkForm.component_maxima
            }
            matches = list(
                Mark.objects.filter(
                    student=student,
                    subject__iexact=row["subject"],
                )[:2]
            )
            if len(matches) > 1:
                raise SampleDataError(
                    f"Multiple existing mark records match {student.email} / "
                    f"{row['subject']}."
                )
            if matches:
                mark = matches[0]
                if any(getattr(mark, field) != value for field, value in scores.items()):
                    raise SampleDataError(
                        f"Marks conflict for {student.email} / {row['subject']}; "
                        "existing scores were not overwritten."
                    )
                summary["marks"]["skipped"] += 1
            else:
                mark = Mark(
                    student=student,
                    subject=row["subject"],
                    **scores,
                )
                mark.full_clean()
                mark.save()
                summary["marks"]["created"] += 1
        return summary

    def _print_summary(
        self,
        summary,
        *,
        dry_run,
        teacher_attendance_count,
        teacher_attendance_source,
        generated_password,
    ):
        heading = "DRY RUN (rolled back)" if dry_run else "IMPORT COMPLETE"
        self.stdout.write(self.style.SUCCESS(f"\nSample data summary — {heading}"))
        labels = (
            ("departments", "Departments"),
            ("courses", "Courses"),
            ("semesters", "Semesters"),
            ("sections", "Sections"),
            ("student_accounts", "Student accounts"),
            ("teacher_accounts", "Teacher accounts"),
            ("students", "Student profiles"),
            ("teachers", "Teacher profiles"),
            ("course_assignments", "Teacher-course assignments"),
            ("student_attendance", "Student attendance"),
            ("marks", "Student marks"),
        )
        for key, label in labels:
            counts = summary[key]
            self.stdout.write(
                f"  {label}: created {counts['created']}, "
                f"updated {counts['updated']}, skipped {counts['skipped']}, "
                "rejected 0"
            )
        self.stdout.write(
            "  Teacher attendance: "
            f"not imported, {teacher_attendance_count} row(s) skipped; "
            "no TeacherAttendance model exists."
        )
        if teacher_attendance_source:
            self.stdout.write(f"    Source checked: {teacher_attendance_source}")
        elif teacher_attendance_count == 0:
            self.stdout.write(
                "    teacher_attendance.csv was not found in the extracted folder "
                "or sibling archive."
            )
        self.stdout.write(
            "  Not stored by current Student fields: date_of_birth, gender, "
            "year, and address."
        )
        if dry_run:
            self.stdout.write("No records were committed.")
        elif generated_password:
            self.stdout.write(
                self.style.WARNING(
                    "\nOne-time temporary password for newly created teacher "
                    f"demo accounts: {generated_password}"
                )
            )
            self.stdout.write(
                "Student usernames and initial passwords use each Student ID. "
                "Teacher usernames use demo_<source-id> (for example, "
                "demo_tch001). Store the teacher password securely; it is not "
                "shown again."
            )