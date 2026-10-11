from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from students.models import Attendance, Department, Mark, Student
from students.permissions import (
    get_teacher_profile,
    role_required,
    students_for_teacher,
)


@login_required
@role_required("Teacher")
def teacher_dashboard(request):
    teacher = get_teacher_profile(request.user)
    students = students_for_teacher(request.user)
    attendance = Attendance.objects.filter(student__in=students)
    total_attendance = attendance.count()
    present_count = attendance.filter(status="Present").count()
    context = {
        "teacher_profile": teacher,
        "total_students": students.count(),
        "total_departments": Department.objects.filter(
            courses__teachers=teacher
        ).distinct().count() if teacher else 0,
        "total_courses": teacher.courses.count() if teacher else 0,
        "total_attendance": total_attendance,
        "attendance_percentage": (
            round(present_count * 100 / total_attendance, 2)
            if total_attendance
            else 0
        ),
        "recent_students": students.order_by("-pk")[:5],
        "recent_marks": Mark.objects.select_related("student")
        .filter(student__in=students)
        .order_by("-created_at")[:5],
    }
    return render(
        request,
        "students/dashboards/teacher_dashboard.html",
        context,
    )


@login_required
@role_required("Teacher")
def teacher_students(request):
    return redirect("student_list")
