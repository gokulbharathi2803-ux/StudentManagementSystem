import csv
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from students.models import Student, Teacher


User = get_user_model()


class Command(BaseCommand):
    help = (
        "Report student and teacher login-account health without changing "
        "records or displaying passwords."
    )

    def handle(self, *args, **options):
        self.stdout.write("Read-only StudentMS login account diagnostic")
        self._report_role("Student", Student.objects.select_related("user"))
        self._report_role("Teacher", Teacher.objects.select_related("user"))
        self._report_csv()

    def _report_role(self, role, profiles):
        role_name = role.casefold()
        other_roles = {"admin", "teacher", "student"} - {role_name}
        total = linked = inactive = unusable = missing_group = wrong_case = 0
        conflicting_role = staff = identity_mismatch = 0

        for profile in profiles.order_by("pk").iterator():
            total += 1
            user = profile.user
            if user is None:
                continue

            linked += 1
            inactive += int(not user.is_active)
            unusable += int(not user.has_usable_password())
            staff += int(user.is_staff or user.is_superuser)

            group_names = list(user.groups.values_list("name", flat=True))
            folded_names = {name.casefold() for name in group_names}
            if role_name not in folded_names:
                missing_group += 1
            elif role not in group_names:
                wrong_case += 1
            conflicting_role += int(bool(folded_names & other_roles))

            if isinstance(profile, Student):
                identity_mismatch += int(
                    not profile.student_id
                    or user.username != profile.student_id
                    or (user.email or "").casefold() != profile.email.casefold()
                )
            else:
                identity_mismatch += int(
                    (user.email or "").casefold() != profile.email.casefold()
                )

        self.stdout.write(f"{role} profiles: {total}")
        self.stdout.write(f"  Linked accounts: {linked}")
        self.stdout.write(f"  Missing links: {total - linked}")
        self.stdout.write(f"  Inactive linked accounts: {inactive}")
        self.stdout.write(f"  Accounts without usable password hashes: {unusable}")
        self.stdout.write(f"  Missing {role} group membership: {missing_group}")
        self.stdout.write(f"  Case-mismatched {role} group names: {wrong_case}")
        self.stdout.write(f"  Accounts with conflicting role groups: {conflicting_role}")
        self.stdout.write(f"  Staff/superuser linked accounts: {staff}")
        self.stdout.write(f"  Profile/account identity mismatches: {identity_mismatch}")

    def _report_csv(self):
        csv_path = Path(settings.BASE_DIR) / "all_login_credentials.csv"
        if not csv_path.is_file():
            self.stdout.write("Credentials CSV: not found")
            return

        with csv_path.open(encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            rows = list(reader)

        if not rows or not {"Role", "ID", "Username", "Email"} <= set(
            reader.fieldnames or ()
        ):
            self.stdout.write("Credentials CSV: present but has invalid/missing columns")
            return

        student_rows = {
            row["ID"]: row
            for row in rows
            if row["Role"] == "Student" and row["ID"]
        }
        teacher_rows = {
            row["Email"].casefold(): row
            for row in rows
            if row["Role"] == "Teacher" and row["Email"]
        }
        student_matches = sum(
            student_rows.get(student.student_id, {}).get("Username")
            == (student.user.username if student.user_id else "")
            for student in Student.objects.select_related("user")
            if student.student_id in student_rows
        )
        teacher_matches = sum(
            teacher_rows.get(teacher.email.casefold(), {}).get("Username")
            == (teacher.user.username if teacher.user_id else "")
            for teacher in Teacher.objects.select_related("user")
            if teacher.email.casefold() in teacher_rows
        )
        password_column = next(
            (
                header
                for header in ("Initial Password", "Initial password")
                if header in (reader.fieldnames or ())
            ),
            None,
        )
        password_values = (
            sum(bool(row.get(password_column, "")) for row in rows)
            if password_column
            else 0
        )

        self.stdout.write(f"Credentials CSV: {csv_path}")
        self.stdout.write(f"  Rows: {len(rows)}")
        self.stdout.write(f"  Student username matches: {student_matches}")
        self.stdout.write(f"  Teacher username matches: {teacher_matches}")
        self.stdout.write(
            f"  Rows with a populated initial-password field: {password_values}"
        )
