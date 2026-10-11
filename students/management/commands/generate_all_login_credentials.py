import csv
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from students.account_services import ensure_missing_accounts
from students.credential_reports import build_credentials_csv


class Command(BaseCommand):
    help = (
        "Safely process student/teacher accounts and write all_login_credentials.csv "
        "beside manage.py."
    )

    output_headers = (
        "Role",
        "ID",
        "Name",
        "Username",
        "Email",
        "Initial Password",
    )

    def handle(self, *args, **options):
        self.stdout.write("Checking student and teacher accounts...")
        summary = ensure_missing_accounts()

        report_response = build_credentials_csv()
        source_rows = csv.DictReader(
            StringIO(report_response.content.decode("utf-8-sig"))
        )
        output_path = Path(settings.BASE_DIR) / "all_login_credentials.csv"
        with output_path.open("w", encoding="utf-8-sig", newline="") as output_file:
            writer = csv.writer(output_file)
            writer.writerow(self.output_headers)
            for row in source_rows:
                writer.writerow(
                    (
                        row["Role"],
                        row["Student ID or Teacher ID"],
                        row["Full name"],
                        row["Username"],
                        row["Email"],
                        row["Initial password"],
                    )
                )

        self.stdout.write("")
        self.stdout.write("Student and teacher account summary:")
        self.stdout.write(f"  Students: {summary['students_total']}")
        self.stdout.write(f"  Teachers: {summary['teachers_total']}")
        self.stdout.write(f"  Created: {summary['created']}")
        self.stdout.write(f"  Already existed: {summary['already_existed']}")
        self.stdout.write(f"  Need manual review: {summary['manual_review']}")
        for conflict in summary["conflicts"]:
            self.stderr.write(f"  REVIEW: {conflict}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {summary['students_total'] + summary['teachers_total']} "
                f"records to {output_path}"
            )
        )
        self.stdout.write(
            "Unknown or unverifiable initial passwords are left blank; "
            "existing passwords were not reset."
        )
