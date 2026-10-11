
from django.urls import path

from .views import (
    dashboard,
    delete_student,
    student_create,
    student_detail,
    student_list,
    student_list_export,
    student_update,
    generate_student_accounts,
)

from .view_modules.authentication import (
    StudentPasswordChangeView,
    role_login,
    role_logout,
)
from .view_modules.admin_views import admin_dashboard, manage_users
from .view_modules.teacher_views import teacher_dashboard, teacher_students
from .view_modules.student_views import (
    student_dashboard,
    student_profile,
    student_results,
)
from .view_modules.attendance_views import (
    attendance_list,
    mark_attendance,
    student_attendance,
)
from .view_modules.marks_views import (
    add_mark,
    delete_mark as delete_mark_record,
    edit_mark,
    marks_results,
)
from .view_modules.department_views import (
    department_create,
    department_delete,
    department_list,
    department_update,
)
from .view_modules.course_views import (
    course_create,
    course_delete,
    course_list,
    course_update,
)
from .view_modules.report_views import reports
from .view_modules.academic_views import (
    academic_list,
    section_create,
    section_delete,
    section_update,
    semester_create,
    semester_delete,
    semester_update,
)


urlpatterns = [
    path("login/", role_login, name="login"),
    path("logout/", role_logout, name="logout"),
    path(
        "student/password-change/",
        StudentPasswordChangeView.as_view(),
        name="student_password_change",
    ),

    path("", dashboard, name="dashboard"),
    path("admin-dashboard/", admin_dashboard, name="admin_dashboard"),
    path("teacher-dashboard/", teacher_dashboard, name="teacher_dashboard"),
    path("student-dashboard/", student_dashboard, name="student_dashboard"),

    path("manage-users/", manage_users, name="manage_users"),

    path("students/", student_list, name="student_list"),
    path("students/export.csv", student_list_export, name="student_list_export"),
    path(
        "students/accounts/generate/",
        generate_student_accounts,
        name="generate_student_accounts",
    ),
    path("students/add/", student_create, name="student_create"),
    path("students/<int:student_id>/", student_detail, name="student_detail"),
    path("students/<int:student_id>/edit/", student_update, name="student_update"),
    path(
        "students/delete/<int:student_id>/",
        delete_student,
        name="delete_student",
    ),
    path("teacher/students/", teacher_students, name="teacher_students"),

    path("student/profile/", student_profile, name="student_profile"),
    path("student/results/", student_results, name="student_results"),
    path("student/attendance/", student_attendance, name="student_attendance"),

    path("departments/", department_list, name="department_list"),
    path("departments/add/", department_create, name="department_create"),
    path("departments/<int:department_id>/edit/", department_update, name="department_update"),
    path("departments/<int:department_id>/delete/", department_delete, name="department_delete"),
    path("courses/", course_list, name="course_list"),
    path("courses/add/", course_create, name="course_create"),
    path("courses/<int:course_id>/edit/", course_update, name="course_update"),
    path("courses/<int:course_id>/delete/", course_delete, name="course_delete"),
    path("academic/", academic_list, name="academic_list"),
    path("academic/semesters/add/", semester_create, name="semester_create"),
    path("academic/semesters/<int:semester_id>/edit/", semester_update, name="semester_update"),
    path("academic/semesters/<int:semester_id>/delete/", semester_delete, name="semester_delete"),
    path("academic/sections/add/", section_create, name="section_create"),
    path("academic/sections/<int:section_id>/edit/", section_update, name="section_update"),
    path("academic/sections/<int:section_id>/delete/", section_delete, name="section_delete"),

    path("attendance/", attendance_list, name="attendance_list"),
    path("attendance/mark/", mark_attendance, name="mark_attendance"),

    path("marks-results/", marks_results, name="marks_results"),
    path("marks-results/add/", add_mark, name="add_mark"),
    path("marks-results/<int:mark_id>/edit/", edit_mark, name="edit_mark"),
    path(
        "marks-results/delete/<int:mark_id>/",
        delete_mark_record,
        name="delete_mark",
    ),

    path("reports/", reports, name="reports"),
]
