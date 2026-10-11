
import csv
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .account_services import StudentAccountConflict, ensure_student_account
from .forms import StudentForm
from .models import Course, Department, Section, Semester, Student
from .permissions import (
    get_authorized_student,
    is_admin,
    is_teacher,
    role_required,
    students_for_teacher,
)


@login_required
def dashboard(request):
    if is_admin(request.user):
        return redirect("admin_dashboard")
    if is_teacher(request.user):
        return redirect("teacher_dashboard")
    if request.user.groups.filter(name__iexact="Student").exists():
        return redirect("student_dashboard")
    raise PermissionDenied


PAGE_SIZES = (10, 25, 50, 100)


def _visible_student_queryset(user):
    students = Student.objects.select_related("semester", "section", "user")
    if is_teacher(user) and not is_admin(user):
        students = students.filter(
            pk__in=students_for_teacher(user).values("pk")
        )
    return students


def _filtered_student_queryset(request):
    students = _visible_student_queryset(request.user)
    query = request.GET.get("q", "").strip()
    department_id = request.GET.get("department", "").strip()
    course_id = request.GET.get("course", "").strip()
    semester_id = request.GET.get("semester", "").strip()
    section_id = request.GET.get("section", "").strip()

    if query:
        students = students.filter(
            Q(student_id__icontains=query)
            | Q(name__icontains=query)
            | Q(email__icontains=query)
            | Q(department__icontains=query)
            | Q(course__icontains=query)
        )
    if department_id.isdigit():
        department = Department.objects.filter(pk=department_id).first()
        if department:
            students = students.filter(department__iexact=department.name)
    if course_id.isdigit():
        course = Course.objects.filter(pk=course_id).first()
        if course:
            students = students.filter(course__iexact=course.name)
    if semester_id.isdigit():
        students = students.filter(semester_id=semester_id)
    if section_id.isdigit():
        students = students.filter(section_id=section_id)

    return students.order_by("name", "pk"), query


def _student_account_display(student):
    user = student.user
    if user is None:
        return {
            "username": "",
            "password_status": "Changed or unknown",
            "account_status": "Not created",
        }
    return {
        "username": user.username,
        "password_status": (
            "Default Student ID"
            if student.must_change_password
            else "Changed or unknown"
        ),
        "account_status": "Active" if user.is_active else "Inactive",
    }


def _safe_csv_value(value):
    value = "" if value is None else str(value)
    if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


@login_required
@role_required("Admin", "Teacher")
def student_list(request):
    students, query = _filtered_student_queryset(request)
    requested_size = request.GET.get("per_page", "25")
    page_size = int(requested_size) if requested_size.isdigit() else 25
    if page_size not in PAGE_SIZES:
        page_size = 25

    page_obj = Paginator(students, page_size).get_page(request.GET.get("page"))
    page_params = request.GET.copy()
    page_params.pop("page", None)
    export_params = request.GET.copy()
    export_params.pop("page", None)
    export_params.pop("per_page", None)
    student_rows = [
        {"student": student, **_student_account_display(student)}
        for student in page_obj.object_list
    ]
    return render(
        request,
        "students/student_list.html",
        {
            "students": student_rows,
            "page_obj": page_obj,
            "query": query,
            "page_size": page_size,
            "page_sizes": PAGE_SIZES,
            "page_query": page_params.urlencode(),
            "export_query": export_params.urlencode(),
            "filtered_count": students.count(),
            "departments": Department.objects.order_by("name"),
            "courses": Course.objects.select_related("department").order_by("name"),
            "semesters": Semester.objects.order_by("number"),
            "sections": Section.objects.select_related("semester"),
            "is_admin": is_admin(request.user),
            "can_delete_students": is_admin(request.user),
        },
    )


@login_required
@role_required("Admin", "Teacher")
def student_list_export(request):
    students, _query = _filtered_student_queryset(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="students.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(
        [
            "Student ID",
            "Student Name",
            "Username",
            "Initial Password Status",
            "Email",
            "Phone",
            "Department",
            "Course",
            "Semester",
            "Section",
            "Account Status",
        ]
    )
    for student in students.iterator():
        account = _student_account_display(student)
        writer.writerow(
            _safe_csv_value(value)
            for value in (
                student.student_id,
                student.name,
                account["username"],
                account["password_status"],
                student.email,
                student.phone,
                student.department,
                student.course,
                student.semester,
                student.section,
                account["account_status"],
            )
        )
    return response


@login_required
@role_required("Admin")
@require_POST
def generate_student_accounts(request):
    counts = {"created": 0, "updated": 0, "unchanged": 0, "conflicts": 0}
    for student in Student.objects.order_by("pk").iterator():
        try:
            result = ensure_student_account(student)
        except StudentAccountConflict:
            counts["conflicts"] += 1
            continue
        if result.created:
            counts["created"] += 1
        elif result.linked or result.renamed or result.group_added:
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1

    messages.success(
        request,
        "Student accounts: "
        f"{counts['created']} created, {counts['updated']} updated, "
        f"{counts['unchanged']} unchanged.",
    )
    if counts["conflicts"]:
        messages.warning(
            request,
            f"{counts['conflicts']} account conflict(s) were not changed. "
            "Run create_student_accounts from the terminal for details.",
        )
    return redirect("student_list")


@login_required
@role_required("Admin", "Teacher")
def student_detail(request, student_id):
    student = get_authorized_student(request.user, student_id)
    return render(request, "students/student_detail.html", {"student": student})


@login_required
@role_required("Admin")
def student_create(request):
    form = StudentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                student = form.save()
                ensure_student_account(student)
        except StudentAccountConflict as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Student and login account created.")
            return redirect("student_list")
    return render(
        request,
        "students/student_form.html",
        {"form": form, "page_title": "Add Student"},
    )


@login_required
@role_required("Admin")
def student_update(request, student_id):
    student = get_object_or_404(Student, pk=student_id)
    form = StudentForm(request.POST or None, instance=student)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                student = form.save()
                ensure_student_account(student)
        except StudentAccountConflict as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Student details updated.")
            return redirect("student_list")
    return render(
        request,
        "students/student_form.html",
        {"form": form, "student": student, "page_title": "Edit Student"},
    )


@login_required
@role_required("Admin")
def delete_student(request, student_id):
    student = get_object_or_404(Student, pk=student_id)

    if request.method == "POST":
        if student.attendance.exists() or student.marks.exists():
            messages.error(
                request,
                "This student has attendance or marks records. Remove or archive "
                "those records before deleting the student.",
            )
            return redirect("student_list")
        student.delete()
        messages.success(request, "Student deleted.")
        return redirect("student_list")

    return render(
        request,
        "students/delete_student.html",
        {"student": student},
    )
