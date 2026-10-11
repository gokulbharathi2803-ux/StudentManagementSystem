from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render

from students.models import Attendance, Course, Department, Mark, Student
from students.permissions import is_admin, role_required, students_for_teacher


@login_required
@role_required("Admin", "Teacher")
def reports(request):
    students = Student.objects.select_related("semester", "section")
    if not is_admin(request.user):
        students = students.filter(
            pk__in=students_for_teacher(request.user).values("pk")
        )

    query = request.GET.get("search", "").strip()
    report_type = request.GET.get("type", "students")
    if report_type not in {"students", "attendance", "marks", "departments", "courses"}:
        report_type = "students"

    if query:
        students = students.filter(
            Q(name__icontains=query)
            | Q(email__icontains=query)
            | Q(department__icontains=query)
            | Q(course__icontains=query)
        )

    student_ids = students.values("pk")
    attendance = Attendance.objects.filter(student_id__in=student_ids)
    marks = Mark.objects.select_related("student").filter(
        student_id__in=student_ids
    )
    departments = Department.objects.all()
    courses = Course.objects.select_related("department").all()
    if not is_admin(request.user):
        teacher = getattr(request.user, "teacher_profile", None)
        courses = courses.filter(teachers=teacher).distinct()
        departments = departments.filter(courses__in=courses).distinct()

    if query:
        attendance = attendance.filter(
            Q(student__name__icontains=query)
            | Q(student__email__icontains=query)
        )
        marks = marks.filter(
            Q(student__name__icontains=query)
            | Q(student__email__icontains=query)
            | Q(subject__icontains=query)
        )
        departments = departments.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
        courses = courses.filter(
            Q(name__icontains=query) | Q(department__name__icontains=query)
        )

    attendance_report = []
    attendance_totals = attendance.values("student_id").annotate(
        total_days=Count("pk"),
        present_days=Count("pk", filter=Q(status="Present")),
        absent_days=Count("pk", filter=Q(status="Absent")),
    )
    attendance_by_id = {row["student_id"]: row for row in attendance_totals}
    for student in students:
        row = attendance_by_id.get(
            student.pk,
            {"total_days": 0, "present_days": 0, "absent_days": 0},
        )
        row["student"] = student
        row["percentage"] = (
            round(row["present_days"] * 100 / row["total_days"], 2)
            if row["total_days"]
            else 0
        )
        attendance_report.append(row)

    department_report = [
        {
            "department": department,
            "student_count": students.filter(
                department__iexact=department.name
            ).count(),
        }
        for department in departments
    ]
    course_report = [
        {
            "course": course,
            "student_count": students.filter(
                course__iexact=course.name,
                department__iexact=course.department.name,
            ).count(),
        }
        for course in courses
    ]

    passed_marks = sum(1 for mark in marks if mark.result == "Pass")
    total_attendance = attendance.count()
    present_count = attendance.filter(status="Present").count()
    context = {
        "students": students,
        "attendance_report": attendance_report,
        "marks_report": marks,
        "department_report": department_report,
        "course_report": course_report,
        "search": query,
        "report_type": report_type,
        "total_students": students.count(),
        "total_departments": departments.count(),
        "total_courses": courses.count(),
        "total_attendance": total_attendance,
        "present_count": present_count,
        "absent_count": attendance.filter(status="Absent").count(),
        "attendance_percentage": (
            round(present_count * 100 / total_attendance, 2)
            if total_attendance
            else 0
        ),
        "total_marks_records": marks.count(),
        "passed_marks": passed_marks,
        "failed_marks": marks.count() - passed_marks,
    }
    return render(request, "students/reports.html", context)
