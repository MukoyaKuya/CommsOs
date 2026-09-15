from django.contrib import admin

from accounts.models import Invitation, StaffProfile


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("membership", "department", "job_title", "rank")
    search_fields = ("membership__user__username", "membership__user__email", "job_title")


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "organization", "role", "expires_at", "accepted_at", "revoked_at")
    readonly_fields = ("token_hash", "accepted_at", "revoked_at", "created_at", "updated_at")
    search_fields = ("email",)

