from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib import admin
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_GET

from students.account_services import (
    StudentAccountConflict,
    ensure_missing_accounts,
    ensure_student_account,
    ensure_teacher_account,
)
from students.credential_vault import CredentialEncryptionNotConfigured
from students.credential_reports import build_credentials_csv
from students.forms import UserCreateForm
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
from students.permissions import role_required


User = get_user_model()


@login_required
@role_required("Admin")
def admin_dashboard(request):
    total_attendance = Attendance.objects.count()
    present_count = Attendance.objects.filter(status="Present").count()
    attendance_percentage = (
        round(present_count / total_attendance * 100, 2)
        if total_attendance
        else 0
    )
    context = {
        "total_students": Student.objects.count(),
        "total_teachers": Teacher.objects.count(),
        "total_departments": Department.objects.count(),
        "total_courses": Course.objects.count(),
        "total_semesters": Semester.objects.count(),
        "total_sections": Section.objects.count(),
        "total_attendance": total_attendance,
        "present_count": present_count,
        "attendance_percentage": attendance_percentage,
        "recent_students": Student.objects.order_by("-pk")[:5],
        "recent_marks": Mark.objects.select_related("student").order_by(
            "-created_at"
        )[:5],
        "recent_attendance": Attendance.objects.select_related(
            "student"
        ).order_by("-date", "-pk")[:5],
        "can_manage_login_credentials": (
            request.user.is_staff
            and request.user.has_perm("students.manage_login_credentials")
        ),
    }
    return render(request, "students/dashboards/admin_dashboard.html", context)


@login_required
@role_required("Admin")
def manage_users(request):
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        role = form.cleaned_data["role"]
        try:
            with transaction.atomic():
                if role == "Student":
                    ensure_student_account(form.cleaned_data["student"])
                elif role == "Teacher":
                    teacher = Teacher(
                        name=form.cleaned_data["name"].strip(),
                        email=form.cleaned_data["email"],
                        phone=form.cleaned_data["phone"].strip(),
                        department=form.cleaned_data["department"],
                    )
                    ensure_teacher_account(teacher)
                    teacher.courses.set(form.cleaned_data["courses"])
                else:
                    user = form.save(commit=False)
                    user.email = form.cleaned_data["email"]
                    user.is_staff = True
                    user.save()
                    group, _ = Group.objects.get_or_create(name="Admin")
                    user.groups.add(group)
        except (StudentAccountConflict, CredentialEncryptionNotConfigured) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f"{role} account created successfully.")
            return redirect("manage_users")

    users = User.objects.prefetch_related("groups").order_by("username")
    teachers = Teacher.objects.select_related(
        "user", "department"
    ).prefetch_related("courses")
    context = {
        "users": users,
        "teachers": teachers,
        "form": form,
        "roles": Group.objects.filter(name__in=["Admin", "Teacher", "Student"]),
        "students": Student.objects.filter(user__isnull=True).order_by("name"),
        "departments": Department.objects.order_by("name"),
        "courses": Course.objects.select_related("department").order_by("name"),
    }
    return render(request, "students/manage_users.html", context)


def _require_credentials_permission(user):
    if not (
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and user.has_perm("students.manage_login_credentials")
    ):
        raise PermissionDenied


@require_http_methods(["GET", "POST"])
@login_required
def student_teacher_credentials(request):
    _require_credentials_permission(request.user)
    summary = None
    if request.method == "POST":
        summary = ensure_missing_accounts()
        messages.success(
            request,
            "Account processing finished: "
            f"{summary['created']} created, "
            f"{summary['already_existed']} already existed, "
            f"{summary['manual_review']} need manual review.",
        )
        if summary["conflicts"]:
            messages.warning(
                request,
                "Review the account notes below. Existing passwords and "
                "conflicting accounts were not changed.",
            )

    context = {
        **admin.site.each_context(request),
        "title": "Student and Teacher Login Credentials",
        "student_count": Student.objects.count(),
        "teacher_count": Teacher.objects.count(),
        "summary": summary,
    }
    return render(
        request,
        "admin/student_teacher_credentials.html",
        context,
    )


@require_GET
@login_required
def download_student_teacher_credentials(request):
    _require_credentials_permission(request.user)
    return build_credentials_csv()
