from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from students.forms import SectionForm, SemesterForm
from students.models import Section, Semester, Student
from students.permissions import is_admin, role_required


@login_required
@role_required("Admin", "Teacher")
def academic_list(request):
    return render(
        request,
        "students/academic_list.html",
        {
            "semesters": Paginator(
                Semester.objects.prefetch_related("sections").order_by("number"),
                50,
            ).get_page(request.GET.get("semester_page")),
            "sections": Paginator(
                Section.objects.select_related("semester").order_by(
                    "semester__number", "name"
                ),
                50,
            ).get_page(request.GET.get("section_page")),
            "is_admin": is_admin(request.user),
        },
    )


@login_required
@role_required("Admin")
def semester_create(request):
    form = SemesterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Semester created.")
        return redirect("academic_list")
    return render(
        request,
        "students/catalog_form.html",
        {"form": form, "page_title": "Add Semester", "cancel_url": "academic_list"},
    )


@login_required
@role_required("Admin")
def semester_update(request, semester_id):
    semester = get_object_or_404(Semester, pk=semester_id)
    form = SemesterForm(request.POST or None, instance=semester)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Semester updated.")
        return redirect("academic_list")
    return render(
        request,
        "students/catalog_form.html",
        {"form": form, "page_title": "Edit Semester", "cancel_url": "academic_list"},
    )


@login_required
@role_required("Admin")
@require_POST
def semester_delete(request, semester_id):
    semester = get_object_or_404(Semester, pk=semester_id)
    if semester.sections.exists() or Student.objects.filter(
        semester=semester
    ).exists():
        messages.error(
            request,
            "This semester is in use. Reassign its sections and students before deleting it.",
        )
    else:
        semester.delete()
        messages.success(request, "Semester deleted.")
    return redirect("academic_list")


@login_required
@role_required("Admin")
def section_create(request):
    form = SectionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Section created.")
        return redirect("academic_list")
    return render(
        request,
        "students/catalog_form.html",
        {"form": form, "page_title": "Add Section", "cancel_url": "academic_list"},
    )


@login_required
@role_required("Admin")
def section_update(request, section_id):
    section = get_object_or_404(Section, pk=section_id)
    form = SectionForm(request.POST or None, instance=section)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Section updated.")
        return redirect("academic_list")
    return render(
        request,
        "students/catalog_form.html",
        {"form": form, "page_title": "Edit Section", "cancel_url": "academic_list"},
    )


@login_required
@role_required("Admin")
@require_POST
def section_delete(request, section_id):
    section = get_object_or_404(Section, pk=section_id)
    if Student.objects.filter(section=section).exists():
        messages.error(
            request,
            "This section has students assigned. Reassign them before deleting it.",
        )
    else:
        section.delete()
        messages.success(request, "Section deleted.")
    return redirect("academic_list")
