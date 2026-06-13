from django.contrib import admin
from .models import (
    Appointment, QueueToken, PatientHistory,
    Payment, DoctorSchedule, Notification, DoctorReview, PaymentSettings, LabTest,
    LabTestCategory
)


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['patient', 'doctor', 'appointment_date', 'time_slot', 'status']
    list_filter = ['status', 'appointment_date']
    search_fields = ['patient__username', 'doctor__username']


@admin.register(QueueToken)
class QueueTokenAdmin(admin.ModelAdmin):
    list_display = ['token_number', 'appointment', 'estimated_wait_minutes', 'is_active']
    list_filter = ['is_active']


@admin.register(PatientHistory)
class PatientHistoryAdmin(admin.ModelAdmin):
    list_display = ['patient', 'doctor', 'visit_date', 'follow_up_required']
    list_filter = ['follow_up_required', 'visit_date']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['appointment', 'amount', 'method', 'status', 'created_at']
    list_filter = ['status', 'method']


@admin.register(DoctorSchedule)
class DoctorScheduleAdmin(admin.ModelAdmin):
    list_display = ['doctor', 'day_of_week', 'start_time', 'end_time', 'is_available']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'notification_type', 'title', 'is_read', 'email_sent', 'sms_sent', 'created_at']
    list_filter = ['notification_type', 'is_read', 'email_sent', 'sms_sent']
    search_fields = ['recipient__username', 'title', 'message']
    readonly_fields = ['created_at', 'email_sent_at', 'sms_sent_at']


@admin.register(DoctorReview)
class DoctorReviewAdmin(admin.ModelAdmin):
    list_display = ['patient', 'doctor', 'rating', 'created_at']
    list_filter = ['rating']


@admin.register(PaymentSettings)
class PaymentSettingsAdmin(admin.ModelAdmin):
    list_display = ['jazzcash_number', 'easypaisa_number', 'bank_name', 'updated_at']


@admin.register(LabTest)
class LabTestAdmin(admin.ModelAdmin):
    list_display = ['test_name', 'patient', 'doctor', 'status', 'ordered_date', 'result_date']
    list_filter = ['status', 'ordered_date']
    search_fields = ['test_name', 'patient__username']


@admin.register(LabTestCategory)
class LabTestCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'default_cost', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['name']
