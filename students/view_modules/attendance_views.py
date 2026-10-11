from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from students.models import Attendance, Student
from students.permissions import (
    get_authorized_student,
    get_student_profile,
    is_admin,
    role_required,
    students_for_teacher,
)


@login_required
@role_required("Admin", "Teacher")
def attendance_list(request):
    raw_date = request.GET.get("date", "").strip()
    selected_date = parse_date(raw_date) if raw_date else date.today()
    if selected_date is None:
        messages.error(request, "Enter a valid attendance date.")
        selected_date = date.today()

    students = Student.objects.order_by("name")
    if not is_admin(request.user):
        students = students.filter(
            pk__in=students_for_teacher(request.user).values("pk")
        )
    query = request.GET.get("q", "").strip()
    if query:
        students = students.filter(
            Q(name__icontains=query) | Q(email__icontains=query)
        )

    stats = {
        row["student_id"]: row
        for row in Attendance.objects.filter(student__in=students)
        .values("student_id")
        .annotate(
            present_days=Count("pk", filter=Q(status="Present")),
            absent_days=Count("pk", filter=Q(status="Absent")),
        )
    }
    records = Attendance.objects.filter(
        student__in=students,
        date=selected_date,
    ).select_related("student")
    attendance_by_student = {record.student_id: record for record in records}

    student_attendance = []
    for student in students.select_related("semester", "section"):
        totals = stats.get(
            student.pk,
            {"present_days": 0, "absent_days": 0},
        )
        total_days = totals["present_days"] + totals["absent_days"]
        record = attendance_by_student.get(student.pk)
        student_attendance.append(
            {
                "student": student,
                "status": record.status if record else "Not marked",
                "present_days": totals["present_days"],
                "absent_days": totals["absent_days"],
                "attendance_percentage": (
                    round(totals["present_days"] * 100 / total_days, 2)
                    if total_days
                    else 0
                ),
            }
        )

    return render(
        request,
        "students/attendance_list.html",
        {
            "student_attendance": student_attendance,
            "selected_date": selected_date.isoformat(),
            "query": query,
            "can_mark_attendance": True,
        },
    )


@login_required
@role_required("Admin", "Teacher")
@require_POST
def mark_attendance(request):
    date_value = parse_date(request.POST.get("date", "").strip())
    status = request.POST.get("status", "")
    student_id = request.POST.get("student_id", "").strip()
    if not date_value or status not in dict(Attendance.STATUS_CHOICES):
        messages.error(request, "Choose a valid date and attendance status.")
        return redirect("attendance_list")

    try:
        student = get_authorized_student(request.user, student_id)
    except (ValueError, TypeError):
        messages.error(request, "Select a valid student.")
        return redirect("attendance_list")

    Attendance.objects.update_or_create(
        student=student,
        date=date_value,
        defaults={"status": status},
    )
    messages.success(request, f"Attendance saved for {student.name}.")
    return redirect(f"/attendance/?date={date_value.isoformat()}")


@login_required
@role_required("Student")
def student_attendance(request):
    student = get_student_profile(request.user)
    records = (
        Attendance.objects.filter(student=student).order_by("-date")
        if student
        else Attendance.objects.none()
    )
    present_days = records.filter(status="Present").count()
    total_days = records.count()
    return render(
        request,
        "students/student_attendance.html",
        {
            "student_profile": student,
            "attendance_records": records,
            "present_days": present_days,
            "absent_days": total_days - present_days,
            "attendance_percentage": (
                round(present_days * 100 / total_days, 2)
                if total_days
                else 0
            ),
        },
    )
