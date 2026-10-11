from dataclasses import dataclass
import hashlib
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction

from students.credential_vault import (
    CredentialEncryptionNotConfigured,
    record_initial_password,
)
from students.models import Student, Teacher

ROLE_GROUPS = {"admin", "teacher", "student"}
User = get_user_model()


class StudentAccountConflict(Exception):
    """Raised when an existing identity cannot safely be linked to a student."""


@dataclass(frozen=True)
class StudentAccountResult:
    user: object
    created: bool = False
    linked: bool = False
    renamed: bool = False
    group_added: bool = False


def _single_match(queryset, description):
    matches = list(queryset[:2])
    if len(matches) > 1:
        raise StudentAccountConflict(
            f"More than one account matches {description}; review it manually."
        )
    return matches[0] if matches else None


def _student_group():
    group = _single_match(
        Group.objects.filter(name__iexact="Student"),
        "the Student role group",
    )
    return group or Group.objects.create(name="Student")


def _validate_student_account(user, student):
    if user.is_superuser or user.is_staff:
        raise StudentAccountConflict(
            f"Account {user.username!r} is staff or a superuser; it was not changed."
        )
    email_matches = (
        (user.email or "").strip().casefold()
        == student.email.strip().casefold()
    )
    username_matches = user.username.casefold() == student.student_id.casefold()
    if not email_matches and not username_matches:
        raise StudentAccountConflict(
            f"Account {user.username!r} does not match the student's email; "
            "it was not linked."
        )
    role_memberships = {
        name.casefold()
        for name in user.groups.values_list("name", flat=True)
        if name.casefold() in ROLE_GROUPS
    }
    if role_memberships - {"student"}:
        raise StudentAccountConflict(
            f"Account {user.username!r} has another privileged role; "
            "it was not changed."
        )


@transaction.atomic
def ensure_student_account(student):
    student_id = (student.student_id or "").strip()
    if not student_id:
        raise StudentAccountConflict(
            f"Student profile {student.pk} has no Student ID; assign one before "
            "creating its account."
        )

    username_matches = list(
        User._default_manager.filter(username__iexact=student_id)[:2]
    )
    if len(username_matches) > 1:
        raise StudentAccountConflict(
            f"Student ID {student_id!r} matches multiple usernames."
        )

    created = False
    linked = False
    renamed = False
    group_added = False

    if student.user_id:
        user = student.user
        _validate_student_account(user, student)
        if username_matches and username_matches[0].pk != user.pk:
            raise StudentAccountConflict(
                f"Username {student_id!r} already belongs to another account."
            )
        email_matches = list(
            User._default_manager.filter(email__iexact=student.email)
            .exclude(pk=user.pk)[:2]
        )
        if email_matches:
            raise StudentAccountConflict(
                f"Email {student.email!r} already belongs to another account."
            )
        changed_fields = []
        if user.username != student_id:
            user.username = student_id
            changed_fields.append("username")
            renamed = True
        if user.email != student.email:
            user.email = student.email
            changed_fields.append("email")
        if changed_fields:
            user.save(update_fields=changed_fields)
    else:
        email_matches = list(
            User._default_manager.filter(email__iexact=student.email)[:2]
        )
        if len(email_matches) > 1:
            raise StudentAccountConflict(
                f"Student email {student.email!r} matches multiple accounts."
            )
        by_username = username_matches[0] if username_matches else None
        by_email = email_matches[0] if email_matches else None

        if by_username or by_email:
            if by_username is None or by_email is None or by_username.pk != by_email.pk:
                raise StudentAccountConflict(
                    f"Student ID {student_id!r} or email {student.email!r} "
                    "belongs to an account that cannot be verified; no account "
                    "was linked."
                )
            user = by_username
            _validate_student_account(user, student)
            linked = True
        else:
            user = User._default_manager.create_user(
                username=student_id,
                email=student.email,
                password=student_id,
                is_active=True,
            )
            record_initial_password(user, "Student", student_id)
            created = True

    student_group = _student_group()
    if not user.groups.filter(pk=student_group.pk).exists():
        user.groups.add(student_group)
        group_added = True

    if student.user_id != user.pk:
        student.user = user
        update_fields = ["user"]
        if created:
            student.must_change_password = True
            update_fields.append("must_change_password")
        student.save(update_fields=update_fields)
        linked = True
    elif created:
        student.must_change_password = True
        student.save(update_fields=["must_change_password"])
        linked = True

    return StudentAccountResult(
        user=user,
        created=created,
        linked=linked,
        renamed=renamed,
        group_added=group_added,
    )


def _teacher_login_identity(email):
    local_part = email.split("@", 1)[0].casefold()
    safe_part = re.sub(r"[^a-z0-9]+", "_", local_part).strip("_") or "teacher"
    suffix = hashlib.sha256(email.strip().casefold().encode("utf-8")).hexdigest()[:10]
    username = f"teacher_{safe_part[:60]}_{suffix}"
    return username, username


@transaction.atomic
def ensure_teacher_account(teacher):
    username, initial_password = _teacher_login_identity(teacher.email)
    created = False
    linked = False
    group_added = False

    if teacher.user_id:
        user = teacher.user
        if user.is_staff or user.is_superuser:
            raise StudentAccountConflict(
                f"Teacher {teacher.email!r} is linked to a staff/admin account."
            )
        if (user.email or "").strip().casefold() != teacher.email.strip().casefold():
            raise StudentAccountConflict(
                f"Teacher {teacher.email!r} is linked to an account with a "
                "different email."
            )
        memberships = {
            name.casefold()
            for name in user.groups.values_list("name", flat=True)
            if name.casefold() in ROLE_GROUPS
        }
        if memberships - {"teacher"}:
            raise StudentAccountConflict(
                f"Teacher account {user.username!r} has a conflicting role."
            )
    else:
        username_user = _single_match(
            User._default_manager.filter(username__iexact=username),
            f"teacher username {username!r}",
        )
        email_user = _single_match(
            User._default_manager.filter(email__iexact=teacher.email),
            f"teacher email {teacher.email!r}",
        )
        if username_user or email_user:
            if username_user is None or email_user is None or username_user.pk != email_user.pk:
                raise StudentAccountConflict(
                    f"Teacher identity {teacher.email!r} conflicts with an "
                    "existing account; it was not linked."
                )
            user = username_user
            if user.is_staff or user.is_superuser:
                raise StudentAccountConflict(
                    f"Teacher {teacher.email!r} matches a staff/admin account."
                )
            memberships = {
                name.casefold()
                for name in user.groups.values_list("name", flat=True)
                if name.casefold() in ROLE_GROUPS
            }
            if memberships - {"teacher"}:
                raise StudentAccountConflict(
                    f"Teacher account {user.username!r} has a conflicting role."
                )
            linked = True
        else:
            user = User._default_manager.create_user(
                username=username,
                email=teacher.email,
                password=initial_password,
                is_active=True,
            )
            record_initial_password(user, "Teacher", initial_password)
            created = True

    teacher_group = _single_match(
        Group.objects.filter(name__iexact="Teacher"),
        "the Teacher role group",
    )
    if teacher_group is None:
        teacher_group = Group.objects.create(name="Teacher")
    if not user.groups.filter(pk=teacher_group.pk).exists():
        user.groups.add(teacher_group)
        group_added = True

    if teacher.user_id != user.pk:
        teacher.user = user
        if teacher.pk:
            teacher.save(update_fields=["user"])
        else:
            teacher.save()
        linked = True

    return StudentAccountResult(
        user=user,
        created=created,
        linked=linked,
        group_added=group_added,
    )


def ensure_missing_accounts():
    summary = {
        "students_total": 0,
        "teachers_total": 0,
        "created": 0,
        "already_existed": 0,
        "manual_review": 0,
        "conflicts": [],
    }
    student_ids = set()
    for student in Student.objects.select_related("user").order_by("pk"):
        summary["students_total"] += 1
        student_id = (student.student_id or "").strip()
        if student_id and student_id.casefold() in student_ids:
            summary["manual_review"] += 1
            summary["conflicts"].append(
                f"Student {student.email}: duplicate Student ID {student_id!r}."
            )
            continue
        if student_id:
            student_ids.add(student_id.casefold())
        try:
            result = ensure_student_account(student)
        except StudentAccountConflict as exc:
            summary["manual_review"] += 1
            summary["conflicts"].append(f"Student {student.email}: {exc}")
            continue
        except CredentialEncryptionNotConfigured as exc:
            summary["manual_review"] += 1
            summary["conflicts"].append(f"Student {student.email}: {exc}")
            continue
        summary["created" if result.created else "already_existed"] += 1

    for teacher in Teacher.objects.select_related("user").prefetch_related(
        "courses"
    ).order_by("pk"):
        summary["teachers_total"] += 1
        try:
            result = ensure_teacher_account(teacher)
        except StudentAccountConflict as exc:
            summary["manual_review"] += 1
            summary["conflicts"].append(f"Teacher {teacher.email}: {exc}")
            continue
        except CredentialEncryptionNotConfigured as exc:
            summary["manual_review"] += 1
            summary["conflicts"].append(f"Teacher {teacher.email}: {exc}")
            continue
        summary["created" if result.created else "already_existed"] += 1

    return summary
