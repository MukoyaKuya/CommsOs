from django import forms
from .models import Campaign, Observation, ContentItem


class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = [
            "name",
            "objective",
            "audience",
            "geographic_focus",
            "issue",
            "desired_outcome",
            "tone",
            "channels",
            "context",
            "starts_on",
            "ends_on",
        ]
        widgets = {
            "starts_on": forms.DateInput(attrs={"type": "date"}),
            "ends_on": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        data = super().clean()
        if data.get("starts_on") and data.get("ends_on") and data["ends_on"] < data["starts_on"]:
            self.add_error("ends_on", "End date must be on or after start date.")
        return data


class ObservationForm(forms.ModelForm):
    class Meta:
        model = Observation
        fields = [
            "channel",
            "format",
            "observed_on",
            "impressions",
            "engagements",
            "clicks",
        ]
        widgets = {"observed_on": forms.DateInput(attrs={"type": "date"})}

    def clean(self):
        data = super().clean()
        if data.get("impressions") is not None:
            for field in ("engagements", "clicks"):
                if data.get(field) is not None and data[field] > data["impressions"]:
                    self.add_error(field, f"{field.title()} cannot exceed impressions.")
        return data


class StrategyEditForm(forms.Form):
    objective = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), max_length=2000)
    audience = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), max_length=2000)
    key_message = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), max_length=2000)
    pillars = forms.CharField(
        help_text="One pillar per line", widget=forms.Textarea(attrs={"rows": 4})
    )

    def clean_pillars(self):
        pillars = [x.strip() for x in self.cleaned_data["pillars"].splitlines() if x.strip()]
        if not 1 <= len(pillars) <= 8:
            raise forms.ValidationError("Enter 1 to 8 pillars.")
        return pillars


class ContentItemForm(forms.ModelForm):
    class Meta:
        model = ContentItem
        fields = ["title", "channel", "format", "pillar", "planned_on", "draft"]
        widgets = {
            "planned_on": forms.DateInput(attrs={"type": "date"}),
            "draft": forms.Textarea(attrs={"rows": 8}),
        }
