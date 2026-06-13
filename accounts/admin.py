from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ['username', 'patient_id', 'email', 'role', 'gender', 'phone', 'is_staff']
    list_filter = ['role', 'gender']
    search_fields = ['username', 'patient_id', 'email', 'first_name', 'last_name', 'phone']
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('role', 'patient_id', 'phone', 'gender', 'date_of_birth', 'address', 'specialization', 'consultation_fee')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('role', 'phone', 'gender', 'date_of_birth', 'address', 'specialization', 'consultation_fee')}),
    )
    readonly_fields = ['patient_id']


admin.site.register(User, CustomUserAdmin)
