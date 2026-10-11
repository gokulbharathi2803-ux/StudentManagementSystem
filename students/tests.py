from datetime import date
import csv
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command, CommandError
from django.test import TestCase
from django.urls import reverse
from django.test.utils import override_settings

from students.forms import MarkForm, RoleLoginForm
from students.models import (
    Attendance,
    Course,
    Department,
    InitialLoginCredential,
    Mark,
    Semester,
    Student,
    Teacher,
)


User = get_user_model()
TEST_CREDENTIAL_KEY = Fernet.generate_key().decode("ascii")


@override_settings(STUDENTMS_CREDENTIAL_ENCRYPTION_KEY=TEST_CREDENTIAL_KEY)
class StudentMSWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_group = Group.objects.create(name="Admin")
        cls.teacher_group = Group.objects.create(name="Teacher")
        cls.student_group = Group.objects.create(name="Student")
        cls.department = Department.objects.create(name="Science")
        cls.course = Course.objects.create(
            name="Biology",
            department=cls.department,
            duration="3 years",
        )
        cls.semester = Semester.objects.create(name="Semester 1", number=1)

        cls.admin = User.objects.create_user(
            username="admin",
            password="safe-password",
        )
        cls.admin.groups.add(cls.admin_group)
        cls.teacher_user = User.objects.create_user(
            username="teacher",
            password="safe-password",
        )
        cls.teacher_user.groups.add(cls.teacher_group)
        cls.teacher = Teacher.objects.create(
            user=cls.teacher_user,
            name="Taylor Teacher",
            email="teacher@example.test",
            department=cls.department,
        )
        cls.teacher.courses.add(cls.course)

        cls.student_user = User.objects.create_user(
            username="student",
            email="student@example.test",
            password="safe-password",
        )
        cls.student_user.groups.add(cls.student_group)
        cls.student = Student.objects.create(
            student_id="STU-TEST-001",
            user=cls.student_user,
            name="Sam Student",
            email="student@example.test",
            department=cls.department.name,
            course=cls.course.name,
            semester=cls.semester,
        )
        cls.other_student = Student.objects.create(
            name="Alex Other",
            email="other@example.test",
            department=cls.department.name,
            course="Unassigned",
        )

    def test_login_redirects_by_role(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": self.student_user.username,
                "password": "safe-password",
                "role": "student",
            },
        )
        self.assertRedirects(response, reverse("student_dashboard"))

    def test_teacher_can_login_with_teacher_role(self):
        self.teacher_user.set_password("teacher-login-password")
        self.teacher_user.save(update_fields=["password"])
        response = self.client.post(
            reverse("login"),
            {
                "username": self.teacher_user.username,
                "password": "teacher-login-password",
                "role": "teacher",
            },
        )
        self.assertRedirects(response, reverse("teacher_dashboard"))

    def test_staff_alias_can_login_as_teacher(self):
        self.teacher_user.username = "demo_tch007"
        self.teacher_user.set_password("teacher-login-password")
        self.teacher_user.save(update_fields=["username", "password"])

        response = self.client.post(
            reverse("login"),
            {
                "username": "demo_tch007",
                "password": "teacher-login-password",
                "role": "staff",
            },
        )

        self.assertRedirects(response, reverse("teacher_dashboard"))

    def test_login_form_role_values_match_authentication_view(self):
        response = self.client.get(reverse("login"))

        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')
        self.assertContains(response, 'name="role"')
        self.assertContains(response, 'value="staff"')
        self.assertContains(response, 'value="teacher"')
        self.assertContains(response, 'value="student"')
        self.assertEqual(RoleLoginForm().fields["role"].initial, "staff")

    def test_wrong_role_and_invalid_password_are_rejected(self):
        for credentials in (
            {
                "username": self.student_user.username,
                "password": "safe-password",
                "role": "teacher",
            },
            {
                "username": self.student_user.username,
                "password": "incorrect-password",
                "role": "student",
            },
            {
                "username": self.teacher_user.username,
                "password": "incorrect-password",
                "role": "teacher",
            },
        ):
            with self.subTest(role=credentials["role"], username=credentials["username"]):
                response = self.client.post(reverse("login"), credentials)
                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response,
                    "Invalid username, password, or selected role.",
                )
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_admin_login_flow_is_unchanged(self):
        self.admin.set_password("admin-login-password")
        self.admin.save(update_fields=["password"])
        response = self.client.post(
            reverse("login"),
            {
                "username": self.admin.username,
                "password": "admin-login-password",
                "role": "admin",
            },
        )
        self.assertRedirects(response, reverse("admin_dashboard"))

    def test_logout_requires_post(self):
        self.client.force_login(self.student_user)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))

    def test_admin_dashboard_and_student_list_render(self):
        self.client.force_login(self.admin)
        for route in (
            "admin_dashboard",
            "student_list",
            "department_list",
            "course_list",
            "academic_list",
            "attendance_list",
            "marks_results",
            "reports",
            "manage_users",
        ):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 200)
        listing = self.client.get(reverse("student_list"))
        self.assertContains(listing, "Sam Student")
        self.assertContains(listing, "Add student")

    def test_role_dashboards_use_shared_responsive_shell(self):
        for user, route in (
            (self.admin, "admin_dashboard"),
            (self.teacher_user, "teacher_dashboard"),
            (self.student_user, "student_dashboard"),
        ):
            with self.subTest(route=route):
                self.client.force_login(user)
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="layout"')
                self.assertContains(response, 'class="sidebar admin-sidebar"')
                self.assertContains(response, "/static/css/studentms.css")

        superuser = User.objects.create_superuser(
            username="ui-admin",
            email="ui-admin@example.test",
            password="admin-ui-password",
        )
        self.client.force_login(superuser)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "studentms-admin")
        self.assertContains(response, "/static/css/studentms.css")

    def test_admin_can_create_and_update_student(self):
        self.client.force_login(self.admin)
        payload = {
            "student_id": "STU-TEST-002",
            "name": "New Student",
            "email": "new.student@example.test",
            "phone": "5550102",
            "department": "Science",
            "course": "Biology",
            "semester": self.semester.pk,
        }
        response = self.client.post(reverse("student_create"), payload)
        self.assertRedirects(response, reverse("student_list"))
        student = Student.objects.get(email=payload["email"])
        self.assertEqual(student.user.username, payload["student_id"])
        self.assertTrue(student.user.check_password(payload["student_id"]))
        self.assertTrue(student.user.groups.filter(name="Student").exists())

        payload["name"] = "Updated Student"
        response = self.client.post(
            reverse("student_update", args=[student.pk]),
            payload,
        )
        self.assertRedirects(response, reverse("student_list"))
        student.refresh_from_db()
        self.assertEqual(student.name, "Updated Student")

    def test_admin_can_create_department_and_course(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("department_create"),
            {"name": "Arts", "description": "Arts department"},
        )
        self.assertRedirects(response, reverse("department_list"))
        department = Department.objects.get(name="Arts")

        response = self.client.post(
            reverse("course_create"),
            {
                "name": "History",
                "department": department.pk,
                "duration": "4 years",
            },
        )
        self.assertRedirects(response, reverse("course_list"))
        self.assertTrue(
            Course.objects.filter(name="History", department=department).exists()
        )

    def test_teacher_and_student_pages_render(self):
        self.client.force_login(self.teacher_user)
        for route in (
            "teacher_dashboard",
            "student_list",
            "department_list",
            "course_list",
            "attendance_list",
            "marks_results",
            "reports",
        ):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 200)
        teacher_student_list = self.client.get(reverse("teacher_students"))
        self.assertRedirects(teacher_student_list, reverse("student_list"))

        self.client.force_login(self.student_user)
        for route in (
            "student_dashboard",
            "student_profile",
            "student_results",
            "student_attendance",
        ):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 200)

    def test_non_admin_cannot_manage_users_or_edit_student(self):
        self.client.force_login(self.teacher_user)
        self.assertEqual(self.client.get(reverse("manage_users")).status_code, 403)
        self.assertEqual(
            self.client.get(
                reverse("student_update", args=[self.student.pk])
            ).status_code,
            403,
        )

    def test_student_can_only_open_own_profile_and_results(self):
        self.client.force_login(self.student_user)
        own_profile = self.client.get(
            reverse("student_profile")
        )
        own_results = self.client.get(reverse("student_results"))
        other_profile = self.client.get(
            reverse("student_detail", args=[self.other_student.pk])
        )
        self.assertEqual(own_profile.status_code, 200)
        self.assertEqual(own_results.status_code, 200)
        self.assertEqual(other_profile.status_code, 403)

    def test_teacher_student_list_is_limited_to_assigned_course(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse("student_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sam Student")
        self.assertNotContains(response, "Alex Other")

    def test_teacher_cannot_mark_students_outside_assigned_courses(self):
        self.client.force_login(self.teacher_user)
        response = self.client.post(
            reverse("mark_attendance"),
            {
                "student_id": self.other_student.pk,
                "date": date(2025, 2, 3).isoformat(),
                "status": "Present",
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            Attendance.objects.filter(student=self.other_student).exists()
        )

    def test_attendance_update_preserves_one_record_per_student_and_date(self):
        self.client.force_login(self.admin)
        endpoint = reverse("mark_attendance")
        payload = {
            "student_id": self.student.pk,
            "date": date(2025, 2, 3).isoformat(),
            "status": "Present",
        }
        first = self.client.post(endpoint, payload)
        payload["status"] = "Absent"
        second = self.client.post(endpoint, payload)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(
            Attendance.objects.filter(
                student=self.student,
                date=date(2025, 2, 3),
            ).count(),
            1,
        )
        self.assertEqual(
            Attendance.objects.get(student=self.student).status,
            "Absent",
        )

    def test_deleting_student_with_academic_records_is_blocked(self):
        Attendance.objects.create(
            student=self.student,
            date=date(2025, 2, 3),
            status="Present",
        )
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("delete_student", args=[self.student.pk])
        )
        self.assertRedirects(response, reverse("student_list"))
        self.assertTrue(Student.objects.filter(pk=self.student.pk).exists())
        self.assertTrue(
            Attendance.objects.filter(student=self.student).exists()
        )

    def test_mark_form_enforces_component_maxima_and_calculates_total(self):
        valid = MarkForm(
            {
                "student": self.student.pk,
                "subject": "Biology",
                "internal_marks": 20,
                "assignment_marks": 10,
                "practical_marks": 20,
                "exam_marks": 50,
            },
            students=Student.objects.all(),
        )
        invalid = MarkForm(
            {
                "student": self.student.pk,
                "subject": "Biology",
                "internal_marks": 21,
                "assignment_marks": 10,
                "practical_marks": 20,
                "exam_marks": 50,
            },
            students=Student.objects.all(),
        )
        self.assertTrue(valid.is_valid(), valid.errors)
        self.assertFalse(invalid.is_valid())
        mark = valid.save()
        self.assertEqual(mark.total_marks, 100)
        self.assertEqual(mark.percentage, 100)
        self.assertEqual(mark.result, "Pass")

        over_total = MarkForm(
            {
                "student": self.student.pk,
                "subject": "Over total",
                "internal_marks": 20,
                "assignment_marks": 20,
                "practical_marks": 20,
                "exam_marks": 50,
            },
            students=Student.objects.all(),
        )
        self.assertFalse(over_total.is_valid())

    def test_student_results_are_read_only(self):
        Mark.objects.create(
            student=self.student,
            subject="Biology",
            internal_marks=15,
            assignment_marks=8,
            practical_marks=17,
            exam_marks=42,
        )
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("student_results"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Biology")
        self.assertNotContains(response, "add_mark")

    def test_student_list_search_pagination_and_complete_csv_export(self):
        students = []
        for index in range(30):
            students.append(
                Student(
                    student_id=f"STU-LIST-{index:03}",
                    name=f"List Student {index:03}",
                    email=f"list.student.{index:03}@example.test",
                    department="Science",
                    course="Biology",
                )
            )
        Student.objects.bulk_create(students)

        self.client.force_login(self.admin)
        first_page = self.client.get(
            reverse("student_list"),
            {"per_page": "10"},
        )
        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(len(first_page.context["students"]), 10)
        self.assertEqual(first_page.context["filtered_count"], 32)

        searched = self.client.get(
            reverse("student_list"),
            {"q": "STU-LIST-029"},
        )
        self.assertEqual(searched.context["filtered_count"], 1)
        self.assertContains(searched, "List Student 029")

        exported = self.client.get(
            reverse("student_list_export"),
            {"q": "List Student"},
        )
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported["Content-Type"], "text/csv; charset=utf-8")
        export_rows = list(csv.reader(exported.content.decode("utf-8-sig").splitlines()))
        self.assertEqual(len(export_rows), 31)
        self.assertEqual(export_rows[0][0], "Student ID")
        self.assertNotIn("Initial Password,", ",".join(export_rows[0]))
        self.assertEqual(export_rows[-1][0], "STU-LIST-029")

    def test_student_role_requires_password_change_only_for_default_id_password(self):
        self.student.student_id = "STU-TEST-001"
        self.student.save(update_fields=["student_id"])
        self.student_user.set_password("STU-TEST-001")
        self.student_user.save(update_fields=["password"])

        self.client.force_login(self.student_user)
        dashboard = self.client.get(reverse("student_dashboard"))
        self.assertRedirects(dashboard, reverse("student_password_change"))

        password_change = self.client.get(reverse("student_password_change"))
        self.assertEqual(password_change.status_code, 200)
        password_change_post = self.client.post(
            reverse("student_password_change"),
            {
                "old_password": "STU-TEST-001",
                "new_password1": "Changed-Student-Password-2036!",
                "new_password2": "Changed-Student-Password-2036!",
            },
        )
        self.assertRedirects(
            password_change_post,
            reverse("student_dashboard"),
        )
        self.assertEqual(
            self.client.get(reverse("student_dashboard")).status_code,
            200,
        )


@override_settings(STUDENTMS_CREDENTIAL_ENCRYPTION_KEY=TEST_CREDENTIAL_KEY)
class StudentAccountCommandTests(TestCase):
    def setUp(self):
        self.student_group, _ = Group.objects.get_or_create(name="Student")

    def test_command_creates_student_id_accounts_and_is_idempotent(self):
        first = Student.objects.create(
            student_id="STU-CMD-001",
            name="Account Student One",
            email="account.student.one@example.test",
            department="Science",
            course="Biology",
        )
        second_user = User.objects.create_user(
            username="old-student-username",
            email="account.student.two@example.test",
            password="Existing-Private-Password-2036!",
        )
        second_user.groups.add(self.student_group)
        second = Student.objects.create(
            student_id="STU-CMD-002",
            user=second_user,
            name="Account Student Two",
            email=second_user.email,
            department="Science",
            course="Biology",
        )

        call_command("create_student_accounts")

        first.refresh_from_db()
        second_user.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.user.username, "STU-CMD-001")
        self.assertTrue(first.user.check_password("STU-CMD-001"))
        self.assertTrue(first.user.is_active)
        self.assertTrue(first.user.groups.filter(name="Student").exists())
        self.assertTrue(first.must_change_password)
        self.assertEqual(second_user.username, "STU-CMD-002")
        self.assertTrue(
            second_user.check_password("Existing-Private-Password-2036!")
        )
        self.assertEqual(second.user_id, second_user.pk)

        rerun_output = tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8")
        call_command("create_student_accounts", stdout=rerun_output)
        rerun_output.seek(0)
        self.assertIn("0 created", rerun_output.read())
        self.assertEqual(User.objects.filter(username="STU-CMD-001").count(), 1)

    def test_command_reports_identity_conflict_without_changing_other_user(self):
        unrelated = User.objects.create_user(
            username="STU-CMD-CONFLICT",
            email="unrelated.user@example.test",
            password="Unrelated-Private-Password-2036!",
        )
        student = Student.objects.create(
            student_id="STU-CMD-CONFLICT",
            name="Conflict Student",
            email="conflict.student@example.test",
            department="Science",
            course="Biology",
        )
        output = tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8")
        errors = tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8")
        call_command("create_student_accounts", stdout=output, stderr=errors)
        errors.seek(0)
        self.assertIn("CONFLICT", errors.read())
        unrelated.refresh_from_db()
        student.refresh_from_db()
        self.assertEqual(unrelated.email, "unrelated.user@example.test")
        self.assertIsNone(student.user_id)


@override_settings(STUDENTMS_CREDENTIAL_ENCRYPTION_KEY=TEST_CREDENTIAL_KEY)
class LoginCredentialReportTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="credential-admin",
            email="credential-admin@example.test",
            password="Credential-Admin-Password-2036!",
        )
        Group.objects.get_or_create(name="Admin")
        self.student_group, _ = Group.objects.get_or_create(name="Student")
        self.teacher_group, _ = Group.objects.get_or_create(name="Teacher")

    def test_report_is_admin_only_and_includes_all_profiles(self):
        student_user = User.objects.create_user(
            username="report-student",
            email="report.student@example.test",
            password="Student-Existing-Password-2036!",
        )
        student_user.groups.add(self.student_group)
        Student.objects.create(
            student_id="STU-REPORT-001",
            user=student_user,
            name="Report Student",
            email=student_user.email,
            department="Science",
            course="Biology",
        )
        teacher_user = User.objects.create_user(
            username="report-teacher",
            email="report.teacher@example.test",
            password="Teacher-Existing-Password-2036!",
        )
        teacher_user.groups.add(self.teacher_group)
        teacher_password_hash = teacher_user.password
        teacher = Teacher.objects.create(
            user=teacher_user,
            name="Report Teacher",
            email=teacher_user.email,
        )
        department = Department.objects.create(name="Chemistry Department")
        teacher.courses.add(
            Course.objects.create(name="Chemistry", department=department)
        )
        Student.objects.create(
            name="Unlinked Student",
            email="unlinked.report.student@example.test",
            department="Science",
            course="Biology",
        )

        unauthenticated = self.client.get(
            reverse("download_student_teacher_credentials")
        )
        self.assertEqual(unauthenticated.status_code, 302)

        regular_admin = User.objects.create_user(
            username="role-admin",
            email="role-admin@example.test",
            password="Role-Admin-Password-2036!",
        )
        regular_admin.groups.add(Group.objects.get(name="Admin"))
        self.client.force_login(regular_admin)
        self.assertEqual(
            self.client.get(reverse("student_teacher_credentials")).status_code,
            403,
        )
        for role_user in (student_user, teacher_user):
            self.client.force_login(role_user)
            self.assertEqual(
                self.client.get(
                    reverse("download_student_teacher_credentials")
                ).status_code,
                403,
            )

        self.client.force_login(self.admin)
        page = self.client.get(reverse("student_teacher_credentials"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Total students")
        self.assertContains(page, "Total teachers")
        self.assertTrue(
            self.client.get(reverse("admin_dashboard")).context[
                "can_manage_login_credentials"
            ]
        )

        student_password_hash = student_user.password
        generated = self.client.post(reverse("student_teacher_credentials"))
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(generated.context["summary"]["students_total"], 2)
        self.assertEqual(generated.context["summary"]["teachers_total"], 1)
        self.assertEqual(generated.context["summary"]["already_existed"], 2)
        self.assertEqual(generated.context["summary"]["manual_review"], 1)
        student_user.refresh_from_db()
        teacher_user.refresh_from_db()
        self.assertEqual(student_user.password, student_password_hash)
        self.assertEqual(teacher_user.password, teacher_password_hash)

        response = self.client.get(reverse("download_student_teacher_credentials"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="student_teacher_login_credentials.csv"',
        )
        self.assertEqual(response["Cache-Control"], "private, no-store, max-age=0")
        rows = list(
            csv.DictReader(response.content.decode("utf-8-sig").splitlines())
        )
        self.assertEqual(len(rows), 3)
        student_row = next(
            row
            for row in rows
            if row["Student ID or Teacher ID"] == "STU-REPORT-001"
        )
        teacher_row = next(row for row in rows if row["Role"] == "Teacher")
        self.assertEqual(student_row["Username"], "STU-REPORT-001")
        self.assertEqual(
            student_row["Initial password status"],
            "Changed or unknown",
        )
        self.assertEqual(student_row["Initial password"], "")
        self.assertIn("Chemistry", teacher_row["Course assignments"])
        self.assertEqual(teacher_row["Student ID or Teacher ID"], "")
        self.assertIn("no Teacher ID field", teacher_row["Notes"])

    def test_initial_password_is_encrypted_and_invalidated_after_change(self):
        student = Student.objects.create(
            student_id="STU-Vault-001",
            name="Vault Student",
            email="vault.student@example.test",
            department="Science",
            course="Biology",
        )
        credential = InitialLoginCredential.objects.get(user=student.user)
        self.assertNotEqual(credential.encrypted_password, "STU-Vault-001")
        self.assertTrue(credential.is_valid)

        self.client.force_login(self.admin)
        response = self.client.get(reverse("download_student_teacher_credentials"))
        rows = list(
            csv.DictReader(response.content.decode("utf-8-sig").splitlines())
        )
        student_row = next(
            row
            for row in rows
            if row["Student ID or Teacher ID"] == student.student_id
        )
        self.assertEqual(
            student_row["Initial password status"],
            "Known current initial password",
        )
        self.assertEqual(student_row["Initial password"], "STU-Vault-001")

        student.user.set_password("Changed-Vault-Password-2036!")
        student.user.save(update_fields=["password"])
        credential.refresh_from_db()
        self.assertFalse(credential.is_valid)
        response = self.client.get(reverse("download_student_teacher_credentials"))
        rows = list(
            csv.DictReader(response.content.decode("utf-8-sig").splitlines())
        )
        student_row = next(
            row
            for row in rows
            if row["Student ID or Teacher ID"] == student.student_id
        )
        self.assertEqual(
            student_row["Initial password status"],
            "Changed or unknown",
        )
        self.assertEqual(student_row["Initial password"], "")

    def test_teacher_missing_account_uses_email_based_identity(self):
        teacher = Teacher(
            name="New Report Teacher",
            email="new.teacher@example.test",
        )
        from students.account_services import ensure_teacher_account

        result = ensure_teacher_account(teacher)
        expected_username = (
            "teacher_new_teacher_"
            + hashlib.sha256(b"new.teacher@example.test").hexdigest()[:10]
        )
        self.assertTrue(result.created)
        self.assertEqual(teacher.user.username, expected_username)
        self.assertTrue(teacher.user.check_password(expected_username))
        self.assertTrue(teacher.user.groups.filter(name="Teacher").exists())
        self.assertFalse(teacher.user.is_staff or teacher.user.is_superuser)
        self.assertTrue(
            InitialLoginCredential.objects.filter(
                user=teacher.user,
                role="Teacher",
                is_valid=True,
            ).exists()
        )

    @override_settings(STUDENTMS_CREDENTIAL_ENCRYPTION_KEY="")
    def test_student_account_creation_still_works_without_report_key(self):
        student = Student.objects.create(
            student_id="STU-NO-VAULT-001",
            name="Unvaulted Student",
            email="unvaulted.student@example.test",
            department="Science",
            course="Biology",
        )

        self.assertIsNotNone(student.user_id)
        self.assertTrue(student.user.check_password("STU-NO-VAULT-001"))
        self.assertFalse(
            InitialLoginCredential.objects.filter(user=student.user).exists()
        )

    def test_report_marks_password_unknown_when_encryption_key_is_unavailable(self):
        student = Student.objects.create(
            student_id="STU-NO-REPORT-KEY",
            name="No Report Key Student",
            email="no.report.key.student@example.test",
            department="Science",
            course="Biology",
        )
        self.client.force_login(self.admin)

        with override_settings(STUDENTMS_CREDENTIAL_ENCRYPTION_KEY=""):
            response = self.client.get(
                reverse("download_student_teacher_credentials")
            )

        self.assertEqual(response.status_code, 200)
        rows = list(
            csv.DictReader(response.content.decode("utf-8-sig").splitlines())
        )
        student_row = next(
            row
            for row in rows
            if row["Student ID or Teacher ID"] == student.student_id
        )
        self.assertEqual(
            student_row["Initial password status"],
            "Changed or unknown",
        )
        self.assertEqual(student_row["Initial password"], "")

    def test_diagnostic_command_reports_counts_without_secrets_or_changes(self):
        student = Student.objects.create(
            student_id="STU-DIAG-001",
            name="Diagnostic Student",
            email="diagnostic.student@example.test",
            department="Science",
            course="Biology",
        )
        student_password_hash = student.user.password
        output = tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8")

        call_command("diagnose_login_accounts", stdout=output)

        output.seek(0)
        report = output.read()
        self.assertIn("Student profiles: 1", report)
        self.assertIn("Linked accounts: 1", report)
        self.assertIn("Missing links: 0", report)
        self.assertIn("Inactive linked accounts: 0", report)
        self.assertIn("Accounts without usable password hashes: 0", report)
        self.assertIn("Missing Student group membership: 0", report)
        self.assertNotIn(student_password_hash, report)
        student.refresh_from_db()
        self.assertEqual(student.user.password, student_password_hash)

    def test_password_reset_command_requires_confirmation(self):
        student = Student.objects.create(
            student_id="STU-NO-CONFIRM",
            name="No Confirm Student",
            email="no.confirm.student@example.test",
            department="Science",
            course="Biology",
        )
        student.user.set_password("Existing-Student-Password-2036!")
        student.user.save(update_fields=["password"])
        old_password_hash = student.user.password

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(BASE_DIR=Path(temp_dir)):
                with self.assertRaises(CommandError):
                    call_command("reset_student_teacher_passwords")
                backups = list(
                    Path(temp_dir).glob(
                        "db_backup_before_role_password_reset_*.sqlite3"
                    )
                )

        student.user.refresh_from_db()
        self.assertEqual(student.user.password, old_password_hash)
        self.assertFalse(student.user.check_password(student.student_id))
        self.assertEqual(backups, [])

    def test_explicit_password_reset_backs_up_then_resets_role_accounts(self):
        student = Student.objects.create(
            student_id="STU-RESET-001",
            name="Reset Student",
            email="reset.student@example.test",
            department="Science",
            course="Biology",
        )
        student.user.set_password("Old-Student-Password-2036!")
        student.user.save(update_fields=["password"])

        teacher_user = User.objects.create_user(
            username="preserved.teacher.username",
            email="reset.teacher@example.test",
            password="Old-Teacher-Password-2036!",
        )
        teacher_user.groups.add(self.teacher_group)
        teacher = Teacher.objects.create(
            user=teacher_user,
            name="Reset Teacher",
            email=teacher_user.email,
        )
        teacher_username = teacher_user.username
        backup_path = Path("db_backup_before_role_password_reset_test.sqlite3")
        with patch(
            "students.management.commands.reset_student_teacher_passwords."
            "Command._backup_database",
            return_value=backup_path,
        ) as backup:
            call_command(
                "reset_student_teacher_passwords",
                "--confirm",
                "RESET-STUDENT-TEACHER-PASSWORDS",
                stdout=tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8"),
            )

        backup.assert_called_once_with()
        student.refresh_from_db()
        teacher.refresh_from_db()
        teacher_user.refresh_from_db()
        self.assertTrue(student.user.check_password(student.student_id))
        self.assertTrue(student.must_change_password)
        self.assertTrue(
            InitialLoginCredential.objects.get(user=student.user).is_valid
        )
        expected_teacher_password = (
            "teacher_reset_teacher_"
            + hashlib.sha256(b"reset.teacher@example.test").hexdigest()[:10]
        )
        self.assertEqual(teacher_user.username, teacher_username)
        self.assertTrue(teacher_user.check_password(expected_teacher_password))
        self.assertTrue(
            InitialLoginCredential.objects.get(user=teacher_user).is_valid
        )
        self.assertTrue(teacher_user.groups.filter(name="Teacher").exists())
        self.assertFalse(teacher_user.is_staff or teacher_user.is_superuser)

    def test_management_command_writes_complete_six_column_csv(self):
        student = Student.objects.create(
            student_id="STU-CSV-001",
            name="CSV Student",
            email="csv.student@example.test",
            department="Science",
            course="Biology",
        )
        teacher_user = User.objects.create_user(
            username="csv-teacher",
            email="csv.teacher@example.test",
            password="Existing-Teacher-Password-2036!",
        )
        teacher_user.groups.add(self.teacher_group)
        Teacher.objects.create(
            user=teacher_user,
            name="CSV Teacher",
            email=teacher_user.email,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(BASE_DIR=Path(temp_dir)):
                call_command("generate_all_login_credentials")
            output_path = Path(temp_dir) / "all_login_credentials.csv"
            self.assertTrue(output_path.is_file())
            with output_path.open(encoding="utf-8-sig", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))

        self.assertEqual(
            list(rows[0]),
            ["Role", "ID", "Name", "Username", "Email", "Initial Password"],
        )
        self.assertEqual(len(rows), 2)
        student_row = next(row for row in rows if row["Role"] == "Student")
        teacher_row = next(row for row in rows if row["Role"] == "Teacher")
        self.assertEqual(student_row["ID"], student.student_id)
        self.assertEqual(student_row["Username"], student.student_id)
        self.assertEqual(student_row["Initial Password"], student.student_id)
        self.assertEqual(teacher_row["ID"], "")
        self.assertEqual(teacher_row["Username"], "csv-teacher")
        self.assertEqual(teacher_row["Initial Password"], "")


@override_settings(STUDENTMS_CREDENTIAL_ENCRYPTION_KEY=TEST_CREDENTIAL_KEY)
class SampleImportCommandTests(TestCase):
    sample_password = "Temporary-Demo-Password-2035!"

    def setUp(self):
        self.admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.data_dir = Path(self.temp_dir.name)
        self._write_csv(
            "students.csv",
            [
                "student_id", "name", "email", "phone", "department",
                "course", "semester", "section",
            ],
            [["STU1", "Demo Student", "sample.student@example.test",
              "9000000001", "Science", "Biology", "1", "A"]],
        )
        self._write_csv(
            "teachers.csv",
            [
                "teacher_id", "name", "email", "phone", "department", "courses",
            ],
            [["TCH1", "Demo Teacher", "sample.teacher@example.test",
              "9100000001", "Science", "Biology"]],
        )
        self._write_csv(
            "student_attendance.csv",
            ["student_id", "date", "status"],
            [["STU1", "2026-09-01", "Present"]],
        )
        self._write_csv(
            "student_marks.csv",
            [
                "student_id", "subject", "internal_marks", "assignment_marks",
                "practical_marks", "exam_marks",
            ],
            [["STU1", "Biology", "20", "16", "11", "53"]],
        )
        self._write_csv(
            "teacher_courses.csv",
            ["teacher_id", "course"],
            [["TCH1", "Biology"]],
        )
        self._write_csv(
            "teacher_attendance.csv",
            ["teacher_id", "date", "status"],
            [["TCH1", "2026-09-01", "Present"]],
        )

    def _write_csv(self, filename, headers, rows):
        with (self.data_dir / filename).open(
            "w", encoding="utf-8", newline=""
        ) as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            writer.writerows(rows)

    def _run_import(self, *extra_options, **command_kwargs):
        return call_command(
            "import_sample_data",
            "--data-dir",
            str(self.data_dir),
            *extra_options,
            **command_kwargs,
        )

    def test_dry_run_rolls_back_all_model_changes(self):
        initial_counts = (
            Student.objects.count(),
            Teacher.objects.count(),
            Attendance.objects.count(),
            Mark.objects.count(),
        )
        output = tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8")
        self._run_import("--dry-run", stdout=output)
        output.seek(0)
        summary = output.read()
        output.close()
        self.assertIn("DRY RUN (rolled back)", summary)
        self.assertIn("1 row(s) skipped", summary)
        self.assertEqual(
            (
                Student.objects.count(),
                Teacher.objects.count(),
                Attendance.objects.count(),
                Mark.objects.count(),
            ),
            initial_counts,
        )

    @override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
    def test_import_is_role_aware_and_idempotent(self):
        existing_admin = User.objects.create_superuser(
            username="preserved-admin",
            email="preserved-admin@example.test",
            password="admin-password-not-reset",
        )
        admin_password_hash = existing_admin.password
        with patch.dict(
            "os.environ",
            {"STUDENTMS_DEMO_PASSWORD": self.sample_password},
        ):
            first_output = tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8")
            self._run_import(stdout=first_output)
            first_output.close()

        student = Student.objects.get(email="sample.student@example.test")
        teacher = Teacher.objects.get(email="sample.teacher@example.test")
        student_user = student.user
        teacher_user = teacher.user
        self.assertEqual(student.student_id, "STU1")
        self.assertEqual(student_user.username, "STU1")
        self.assertTrue(student_user.check_password("STU1"))
        self.assertTrue(teacher_user.check_password(self.sample_password))
        self.assertTrue(student_user.groups.filter(name="Student").exists())
        self.assertTrue(teacher_user.groups.filter(name="Teacher").exists())
        self.assertFalse(student_user.is_staff or student_user.is_superuser)
        self.assertFalse(teacher_user.is_staff or teacher_user.is_superuser)
        self.assertEqual(teacher.courses.get().name, "Biology")
        self.assertEqual(student.semester.number, 1)
        self.assertEqual(student.section.name, "A")
        self.assertEqual(student.attendance.get().status, "Present")
        self.assertEqual(student.marks.get().total_marks, 100)

        self.assertTrue(
            self.client.login(
                username=student_user.username,
                password="STU1",
            )
        )
        self.assertRedirects(
            self.client.get(reverse("dashboard")),
            reverse("student_password_change"),
        )
        self.assertEqual(
            self.client.get(reverse("student_dashboard")).status_code,
            302,
        )
        response = self.client.post(
            reverse("student_password_change"),
            {
                "old_password": "STU1",
                "new_password1": "Different-Secure-Password-2036!",
                "new_password2": "Different-Secure-Password-2036!",
            },
        )
        self.assertRedirects(response, reverse("student_dashboard"))
        student_user.refresh_from_db()
        self.assertTrue(
            student_user.check_password("Different-Secure-Password-2036!")
        )
        self.client.logout()
        self.assertTrue(
            self.client.login(
                username=teacher_user.username,
                password=self.sample_password,
            )
        )
        self.assertRedirects(
            self.client.get(reverse("dashboard")),
            reverse("teacher_dashboard"),
        )

        second_output = tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8")
        self._run_import(stdout=second_output)
        second_output.seek(0)
        self.assertIn("Student profiles: created 0", second_output.read())
        second_output.close()
        self.assertEqual(Student.objects.filter(email=student.email).count(), 1)
        self.assertEqual(Attendance.objects.filter(student=student).count(), 1)
        self.assertEqual(Mark.objects.filter(student=student).count(), 1)
        existing_admin.refresh_from_db()
        self.assertTrue(existing_admin.is_superuser)
        self.assertEqual(existing_admin.password, admin_password_hash)

    def test_account_identity_conflict_rolls_back_and_preserves_existing_user(self):
        existing = User.objects.create_user(
            username="STU1",
            email="unrelated@example.test",
            password="existing-password",
        )
        existing.groups.add(self.admin_group)
        with self.assertRaises(CommandError):
            self._run_import("--dry-run")
        existing.refresh_from_db()
        self.assertEqual(existing.email, "unrelated@example.test")
        self.assertTrue(existing.groups.filter(name="Admin").exists())
        self.assertEqual(Student.objects.filter(email="sample.student@example.test").count(), 0)

    def test_bad_required_headers_fail_before_writing(self):
        self._write_csv(
            "student_marks.csv",
            ["student_id", "subject"],
            [["STU1", "Biology"]],
        )
        with self.assertRaises(CommandError):
            self._run_import("--dry-run")
        self.assertEqual(Department.objects.count(), 0)
        self.assertEqual(Student.objects.count(), 0)

    def test_conflicting_attendance_rolls_back_related_import_changes(self):
        student = Student.objects.create(
            name="Demo Student",
            email="sample.student@example.test",
            phone="9000000001",
            department="Science",
            course="Biology",
        )
        Attendance.objects.create(
            student=student,
            date=date(2026, 9, 1),
            status="Absent",
        )
        initial_user_count = User.objects.count()
        with self.assertRaises(CommandError):
            self._run_import()
        student.refresh_from_db()
        self.assertIsNone(student.user_id)
        self.assertIsNone(student.section_id)
        self.assertEqual(User.objects.count(), initial_user_count)
        self.assertEqual(Teacher.objects.count(), 0)
        self.assertEqual(Department.objects.count(), 0)
        self.assertEqual(
            Attendance.objects.get(student=student).status,
            "Absent",
        )
