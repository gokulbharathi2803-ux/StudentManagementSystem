from django.core.management.base import BaseCommand

from students.account_services import ensure_missing_accounts


class Command(BaseCommand):
    help = "Safely create missing student and teacher login accounts."

    def handle(self, *args, **options):
        self.stdout.write("Checking student and teacher account records...")
        summary = ensure_missing_accounts()
        self.stdout.write("")
        self.stdout.write("Student and teacher account summary:")
        self.stdout.write(f"  Students: {summary['students_total']}")
        self.stdout.write(f"  Teachers: {summary['teachers_total']}")
        self.stdout.write(f"  Created: {summary['created']}")
        self.stdout.write(f"  Already existed: {summary['already_existed']}")
        self.stdout.write(f"  Need manual review: {summary['manual_review']}")
        for conflict in summary["conflicts"]:
            self.stderr.write(f"  REVIEW: {conflict}")

        if summary["manual_review"]:
            self.stderr.write(
                "Conflicting accounts were not overwritten. Resolve review "
                "items before relying on the report."
            )
