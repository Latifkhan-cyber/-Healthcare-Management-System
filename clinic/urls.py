from django.urls import path
from . import views

app_name = 'clinic'

urlpatterns = [
    # Appointments
    path('book/', views.book_appointment, name='book_appointment'),
    path('book/slots/', views.get_doctor_slots, name='get_doctor_slots'),
    path('my-appointments/', views.my_appointments, name='my_appointments'),
    path('appointment/<int:appointment_id>/cancel/', views.cancel_appointment, name='cancel_appointment'),
    path('appointment/<int:appointment_id>/reschedule/', views.reschedule_appointment, name='reschedule_appointment'),
    path('appointment/<int:appointment_id>/', views.appointment_detail, name='appointment_detail'),

    # Payments
    path('payment/<int:appointment_id>/', views.make_payment, name='make_payment'),
    path('admin/payments/', views.payment_records, name='payment_records'),
    path('admin/payments/verify/<int:payment_id>/', views.verify_payment, name='verify_payment'),
    path('admin/payments/reject/<int:payment_id>/', views.reject_payment, name='reject_payment'),
    path('admin/payments/receipt/<int:payment_id>/', views.payment_receipt, name='payment_receipt'),
    path('admin/payments/refund/<int:payment_id>/', views.process_refund, name='process_refund'),
    path('my-payments/', views.patient_payment_history, name='patient_payment_history'),

    # Queue
    path('queue/', views.manage_queue, name='manage_queue'),
    path('queue/call-next/', views.call_next, name='call_next'),
    path('queue/serve/<int:token_id>/', views.serve_patient, name='serve_patient'),
    path('queue/display/', views.queue_display, name='queue_display'),
    path('queue/emergency/<int:token_id>/', views.emergency_priority, name='emergency_priority'),

    # Medical Records
    path('history/', views.view_history, name='view_history'),
    path('history/<int:history_id>/print/', views.print_medical_record, name='print_medical_record'),
    path('follow-ups/', views.view_follow_ups, name='view_follow_ups'),

    # Doctor Management (Admin)
    path('admin/doctors/', views.manage_doctors, name='manage_doctors'),
    path('admin/doctors/<int:doctor_id>/schedule/', views.doctor_schedule, name='doctor_schedule'),

    # Notifications
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:notif_id>/read/', views.mark_notification_read, name='mark_notification_read'),

    # Doctor Reviews
    path('review/<int:appointment_id>/', views.review_doctor, name='review_doctor'),
    path('doctors/<int:doctor_id>/reviews/', views.doctor_reviews, name='doctor_reviews'),
    path('doctors/<int:doctor_id>/', views.doctor_profile, name='doctor_profile'),

    # Patient Profile
    path('profile/', views.patient_profile, name='patient_profile'),
    path('profile/photo/remove/', views.remove_profile_photo, name='remove_profile_photo'),

    # Payment Settings (Admin)
    path('admin/payment-settings/', views.payment_settings, name='payment_settings'),
    path('admin/payments/confirm-cash/<int:payment_id>/', views.confirm_cash_payment, name='confirm_cash_payment'),

    # Walk-in Booking (Admin)
    path('admin/walkin-booking/', views.walkin_booking, name='walkin_booking'),

    # Lab Tests
    path('lab-tests/', views.lab_tests, name='lab_tests'),
    path('lab-tests/<int:test_id>/update/', views.update_lab_test, name='update_lab_test'),

    # Patient Lookup
    path('patient-lookup/', views.patient_lookup, name='patient_lookup'),
    path('patient/register/', views.register_patient, name='register_patient'),
    path('patient/<str:patient_id>/', views.patient_detail, name='patient_detail'),

    # Record Consultation (Admin)
    path('admin/record-consultation/<int:appointment_id>/', views.record_consultation, name='record_consultation'),
]
