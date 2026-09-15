from django import forms
from django.contrib.auth.forms import AuthenticationForm

from accounts.selectors import active_membership_for
from accounts.models import StaffProfile
from core.models import Membership


class InvitationForm(forms.Form):
    email = forms.EmailField()
    role = forms.ChoiceField(choices=Membership.Role.choices)
    department = forms.CharField(max_length=160, required=False)
    job_title = forms.CharField(max_length=160, required=False)
    job_group = forms.CharField(max_length=100, required=False)
    rank = forms.CharField(max_length=100, required=False)
    skills = forms.CharField(required=False, help_text="Comma-separated skills")

    def profile_data(self):
        return {
            "department": self.cleaned_data["department"],
            "job_title": self.cleaned_data["job_title"],
            "job_group": self.cleaned_data["job_group"],
            "rank": self.cleaned_data["rank"],
            "skills": [value.strip() for value in self.cleaned_data["skills"].split(",") if value.strip()],
        }


class InvitationAcceptanceForm(forms.Form):
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        data = super().clean()
        if data.get("password1") != data.get("password2"):
            self.add_error("password2", "Passwords do not match.")
        return data


class StaffProfileForm(forms.ModelForm):
    class Meta:
        model = StaffProfile
        fields = ["department", "job_title", "job_group", "rank", "skills", "job_description", "phone", "supervisor"]


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
