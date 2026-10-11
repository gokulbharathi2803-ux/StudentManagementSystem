import csv
import io

from django.http import HttpResponse

from students.credential_vault import get_current_initial_password
from students.models import Student, Teacher


CSV_HEADERS = (
    "Role",
    "Student ID or Teacher ID",
    "Full name",
    "Username",
    "Email",
    "Department",
    "Course assignments",
    "Account status",
    "Initial password status",
    "Initial password",
    "Notes",
)


def _csv_safe(value):
    value = "" if value is None else str(value)
    if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _row(role, identifier, name, user, email, department, courses, notes):
    if user is None:
        account_status = "Missing"
        initial_password_status = "Changed or unknown"
        initial_password = ""
        notes = notes or "Missing login account; run account generation."
    else:
        account_status = "Active" if user.is_active else "Inactive"
        initial_password = (
            None
            if notes.startswith("Manual review:")
            else get_current_initial_password(user, role)
        )
        if initial_password is None:
            initial_password_status = "Changed or unknown"
            if not notes:
                notes = "Initial password is not recorded or is no longer valid."
        else:
            initial_password_status = "Known current initial password"

    values = (
        role,
        identifier or "",
        name,
        user.username if user else "",
        email,
        department or "",
        courses,
        account_status,
        initial_password_status,
        initial_password or "",
        notes,
    )
    return tuple(_csv_safe(value) for value in values)


def build_credentials_csv():
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(CSV_HEADERS)

    for student in Student.objects.select_related(
        "user",
        "semester",
        "section",
    ).order_by("student_id", "name", "pk"):
        user = student.user
        notes = ""
        if user is None:
            notes = "Student profile has no linked user account."
        else:
            role_names = {
                name.casefold()
                for name in user.groups.values_list("name", flat=True)
            }
            if user.is_staff or user.is_superuser or (
                role_names & {"admin", "teacher"}
            ):
                notes = "Manual review: linked account has a conflicting role."
            elif "student" not in role_names:
                notes = "Student group missing; run account generation."
        writer.writerow(
            _row(
                "Student",
                student.student_id,
                student.name,
                user,
                student.email,
                student.department,
                student.course,
                notes,
            )
        )

    for teacher in Teacher.objects.select_related(
        "user",
        "department",
    ).prefetch_related("courses").order_by("name", "pk"):
        user = teacher.user
        notes = ""
        if user is None:
            notes = "Teacher profile has no linked user account."
        else:
            role_names = {
                name.casefold()
                for name in user.groups.values_list("name", flat=True)
            }
            if user.is_staff or user.is_superuser or (
                role_names & {"admin", "student"}
            ):
                notes = "Manual review: linked account has a conflicting role."
            elif "teacher" not in role_names:
                notes = "Teacher group missing; run account generation."
        teacher_id = getattr(teacher, "teacher_id", "")
        if not teacher_id:
            notes = "; ".join(
                item
                for item in (notes, "Teacher model has no Teacher ID field.")
                if item
            )
        writer.writerow(
            _row(
                "Teacher",
                teacher_id,
                teacher.name,
                user,
                teacher.email,
                teacher.department,
                "; ".join(course.name for course in teacher.courses.all()),
                notes,
            )
        )

    response = HttpResponse(
        output.getvalue(),
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = (
        'attachment; filename="student_teacher_login_credentials.csv"'
    )
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    return response
