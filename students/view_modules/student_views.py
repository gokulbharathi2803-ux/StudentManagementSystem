from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from students.models import Student, Attendance, Mark
from students.permissions import get_student_profile, role_required


@login_required
@role_required("Student")
def student_dashboard(request):
    student = get_student_profile(request.user)

    if student is None:
        return render(
            request,
            "students/dashboards/student_dashboard.html",
            {
                "student_profile": None,
                "student_marks": [],
                "student_attendance": [],
                "total_marks_records": 0,
                "present_count": 0,
                "attendance_count": 0,
                "profile_message": (
                    "No student profile matches your account email. "
                    "Please contact your administrator."
                ),
            },
        )

    student_marks = Mark.objects.filter(student=student).order_by("subject")
    student_attendance = Attendance.objects.filter(
        student=student
    ).order_by("-date")

    attendance_count = student_attendance.count()
    present_count = student_attendance.filter(status="Present").count()

    context = {
        "student_profile": student,
        "student_marks": student_marks,
        "student_attendance": student_attendance,
        "total_marks_records": student_marks.count(),
        "present_count": present_count,
        "attendance_count": attendance_count,
        "total_attendance_records": attendance_count,
        "attendance_percentage": (
            round(present_count * 100 / attendance_count, 2)
            if attendance_count
            else 0
        ),
        "profile_message": "",
    }

    return render(
        request,
        "students/dashboards/student_dashboard.html",
        context,
    )


@login_required
@role_required("Student")
def student_profile(request):
    student = get_student_profile(request.user)

    return render(
        request,
        "students/student_profile.html",
        {"student_profile": student},
    )


@login_required
@role_required("Student")
def student_results(request):
    student = get_student_profile(request.user)

    marks = (
        Mark.objects.filter(student=student).order_by("subject")
        if student
        else Mark.objects.none()
    )

    return render(
        request,
        "students/student_results.html",
        {
            "student_profile": student,
            "marks": marks,
        },
    )
