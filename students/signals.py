import logging

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from students.account_services import StudentAccountConflict, ensure_student_account
from students.credential_vault import (
    get_current_initial_password,
    invalidate_initial_password,
)
from students.models import InitialLoginCredential, Student


logger = logging.getLogger(__name__)
User = get_user_model()


@receiver(post_save, sender=Student)
def create_student_login_account(sender, instance, created, **kwargs):
    if not created:
        return
    if not instance.student_id:
        logger.warning(
            "Student profile %s was created without a Student ID; "
            "no login account was created.",
            instance.pk,
        )
        return

    try:
        ensure_student_account(instance)
    except StudentAccountConflict as exc:
        logger.error(
            "Could not create or link a login account for student profile %s: %s",
            instance.pk,
            exc,
        )


@receiver(pre_save, sender=User)
def remember_previous_user_password(sender, instance, **kwargs):
    if instance.pk:
        instance._studentms_previous_password = (
            sender._default_manager.filter(pk=instance.pk)
            .values_list("password", flat=True)
            .first()
        )
    else:
        instance._studentms_previous_password = None


@receiver(post_save, sender=User)
def update_student_initial_password_status(sender, instance, created, **kwargs):
    previous_password = getattr(instance, "_studentms_previous_password", None)
    if created or previous_password is None or previous_password == instance.password:
        return

    credential = InitialLoginCredential.objects.filter(
        user_id=instance.pk,
        is_valid=True,
    ).first()
    if credential is not None:
        role = credential.role
        if get_current_initial_password(instance, role) is None:
            invalidate_initial_password(instance)

    student = (
        Student.objects.filter(user_id=instance.pk)
        .only("pk", "student_id", "must_change_password")
        .first()
    )
    if student is None:
        return

    still_using_initial_password = bool(
        student.student_id and instance.check_password(student.student_id)
    )
    if student.must_change_password != still_using_initial_password:
        Student.objects.filter(pk=student.pk).update(
            must_change_password=still_using_initial_password
        )
