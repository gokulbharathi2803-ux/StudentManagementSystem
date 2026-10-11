from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from students.forms import DepartmentForm
from students.models import Department, Student
from students.permissions import is_admin, role_required


@login_required
@role_required("Admin", "Teacher")
def department_list(request):
    departments = Department.objects.prefetch_related("courses").order_by("name")
    if not is_admin(request.user):
        teacher = getattr(request.user, "teacher_profile", None)
        departments = departments.filter(courses__teachers=teacher).distinct()
    query = request.GET.get("q", "").strip()
    if query:
        departments = departments.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
    page_obj = Paginator(departments, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "students/department_list.html",
        {
            "departments": page_obj.object_list,
            "page_obj": page_obj,
            "query": query,
            "is_admin": is_admin(request.user),
        },
    )


@login_required
@role_required("Admin")
def department_create(request):
    form = DepartmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Department created.")
        return redirect("department_list")
    return render(
        request,
        "students/catalog_form.html",
        {
            "form": form,
            "page_title": "Add Department",
            "cancel_url": "department_list",
        },
    )


@login_required
@role_required("Admin")
def department_update(request, department_id):
    department = get_object_or_404(Department, pk=department_id)
    form = DepartmentForm(request.POST or None, instance=department)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Department updated.")
        return redirect("department_list")
    return render(
        request,
        "students/catalog_form.html",
        {
            "form": form,
            "page_title": "Edit Department",
            "cancel_url": "department_list",
        },
    )


@login_required
@role_required("Admin")
@require_POST
def department_delete(request, department_id):
    department = get_object_or_404(Department, pk=department_id)
    has_students = Student.objects.filter(
        department__iexact=department.name
    ).exists()
    if (
        department.courses.exists()
        or department.teachers.exists()
        or has_students
    ):
        messages.error(
            request,
            "This department is in use. Reassign its courses, teachers, and "
            "students before deleting it.",
        )
    else:
        department.delete()
        messages.success(request, "Department deleted.")
    return redirect("department_list")
