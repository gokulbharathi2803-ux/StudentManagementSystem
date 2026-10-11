from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from students.account_services import StudentAccountConflict, ensure_student_account
from students.models import Student


class Command(BaseCommand):
    help = "Create or safely link Student-ID-based login accounts for all students."

    def handle(self, *args, **options):
        students = list(Student.objects.select_related("user").order_by("pk"))
        counts = Counter()
        ids_seen = set()

        self.stdout.write(f"Processing {len(students)} student profile(s).")
        for index, student in enumerate(students, start=1):
            student_id = (student.student_id or "").strip()
            duplicate_id = student_id.casefold() in ids_seen if student_id else False
            if student_id:
                ids_seen.add(student_id.casefold())

            if duplicate_id:
                counts["conflicts"] += 1
                self.stderr.write(
                    f"[{index}/{len(students)}] CONFLICT {student.email}: "
                    f"duplicate Student ID {student_id!r}."
                )
                continue

            try:
                with transaction.atomic():
                    result = ensure_student_account(student)
            except StudentAccountConflict as exc:
                counts["conflicts"] += 1
                if not student_id:
                    counts["missing_student_id"] += 1
                self.stderr.write(
                    f"[{index}/{len(students)}] CONFLICT {student.email}: {exc}"
                )
                continue

            if result.created:
                counts["created"] += 1
                outcome = "CREATED"
            elif result.linked or result.renamed or result.group_added:
                counts["updated"] += 1
                outcome = "UPDATED"
            else:
                counts["unchanged"] += 1
                outcome = "UNCHANGED"
            self.stdout.write(
                f"[{index}/{len(students)}] {outcome} "
                f"{student.student_id} ({student.email})"
            )

        self.stdout.write("")
        self.stdout.write(
            "Summary: "
            f"{counts['created']} created, "
            f"{counts['updated']} updated, "
            f"{counts['unchanged']} unchanged, "
            f"{counts['conflicts']} conflicts "
            f"({counts['missing_student_id']} missing Student ID)."
        )
        if counts["conflicts"]:
            self.stderr.write(
                "Resolve the listed conflicts manually; no conflicting account "
                "or profile was overwritten."
            )
