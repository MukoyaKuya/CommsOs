from django import forms
from django.contrib.auth.forms import AuthenticationForm

from accounts.selectors import active_membership_for
from core.models import Membership


class RoleLoginForm(AuthenticationForm):
    role = forms.ChoiceField(choices=Membership.Role.choices)
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Unable to sign in with those details.",
        "inactive": "Unable to sign in with those details.",
    }

    def clean(self):
        cleaned_data = super().clean()
        membership = active_membership_for(self.get_user())
        if membership is None or membership.role != cleaned_data.get("role"):
            raise forms.ValidationError(self.error_messages["invalid_login"], code="invalid_login")
        return cleaned_data

