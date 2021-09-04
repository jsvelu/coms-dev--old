from allianceutils.views import export_permissions
from django.conf.urls import url

urlpatterns_permissionsexport = [
    url(r'group_permissions_export/', export_permissions.group_permissions, name='group_permissions'),
    url(r'permissions_export/', export_permissions.permissions, name='permissions'),
]
