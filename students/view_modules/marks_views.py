from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from students.forms import MarkForm
from students.models import Mark, Student
from students.permissions import (
    get_authorized_student,
    get_student_profile,
    is_admin,
    role_required,
    students_for_teacher,
)


def _staff_students(user):
    if is_admin(user):
        return Student.objects.order_by("name")
    return students_for_teacher(user).order_by("name")


@login_required
@role_required("Admin", "Teacher", "Student")
def marks_results(request):
    students = _staff_students(request.user)
    if is_admin(request.user) or request.user.groups.filter(
        name__iexact="Teacher"
    ).exists():
        marks = Mark.objects.select_related("student").filter(
            student__in=students
        )
        can_manage_marks = True
    else:
        student = get_student_profile(request.user)
        marks = (
            Mark.objects.select_related("student").filter(student=student)
            if student
            else Mark.objects.none()
        )
        can_manage_marks = False

    search_query = request.GET.get("q", "").strip()
    student_filter = request.GET.get("student", "").strip()
    if search_query:
        marks = marks.filter(
            Q(student__name__icontains=search_query)
            | Q(student__email__icontains=search_query)
            | Q(subject__icontains=search_query)
        )
    if student_filter.isdigit():
        marks = marks.filter(student_id=student_filter)

    marks = marks.annotate(
        _total=(
            F("internal_marks")
            + F("assignment_marks")
            + F("practical_marks")
            + F("exam_marks")
        )
    ).order_by("student__name", "subject")
    summary = marks.aggregate(
        total=Count("pk"),
        average=Avg("_total"),
        passed=Count("pk", filter=Q(_total__gte=40)),
    )
    total = summary["total"] or 0
    page_obj = Paginator(marks, 25).get_page(request.GET.get("page"))
    form = MarkForm(students=students) if can_manage_marks else None
    return render(
        request,
        "students/marks_results.html",
        {
            "marks": page_obj.object_list,
            "page_obj": page_obj,
            "students": students,
            "form": form,
            "can_manage_marks": can_manage_marks,
            "can_delete_marks": is_admin(request.user),
            "search_query": search_query,
            "student_filter": student_filter,
            "total_records": total,
            "passed_records": summary["passed"] or 0,
            "failed_records": total - (summary["passed"] or 0),
            "average_percentage": round(summary["average"] or 0, 2),
        },
    )


@login_required
@role_required("Admin", "Teacher")
@require_POST
def add_mark(request):
    students = _staff_students(request.user)
    form = MarkForm(request.POST, students=students)
    if form.is_valid():
        mark = form.save(commit=False)
        mark.student = get_authorized_student(request.user, mark.student_id)
        mark.save()
        messages.success(request, "Marks saved successfully.")
        return redirect("marks_results")

    marks = Mark.objects.select_related("student").filter(student__in=students)
    return render(
        request,
        "students/marks_results.html",
        {
            "marks": marks[:25],
            "students": students,
            "form": form,
            "can_manage_marks": True,
            "can_delete_marks": is_admin(request.user),
            "total_records": marks.count(),
        },
        status=400,
    )


@login_required
@role_required("Admin", "Teacher")
def edit_mark(request, mark_id):
    mark = get_object_or_404(
        Mark.objects.select_related("student"),
        pk=mark_id,
    )
    authorized_student = get_authorized_student(
        request.user,
        mark.student_id,
    )
    students = _staff_students(request.user)
    form = MarkForm(
        request.POST or None,
        instance=mark,
        students=students,
    )
    if request.method == "POST" and form.is_valid():
        updated_mark = form.save(commit=False)
        updated_mark.student = get_authorized_student(
            request.user,
            updated_mark.student_id,
        )
        updated_mark.save()
        messages.success(request, "Marks updated successfully.")
        return redirect("marks_results")
    return render(
        request,
        "students/edit_mark.html",
        {
            "form": form,
            "mark": mark,
            "student": authorized_student,
        },
    )


@login_required
@role_required("Admin")
@require_POST
def delete_mark(request, mark_id):
    mark = get_object_or_404(Mark, pk=mark_id)
    mark.delete()
    messages.success(request, "Mark record deleted.")
    return redirect("marks_results")
