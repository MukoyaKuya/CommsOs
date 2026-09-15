from django.urls import path

from accounts import views


urlpatterns = [
    path("team/", views.team_directory, name="team_directory"),
    path("invitations/new/", views.invitation_create, name="invitation_create"),
    path("invitations/<str:token>/accept/", views.invitation_accept, name="invitation_accept"),
    path("invitations/<uuid:pk>/revoke/", views.invitation_revoke, name="invitation_revoke"),
    path("team/<uuid:pk>/edit/", views.staff_profile_edit, name="staff_profile_edit"),
    path("team/<uuid:pk>/deactivate/", views.member_deactivate, name="member_deactivate"),
    path("team/<uuid:pk>/reactivate/", views.member_reactivate, name="member_reactivate"),
]
