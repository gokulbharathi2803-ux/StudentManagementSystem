from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

from students.models import InitialLoginCredential


class CredentialEncryptionNotConfigured(Exception):
    """Raised when the separate credential-encryption key is unavailable."""


def _fernet(required=True):
    key = getattr(settings, "STUDENTMS_CREDENTIAL_ENCRYPTION_KEY", "")
    if not key:
        if not required:
            return None
        raise CredentialEncryptionNotConfigured(
            "Set STUDENTMS_CREDENTIAL_ENCRYPTION_KEY before creating accounts "
            "whose initial passwords must be included in the credentials report."
        )
    try:
        return Fernet(key.encode("ascii"))
    except (UnicodeEncodeError, ValueError) as exc:
        raise CredentialEncryptionNotConfigured(
            "STUDENTMS_CREDENTIAL_ENCRYPTION_KEY must be a valid Fernet key."
        ) from exc


def record_initial_password(user, role, password, replace=False):
    if not user.check_password(password):
        raise ValueError(
            "The password being recorded does not match the account password."
        )
    existing = InitialLoginCredential.objects.filter(user=user).first()
    if existing and not replace:
        return existing

    fernet = _fernet(required=replace)
    if fernet is None:
        return None
    encrypted_password = fernet.encrypt(password.encode("utf-8")).decode("ascii")
    if existing:
        existing.role = role
        existing.encrypted_password = encrypted_password
        existing.is_valid = True
        existing.save(
            update_fields=("role", "encrypted_password", "is_valid")
        )
        return existing
    return InitialLoginCredential.objects.create(
        user=user,
        role=role,
        encrypted_password=encrypted_password,
    )


def get_current_initial_password(user, role):
    credential = InitialLoginCredential.objects.filter(
        user=user,
        role=role,
        is_valid=True,
    ).first()
    if credential is None:
        return None

    try:
        password = _fernet().decrypt(
            credential.encrypted_password.encode("ascii")
        ).decode("utf-8")
    except (CredentialEncryptionNotConfigured, InvalidToken, UnicodeError):
        return None

    if user.check_password(password):
        return password

    InitialLoginCredential.objects.filter(pk=credential.pk).update(is_valid=False)
    return None


def invalidate_initial_password(user):
    InitialLoginCredential.objects.filter(user=user, is_valid=True).update(
        is_valid=False
    )
