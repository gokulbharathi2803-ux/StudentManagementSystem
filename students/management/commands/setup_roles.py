from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from students.models import (
    Student,
    Department,
    Course,
    Attendance,
    Mark,
)


class Command(BaseCommand):
    help = "Create StudentMS user roles and permissions"

    def handle(self, *args, **options):
        admin_group, _ = Group.objects.get_or_create(name="Admin")
        teacher_group, _ = Group.objects.get_or_create(name="Teacher")
        student_group, _ = Group.objects.get_or_create(name="Student")

        # Admin: full access to StudentMS data models.
        admin_permissions = Permission.objects.filter(
            content_type__in=ContentType.objects.get_for_models(
                Student,
                Department,
                Course,
                Attendance,
                Mark,
            ).values()
        )
        admin_group.permissions.set(admin_permissions)

        # Teacher: view student/course information and manage
        # attendance and marks. No student deletion permission.
        teacher_permissions = Permission.objects.filter(
            content_type__in=ContentType.objects.get_for_models(
                Student,
                Department,
                Course,
                Attendance,
                Mark,
            ).values()
        )

        allowed_teacher_permissions = teacher_permissions.filter(
            codename__in=[
                "view_student",
                "view_department",
                "view_course",
                "view_attendance",
                "add_attendance",
                "change_attendance",
                "view_mark",
                "add_mark",
                "change_mark",
            ]
        )
        teacher_group.permissions.set(allowed_teacher_permissions)

        # Student: view-only access to the relevant model types.
        student_permissions = Permission.objects.filter(
            content_type__in=ContentType.objects.get_for_models(
                Student,
                Department,
                Course,
                Attendance,
                Mark,
            ).values(),
            codename__startswith="view_",
        )
        student_group.permissions.set(student_permissions)

        self.stdout.write(
            self.style.SUCCESS(
                "StudentMS roles created: Admin, Teacher, Student."
            )
        )
