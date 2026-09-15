import hashlib
import secrets
import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import Membership, Organization


class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class StaffProfile(TimestampedModel):
    membership = models.OneToOneField(
        Membership,
        on_delete=models.CASCADE,
        related_name="staff_profile",
    )
    department = models.CharField(max_length=160, blank=True)
    job_title = models.CharField(max_length=160, blank=True)
    job_group = models.CharField(max_length=100, blank=True)
    rank = models.CharField(max_length=100, blank=True)
    skills = models.JSONField(default=list, blank=True)
    job_description = models.TextField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    supervisor = models.ForeignKey(
        Membership,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supervised_profiles",
    )

    def clean(self):
        super().clean()
        if not self.supervisor_id:
            return
        if self.membership_id == self.supervisor_id:
            raise ValidationError({"supervisor": "A staff member cannot supervise themselves."})
        if self.membership.organization_id != self.supervisor.organization_id:
            raise ValidationError({"supervisor": "Supervisor must belong to the same organization."})

    def __str__(self):
        return self.membership.user.get_full_name() or self.membership.user.get_username()


class Invitation(TimestampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="staff_invitations",
    )
    email = models.EmailField()
    role = models.CharField(max_length=32, choices=Membership.Role.choices)
    profile_data = models.JSONField(default=dict, blank=True)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(
        Membership,
        on_delete=models.PROTECT,
        related_name="sent_invitations",
    )

    class Meta:
        indexes = [models.Index(fields=["organization", "email"])]

    @staticmethod
    def hash_token(raw_token):
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @classmethod
    def issue(cls, organization, email, role, invited_by, profile_data=None, expires_in=None):
        raw_token = secrets.token_urlsafe(32)
        normalized_email = email.strip()
        if "@" in normalized_email:
            local_part, domain = normalized_email.split("@", 1)
            normalized_email = f"{local_part}@{domain.lower()}"
        invitation = cls.objects.create(
            organization=organization,
            email=normalized_email,
            role=role,
            profile_data=profile_data or {},
            token_hash=cls.hash_token(raw_token),
            expires_at=timezone.now() + (expires_in or timedelta(hours=72)),
            invited_by=invited_by,
        )
        return invitation, raw_token

    def matches(self, raw_token):
        return secrets.compare_digest(self.token_hash, self.hash_token(raw_token))
