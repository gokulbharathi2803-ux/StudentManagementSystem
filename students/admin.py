from django.contrib import admin, messages

from .account_services import StudentAccountConflict, ensure_student_account
from .forms import StudentForm
from .models import (
    Department,
    Course,
    Semester,
    Section,
    Student,
    Mark,
    Attendance,
)


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ("name", "number", "description")
    search_fields = ("name",)
    ordering = ("number",)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "semester", "description")
    list_filter = ("semester",)
    search_fields = ("name", "semester__name")


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    form = StudentForm
    list_display = (
        "student_id",
        "name",
        "email",
        "department",
        "course",
        "semester",
        "section",
    )
    list_filter = ("department", "course", "semester", "section")
    search_fields = (
        "student_id",
        "name",
        "email",
        "user__username",
        "department",
        "course",
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        try:
            ensure_student_account(obj)
        except StudentAccountConflict as exc:
            self.message_user(request, str(exc), level=messages.ERROR)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("name", "department", "duration")
    list_filter = ("department",)
    search_fields = ("name",)


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "date", "status")
    list_filter = ("date", "status")
    search_fields = ("student__name",)


@admin.register(Mark)
class MarkAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "subject",
        "internal_marks",
        "assignment_marks",
        "practical_marks",
        "exam_marks",
        "total_marks",
        "percentage",
        "grade",
        "result",
    )
    list_filter = ("subject",)
    search_fields = ("student__name", "subject")
