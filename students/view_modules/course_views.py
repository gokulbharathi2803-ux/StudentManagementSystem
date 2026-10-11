from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from students.forms import CourseForm
from students.models import Course, Student
from students.permissions import is_admin, role_required


@login_required
@role_required("Admin", "Teacher")
def course_list(request):
    courses = Course.objects.select_related("department").order_by("name")
    if not is_admin(request.user):
        assigned_ids = request.user.teacher_profile.courses.values("pk") if hasattr(
            request.user, "teacher_profile"
        ) else []
        courses = courses.filter(pk__in=assigned_ids)
    query = request.GET.get("q", "").strip()
    if query:
        courses = courses.filter(
            Q(name__icontains=query)
            | Q(department__name__icontains=query)
            | Q(duration__icontains=query)
        )
    page_obj = Paginator(courses, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "students/course_list.html",
        {
            "courses": page_obj.object_list,
            "page_obj": page_obj,
            "query": query,
            "total_courses": courses.count(),
            "is_admin": is_admin(request.user),
        },
    )


@login_required
@role_required("Admin")
def course_create(request):
    form = CourseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Course created.")
        return redirect("course_list")
    return render(
        request,
        "students/catalog_form.html",
        {"form": form, "page_title": "Add Course", "cancel_url": "course_list"},
    )


@login_required
@role_required("Admin")
def course_update(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    previous_name = course.name
    form = CourseForm(request.POST or None, instance=course)
    if request.method == "POST" and form.is_valid():
        updated_course = form.save()
        if previous_name != updated_course.name:
            Student.objects.filter(
                course__iexact=previous_name,
                department__iexact=updated_course.department.name,
            ).update(course=updated_course.name)
        messages.success(request, "Course updated.")
        return redirect("course_list")
    return render(
        request,
        "students/catalog_form.html",
        {"form": form, "page_title": "Edit Course", "cancel_url": "course_list"},
    )


@login_required
@role_required("Admin")
@require_POST
def course_delete(request, course_id):
    course = get_object_or_404(Course.objects.select_related("department"), pk=course_id)
    has_students = Student.objects.filter(
        course__iexact=course.name,
        department__iexact=course.department.name,
    ).exists()
    if course.teachers.exists() or has_students:
        messages.error(
            request,
            "This course is in use. Reassign its teachers and students before deleting it.",
        )
    else:
        course.delete()
        messages.success(request, "Course deleted.")
    return redirect("course_list")
