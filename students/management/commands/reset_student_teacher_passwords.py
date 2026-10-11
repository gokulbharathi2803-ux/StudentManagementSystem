from datetime import datetime
from pathlib import Path
import sqlite3

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from students.account_services import _teacher_login_identity
from students.credential_vault import (
    CredentialEncryptionNotConfigured,
    _fernet,
    record_initial_password,
)
from students.models import Student, Teacher


CONFIRMATION = "RESET-STUDENT-TEACHER-PASSWORDS"
User = get_user_model()


class Command(BaseCommand):
    help = (
        "Back up SQLite, then explicitly reset eligible student and teacher "
        "passwords to the documented temporary-credential policy."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            default="",
            help=f"Required exact confirmation token: {CONFIRMATION}",
        )

    def handle(self, *args, **options):
        if options["confirm"] != CONFIRMATION:
            raise CommandError(
                "No passwords were changed. To explicitly authorize the "
                f"operation, pass --confirm {CONFIRMATION}."
            )
        if connection.vendor != "sqlite":
            raise CommandError(
                "This command currently supports SQLite backups only; "
                "no passwords were changed."
            )
        try:
            _fernet()
        except CredentialEncryptionNotConfigured as exc:
            raise CommandError(
                f"{exc} No passwords were changed."
            ) from exc

        candidates, skipped = self._collect_candidates()
        if not candidates:
            self.stdout.write("No eligible accounts found; no passwords changed.")
            self.stdout.write(f"Skipped for review: {skipped}")
            return

        backup_path = self._backup_database()
        with transaction.atomic():
            for role, profile, user, password in candidates:
                user.set_password(password)
                user.save(update_fields=["password"])
                record_initial_password(
                    user,
                    role,
                    password,
                    replace=True,
                )
                if role == "Student" and not profile.must_change_password:
                    Student.objects.filter(pk=profile.pk).update(
                        must_change_password=True
                    )

        self.stdout.write(self.style.SUCCESS(f"Database backup: {backup_path}"))
        self.stdout.write(
            self.style.SUCCESS(
                f"Reset {sum(role == 'Student' for role, *_ in candidates)} "
                "student and "
                f"{sum(role == 'Teacher' for role, *_ in candidates)} "
                "teacher password(s)."
            )
        )
        self.stdout.write(
            "Student temporary passwords are their Student IDs. Teacher "
            "temporary passwords follow the documented email-derived policy. "
            "The passwords are not printed; use the protected credentials report."
        )
        self.stdout.write(f"Skipped for manual review: {skipped}")

    def _collect_candidates(self):
        candidates = []
        skipped = 0
        groups = {
            group.name: group
            for group in Group.objects.filter(name__in=("Student", "Teacher"))
        }

        for student in Student.objects.select_related("user").order_by("pk"):
            user = student.user
            if (
                user is None
                or not student.student_id
                or user.username != student.student_id
                or (user.email or "").casefold() != student.email.casefold()
                or not self._has_only_role(user, "Student", groups)
            ):
                skipped += 1
                continue
            candidates.append(
                ("Student", student, user, student.student_id)
            )

        for teacher in Teacher.objects.select_related("user").order_by("pk"):
            user = teacher.user
            if (
                user is None
                or (user.email or "").casefold() != teacher.email.casefold()
                or not self._has_only_role(user, "Teacher", groups)
            ):
                skipped += 1
                continue
            teacher_id = getattr(teacher, "teacher_id", None)
            password = (
                teacher_id
                if teacher_id
                else _teacher_login_identity(teacher.email)[1]
            )
            candidates.append(("Teacher", teacher, user, password))

        return candidates, skipped

    @staticmethod
    def _has_only_role(user, role, groups):
        if (
            not user.is_active
            or user.is_staff
            or user.is_superuser
            or role not in groups
        ):
            return False
        role_names = {
            name.casefold() for name in user.groups.values_list("name", flat=True)
        }
        allowed = role.casefold()
        return (
            user.groups.filter(name=role).exists()
            and allowed in role_names
            and not ((role_names & {"admin", "student", "teacher"}) - {allowed})
        )

    @staticmethod
    def _backup_database():
        connection.ensure_connection()
        raw_connection = connection.connection
        if raw_connection is None:
            raise CommandError("Could not open SQLite database; no passwords changed.")

        output_dir = Path(settings.BASE_DIR)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = output_dir / f"db_backup_before_role_password_reset_{stamp}.sqlite3"
        try:
            with sqlite3.connect(backup_path) as backup_connection:
                raw_connection.backup(backup_connection)
        except sqlite3.Error as exc:
            backup_path.unlink(missing_ok=True)
            raise CommandError(
                f"Could not create the required database backup; "
                f"no passwords were changed: {exc}"
            ) from exc
        return backup_path
