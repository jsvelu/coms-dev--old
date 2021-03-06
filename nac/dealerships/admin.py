import authtools.admin
from authtools.forms import UserChangeForm
from authtools.forms import UserCreationForm
from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.admin import widgets
from django.contrib.admin.widgets import AdminDateWidget
from django.urls import reverse
from django.utils.html import format_html
from django.utils.html import format_html_join
from django.utils.safestring import mark_safe

from caravans.models import Series

from .models import Dealership
from .models import DealershipUser
from .models import DealershipUserDealership


class DealershipInline(admin.TabularInline):
    model = DealershipUser.dealerships.through
    exclude = ('dealership',),
    # fk_name = "dealership_user_dealership_ref"
    #fk_name = DealershipUserDealership.dealership
    # readonly_fields = ('name', 'email',)
    extra = 0
    verbose_name = 'Dealership Relationship'
    verbose_name_plural = 'Dealership Relationships'
    # can_delete = False
    # show_change_link = False

    # def name(self, obj):
    #     return obj.dealershipuser.name
    # def email(self, obj): return obj.dealershipuser.email


class DealershipUserInline(admin.TabularInline):
    model = DealershipUserDealership
    exclude = ('dealershipuser',),
    # fk_name = DealershipUserDealership.dealership_user
    # fk_name = "dealership_user_dealership_ref"
    readonly_fields = ()
    extra = 0
    verbose_name = 'Dealership Staff Relationship'
    verbose_name_plural = 'Dealership Staff Relationships'
    # can_delete = True
    # show_change_link = True


class DealershipAdminForm(forms.ModelForm):
    series = forms.ModelMultipleChoiceField(
        Series.objects.all(),
        widget=widgets.FilteredSelectMultiple('Series', False),
        required=False,
    )

    egm_implementation_date = forms.DateField(widget=AdminDateWidget(attrs={'placeholder': settings.FORMAT_DATE_JS}), required=False, label=' eGM implementation date') # First character space of verbose_name is to prevent capitalisation

    def __init__(self, *args, **kwargs):
        super(DealershipAdminForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['series'] = self.instance.series_set.values_list('pk', flat=True)

    def save(self, *args, **kwargs):
        instance = super(DealershipAdminForm, self).save(*args, **kwargs)
        if instance.pk:
            instance.series_set.clear()
            instance.series_set.add(*self.cleaned_data['series'])
        return instance


class DealershipAdmin(admin.ModelAdmin):
    # fk_name = DealershipUserDealership.dealership_user_dealership_ref
    form = DealershipAdminForm
    list_display = ('name',)
    ordering = ('name',)
    fields = (
        'name',
        'logo',
        'address_edit',
        'phone1',
        'phone2',
        'egm_implementation_date',
        'series',
    )
    inlines = [
        DealershipUserInline,
    ]

    # the structure of Address table cause some 10,000-options select to be generated and renders the admin page unresponsive.
    # we're going to force a readonly here along with the option to EDIT (but not ADD NEW) the address.
    readonly_fields = ('address_edit',)
    def address_edit(self, instance):
        html = """<a class="related-widget-wrapper-link change-related" id="change_id_address" data-href-template="/admin/newage/address/__fk__/?_to_field=id&amp;_popup=1" title="" data-original-title="Change selected address" href="/admin/newage/address/%s/?_to_field=id&amp;_popup=1"><span class="glyphicon glyphicon-pencil" aria-hidden="true"></span></a> (Changes made in popup may not appear here until you refresh the page)"""\
               % instance.address_id
        return mark_safe("<span>%s %s</span>" % (instance.address, html))

    address_edit.short_description = "Address"


class DealershipUserChangeForm(UserChangeForm):
    class Meta(object):
        model = DealershipUser
        fields = UserChangeForm.Meta.fields   # (deliberately not ChangeForm)
        # if fields != forms.ALL_FIELDS: fields += ('dealerships',)
        fields = '__all__'


class DealershipUserCreationForm(UserCreationForm):
    class Meta(object):
        model = DealershipUser
        fields = UserCreationForm.Meta.fields + (
            # 'dealerships',
        )


class DealershipUserAdmin(authtools.admin.UserAdmin):
    # fk_name = dealership_user_dealership_ref
    COMMON_FIELDSET = (None, {
        'fields': (
            'is_active',
            # 'is_principal',
            # 'dealerships',
        ),
    })

    EDIT_FIELDSET = (None, {
        'fields': authtools.admin.DATE_FIELDS[1]['fields'],
    })

    fieldsets = (
        authtools.admin.BASE_FIELDS,
        # authtools.admin.ADVANCED_PERMISSION_FIELDS,
        COMMON_FIELDSET,
        EDIT_FIELDSET,
        # authtools.admin.DATE_FIELDS,
    )
    add_fieldsets = authtools.admin.UserAdmin.add_fieldsets + (COMMON_FIELDSET,)

    form = DealershipUserChangeForm
    add_form = DealershipUserCreationForm
    list_display = (
        'is_active',
        'email',
        'name',
        'groups_list',
        'dealerships_list',
        'hijack_link',
    )
    list_filter = (
        'is_active',
        'dealerships',
    )
    search_fields = ('email', 'name', 'dealerships__name')

    inlines = [
        DealershipInline,
    ]

    def get_queryset(self, request):
        """
        Preload related data to prevent query explosion
        """
        qs = super(DealershipUserAdmin, self).get_queryset(request)
        qs = qs.prefetch_related('dealershipuserdealership_set', 'dealershipuserdealership_set__dealership', 'groups')
        return qs

    @mark_safe
    def groups_list(self, user):
        groups = user.groups.all()
        return format_html_join(', ', '{}', ((group.name,) for group in groups))
    groups_list.allow_tags = True
    groups_list.short_description = 'User Type'

    @mark_safe
    def dealerships_list(self, user):
        output = []
        for dealership_user_dealership in user.dealershipuserdealership_set.all():
            dealership = dealership_user_dealership.dealership
            html = format_html('<li><a href="{}">{} {}</a></li>',
                reverse('admin:dealerships_dealership_change', args=(dealership.id,)),
                dealership.name,
                '(Principal)' if dealership_user_dealership.is_principal else '')
            output.append((dealership.name, html,))
        output.sort()

        return '<ul>' + '\n'.join(x[1] for x in output) + '</ul>'
    dealerships_list.allow_tags = True
    dealerships_list.short_description = 'Dealerships'

    @mark_safe
    def hijack_link(self, user):
        hijack_url = reverse('hijack:login_with_id', args=(user.id,))
        return format_html('<a href="{}" class="button transformGetToCsrfPost">Impersonate</a>', hijack_url)
    hijack_link.allow_tags = True
    hijack_link.short_description = ''


admin.site.register(Dealership, DealershipAdmin)
admin.site.register(DealershipUser, DealershipUserAdmin)
