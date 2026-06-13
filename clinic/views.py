from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum, Q, Avg
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from datetime import date, timedelta, datetime
import json

from .models import (
    Appointment, QueueToken, PatientHistory,
    Payment, DoctorSchedule, Notification, DoctorReview, PaymentSettings, LabTest
)
from .forms import (
    AppointmentForm, PatientHistoryForm,
    PaymentForm, DoctorScheduleForm, DoctorReviewForm
)
from accounts.models import User


def estimate_wait_time(doctor, appointment_date):
    """
    Estimate wait time based on doctor's queue.
    Uses 15 min per patient as average consultation time.
    Can be enhanced with actual timing data later.
    """
    avg_time = 15  # minutes per patient
    patients_ahead = QueueToken.objects.filter(
        appointment__doctor=doctor,
        appointment__appointment_date=appointment_date,
        is_active=True
    ).count()
    return patients_ahead * avg_time

@login_required
def book_appointment(request):
    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.patient = request.user
            appointment.save()
            messages.success(
                request,
                "Appointment booked successfully! Please proceed to payment."
            )
            return redirect('clinic:make_payment', appointment_id=appointment.id)
    else:
        form = AppointmentForm()

    doctors = User.objects.filter(role='DOCTOR').order_by('first_name')
    specializations = list(User.objects.filter(role='DOCTOR')
                          .exclude(specialization__isnull=True)
                          .exclude(specialization='')
                          .values_list('specialization', flat=True)
                          .distinct().order_by('specialization'))

    return render(request, 'clinic/book_appointment.html', {
        'form': form,
        'doctors': doctors,
        'specializations': specializations,
        'today': date.today(),
    })


@login_required
def my_appointments(request):
    appointments = Appointment.objects.filter(
        patient=request.user
    ).select_related('doctor', 'queue_token', 'payment')

    today = date.today()
    stats = {
        'total': appointments.count(),
        'completed': appointments.filter(status='COMPLETED').count(),
        'upcoming': appointments.filter(
            status='CONFIRMED', appointment_date__gte=today
        ).count(),
        'pending': appointments.filter(status='PENDING').count(),
    }

    return render(request, 'clinic/my_appointments.html', {
        'appointments': appointments,
        'stats': stats,
    })


@login_required
def get_doctor_slots(request):
    """AJAX endpoint: returns available 30-min time slots for a doctor on a given date."""
    doctor_id = request.GET.get('doctor_id')
    date_str = request.GET.get('date')

    if not doctor_id or not date_str:
        return JsonResponse({'error': 'Missing doctor_id or date'}, status=400)

    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)

    day_of_week = selected_date.weekday()

    # Get doctor's schedule for this day
    schedules = DoctorSchedule.objects.filter(
        doctor_id=doctor_id,
        day_of_week=day_of_week,
        is_available=True
    )

    if not schedules.exists():
        return JsonResponse({'slots': [], 'message': 'Doctor is not available on this day.'})

    # Generate 30-min slots from schedule
    slots = []
    for sched in schedules:
        current = datetime.combine(selected_date, sched.start_time)
        end = datetime.combine(selected_date, sched.end_time)
        while current < end:
            time_str = current.strftime('%H:%M')
            # Check if slot is already booked
            is_booked = Appointment.objects.filter(
                doctor_id=doctor_id,
                appointment_date=selected_date,
                time_slot=time_str,
                status__in=['PENDING', 'CONFIRMED']
            ).exists()
            slots.append({
                'time': time_str,
                'display': current.strftime('%I:%M %p'),
                'available': not is_booked
            })
            current += timedelta(minutes=30)

    return JsonResponse({'slots': slots})


@login_required
def cancel_appointment(request, appointment_id):
    appointment = get_object_or_404(
        Appointment, id=appointment_id, patient=request.user
    )
    if request.method == 'POST':
        if appointment.status in ('PENDING', 'CONFIRMED'):
            appointment.status = 'CANCELLED'
            appointment.save()
            messages.success(request, "Appointment cancelled.")
        else:
            messages.error(request, "This appointment cannot be cancelled.")
        return redirect('clinic:my_appointments')
    return render(request, 'clinic/cancel_appointment.html', {
        'appointment': appointment
    })


@login_required
def appointment_detail(request, appointment_id):
    """View full details of a specific appointment."""
    appointment = get_object_or_404(
        Appointment, id=appointment_id
    )

    # Role-based access: patient sees own, doctor sees own, admin/receptionist sees all
    if request.user.role == 'PATIENT' and appointment.patient != request.user:
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    if request.user.role == 'DOCTOR' and appointment.doctor != request.user:
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    # Get related data
    token = getattr(appointment, 'queue_token', None)
    payment = getattr(appointment, 'payment', None)
    medical_record = getattr(appointment, 'medical_record', None)
    review = getattr(appointment, 'review', None)

    return render(request, 'clinic/appointment_detail.html', {
        'appointment': appointment,
        'token': token,
        'payment': payment,
        'medical_record': medical_record,
        'review': review,
    })


@login_required
def reschedule_appointment(request, appointment_id):
    """Patient reschedules their appointment to a new date/time."""
    appointment = get_object_or_404(
        Appointment, id=appointment_id, patient=request.user
    )

    # Can only reschedule PENDING or CONFIRMED appointments
    if appointment.status not in ('PENDING', 'CONFIRMED'):
        messages.error(request, "This appointment cannot be rescheduled.")
        return redirect('clinic:my_appointments')

    if request.method == 'POST':
        new_date = request.POST.get('appointment_date')
        new_time = request.POST.get('time_slot')

        if not new_date or not new_time:
            messages.error(request, "Please select both date and time.")
            return redirect('clinic:reschedule_appointment', appointment_id=appointment.id)

        from datetime import date as date_type
        from datetime import datetime

        try:
            parsed_date = datetime.strptime(new_date, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect('clinic:reschedule_appointment', appointment_id=appointment.id)

        if parsed_date < date_type.today():
            messages.error(request, "Cannot reschedule to a past date.")
            return redirect('clinic:reschedule_appointment', appointment_id=appointment.id)

        # Check for conflicts (exclude current appointment)
        from django.db.models import Q
        conflict = Appointment.objects.filter(
            doctor=appointment.doctor,
            appointment_date=parsed_date,
            time_slot=new_time
        ).exclude(id=appointment.id).exists()

        if conflict:
            messages.error(
                request,
                "This time slot is already booked for the selected doctor. Please choose another."
            )
            return redirect('clinic:reschedule_appointment', appointment_id=appointment.id)

        # Update appointment
        appointment.appointment_date = parsed_date
        appointment.time_slot = new_time
        appointment.reason = request.POST.get('reason', appointment.reason)
        appointment.save()

        messages.success(
            request,
            f"Appointment rescheduled to {parsed_date.strftime('%B %d, %Y')} at {new_time}."
        )
        return redirect('clinic:my_appointments')

    return render(request, 'clinic/reschedule_appointment.html', {
        'appointment': appointment,
        'today': date.today(),
    })


# ─── Payment ───────────────────────────────────────────────────────

@login_required
def make_payment(request, appointment_id):
    appointment = get_object_or_404(
        Appointment, id=appointment_id, patient=request.user
    )

    if hasattr(appointment, 'payment'):
        return redirect('clinic:my_appointments')

    if request.method == 'POST':
        form = PaymentForm(request.POST, request.FILES)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.appointment = appointment

            payment.status = 'PENDING'
            msg = "Payment proof submitted! Your appointment will be confirmed after admin verification."

            payment.save()
            appointment.save()

            messages.success(request, msg)
            return redirect('clinic:my_appointments')
    else:
        initial = {'amount': appointment.doctor.consultation_fee}
        form = PaymentForm(initial=initial)

    return render(request, 'clinic/make_payment.html', {
        'form': form,
        'appointment': appointment,
        'payment_settings': PaymentSettings.objects.first(),
    })


@login_required
def payment_records(request):
    if request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    payments = Payment.objects.select_related(
        'appointment__patient', 'appointment__doctor'
    ).order_by('-created_at')

    # Pagination
    from django.core.paginator import Paginator
    page = request.GET.get('page', 1)
    paginator = Paginator(payments, 20)
    payments_page = paginator.get_page(page)

    stats = {
        'total_revenue': Payment.objects.filter(status='PAID').aggregate(
            Sum('amount'))['amount__sum'] or 0,
        'paid_count': Payment.objects.filter(status='PAID').count(),
        'pending_count': Payment.objects.filter(status='PENDING').count(),
        'failed_count': Payment.objects.filter(status='FAILED').count(),
        'refunded_count': Payment.objects.filter(status='REFUNDED').count(),
    }

    return render(request, 'clinic/payment_records.html', {
        'payments': payments_page,
        'page_obj': payments_page,
        **stats,
    })


@login_required
def verify_payment(request, payment_id):
    if request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    payment = get_object_or_404(Payment, id=payment_id)
    payment.status = 'PAID'
    payment.save()
    appointment = payment.appointment
    appointment.status = 'CONFIRMED'
    appointment.save()

    # Generate queue token on confirmation
    existing_count = QueueToken.objects.filter(
        appointment__doctor=appointment.doctor,
        appointment__appointment_date=appointment.appointment_date,
        is_active=True
    ).count()
    token_number = existing_count + 1
    estimated_wait = estimate_wait_time(
        appointment.doctor, appointment.appointment_date
    )
    QueueToken.objects.create(
        appointment=appointment,
        token_number=token_number,
        estimated_wait_minutes=estimated_wait
    )

    # Notify patient
    create_notification(
        recipient=appointment.patient,
        title="Appointment Confirmed",
        message=f"Your appointment with Dr. {appointment.doctor.get_full_name()} on {appointment.appointment_date.strftime('%B %d, %Y')} at {appointment.time_slot} has been confirmed. Your queue token is #{token_number}.",
        notification_type='APPOINTMENT_CONFIRMED',
    )

    messages.success(request, "Payment verified. Appointment confirmed.")
    return redirect('clinic:payment_records')


@login_required
def reject_payment(request, payment_id):
    if request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    payment = get_object_or_404(Payment, id=payment_id)
    payment.status = 'FAILED'
    payment.save()
    messages.warning(request, "Payment rejected.")
    return redirect('clinic:payment_records')


@login_required
def payment_receipt(request, payment_id):
    """Generate a PDF receipt for a payment."""
    payment = get_object_or_404(Payment, id=payment_id)

    # Access control: patient sees own, admin/receptionist sees all
    if request.user.role == 'PATIENT' and payment.appointment.patient != request.user:
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    if request.user.role == 'DOCTOR':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    if payment.status != 'PAID':
        messages.error(request, "Receipt is only available for paid payments.")
        return redirect('clinic:payment_records')

    # Generate PDF using weasyprint
    from weasyprint import HTML
    from django.template.loader import render_to_string
    from django.conf import settings

    context = {
        'payment': payment,
        'appointment': payment.appointment,
        'patient': payment.appointment.patient,
        'doctor': payment.appointment.doctor,
        'payment_settings': PaymentSettings.objects.first(),
    }

    html_string = render_to_string('clinic/receipt_pdf.html', context)
    html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
    pdf_file = html.write_pdf()

    response = HttpResponse(pdf_file, content_type='application/pdf')
    filename = f"Healthcare_Receipt_{payment.id}_{payment.appointment.patient.patient_id or 'N/A'}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def process_refund(request, payment_id):
    """Admin processes a refund for a paid payment."""
    if request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    payment = get_object_or_404(Payment, id=payment_id, status='PAID')

    if request.method == 'POST':
        refund_amount = request.POST.get('refund_amount', '')
        refund_reason = request.POST.get('refund_reason', '')

        try:
            refund_amount = float(refund_amount)
        except (ValueError, TypeError):
            messages.error(request, "Invalid refund amount.")
            return redirect('clinic:process_refund', payment_id=payment.id)

        if refund_amount <= 0 or refund_amount > float(payment.amount):
            messages.error(request, f"Refund amount must be between 0 and {payment.amount}.")
            return redirect('clinic:process_refund', payment_id=payment.id)

        # Process the refund
        payment.status = 'REFUNDED'
        payment.notes = f"{payment.notes or ''}\n\nREFUND PROCESSED:\nAmount: PKR {refund_amount}\nReason: {refund_reason}\nDate: {date.today()}"
        payment.save()

        # Cancel the associated appointment
        appointment = payment.appointment
        appointment.status = 'CANCELLED'
        appointment.save()

        # Deactivate queue token if exists
        if hasattr(appointment, 'queue_token'):
            appointment.queue_token.is_active = False
            appointment.queue_token.save()

        messages.success(
            request,
            f"Refund of PKR {refund_amount} processed for {payment.appointment.patient.get_full_name()}. "
            f"Appointment cancelled."
        )
        return redirect('clinic:payment_records')

    return render(request, 'clinic/process_refund.html', {
        'payment': payment,
    })


@login_required
def patient_payment_history(request):
    """Patient views their own complete payment history."""
    if request.user.role != 'PATIENT':
        # Admin/receptionist redirect to records
        return redirect('clinic:payment_records')

    payments = Payment.objects.filter(
        appointment__patient=request.user
    ).select_related('appointment__doctor').order_by('-created_at')

    # Stats
    stats = {
        'total_payments': payments.count(),
        'total_paid': payments.filter(status='PAID').aggregate(s=Sum('amount'))['s'] or 0,
        'total_pending': payments.filter(status='PENDING').aggregate(s=Sum('amount'))['s'] or 0,
        'total_refunded': payments.filter(status='REFUNDED').aggregate(s=Sum('amount'))['s'] or 0,
    }

    return render(request, 'clinic/patient_payment_history.html', {
        'payments': payments,
        'stats': stats,
    })



# ─── Queue Display (Public TV View) ────────────────────────────────

def queue_display(request):
    """Public-facing queue display for waiting room TV. No login required."""
    today = date.today()

    doctors = User.objects.filter(role='DOCTOR').order_by('first_name')
    doctors_queue = []
    now_serving = None

    for doctor in doctors:
        active_tokens = QueueToken.objects.filter(
            appointment__doctor=doctor,
            appointment__appointment_date=today,
            is_active=True
        ).select_related('appointment__patient').order_by('token_number')

        tokens_list = list(active_tokens)

        if tokens_list:
            current = tokens_list[0]
            if now_serving is None:
                now_serving = current

            waiting = tokens_list[1:] if len(tokens_list) > 1 else []

            queue_data = []
            for t in tokens_list:
                patient_name = t.appointment.patient.get_full_name() or t.appointment.patient.username
                initials = ''.join([n[0].upper() for n in patient_name.split()[:2]])
                queue_data.append({
                    'token_number': t.token_number,
                    'patient_initials': initials,
                })

            doctors_queue.append({
                'doctor': doctor,
                'active_token': current,
                'waiting_count': len(waiting),
                'queue': queue_data,
            })

    return render(request, 'clinic/queue_display.html', {
        'doctors_queue': doctors_queue,
        'now_serving': now_serving,
    })

@login_required
def manage_queue(request):
    if request.user.role == 'PATIENT':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    if request.user.role == 'DOCTOR':
        tokens = QueueToken.objects.filter(
            appointment__doctor=request.user,
            is_active=True
        ).select_related('appointment__patient').order_by('token_number')
    else:
        tokens = QueueToken.objects.filter(
            is_active=True
        ).select_related('appointment__patient', 'appointment__doctor').order_by('token_number')

    active_token = tokens.first()
    return render(request, 'clinic/manage_queue.html', {
        'tokens': tokens,
        'active_token': active_token,
    })


@login_required
def emergency_priority(request, token_id):
    """Mark a token as emergency — move to front of doctor's queue."""
    if request.user.role not in ('ADMIN', 'RECEPTIONIST', 'DOCTOR'):
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    token = get_object_or_404(QueueToken, id=token_id)

    # Doctors can only manage their own queue
    if request.user.role == 'DOCTOR' and token.appointment.doctor != request.user:
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    if not token.is_active:
        messages.error(request, "This token is no longer active.")
        return redirect('clinic:manage_queue')

    today = date.today()
    doctor = token.appointment.doctor

    # Get the minimum active token number for this doctor today
    min_token = QueueToken.objects.filter(
        appointment__doctor=doctor,
        appointment__appointment_date=today,
        is_active=True
    ).order_by('token_number').first()

    if min_token and token.id != min_token.id:
        # Move this token to the front by swapping numbers
        old_number = token.token_number
        new_number = min_token.token_number

        # Use a temporary number to avoid unique constraint issues
        temp_number = 999999
        token.token_number = temp_number
        token.save()

        min_token.token_number = old_number
        min_token.save()

        token.token_number = new_number
        token.save()

        messages.success(
            request,
            f"Token #{new_number} ({token.appointment.patient.get_full_name()}) moved to front of queue."
        )
    else:
        messages.info(request, "This token is already at the front of the queue.")

    return redirect('clinic:manage_queue')


@login_required
def call_next(request):
    """Mark current token as done and activate next."""
    if request.user.role != 'DOCTOR':
        return redirect('dashboard')
    current = QueueToken.objects.filter(
        appointment__doctor=request.user,
        is_active=True
    ).order_by('token_number').first()
    if current:
        current.is_active = False
        current.appointment.status = 'COMPLETED'
        current.appointment.save()
        current.save()
        # Notify next patient in queue
        next_token = QueueToken.objects.filter(
            appointment__doctor=request.user,
            is_active=True
        ).order_by('token_number').first()

        if next_token:
            create_notification(
                recipient=next_token.appointment.patient,
                title="Your Turn Next",
                message=f"Token #{next_token.token_number}, you are next in Dr. {request.user.get_full_name()}'s queue. Please proceed to the consultation room.",
                notification_type='QUEUE_YOUR_TURN',
            )

        messages.success(request, f"Token #{current.token_number} completed.")
    return redirect('clinic:manage_queue')


@login_required
def serve_patient(request, token_id):
    """Doctor marks patient as seen — admin will record details later."""
    if request.user.role != 'DOCTOR':
        return redirect('dashboard')
    token = get_object_or_404(
        QueueToken, id=token_id,
        appointment__doctor=request.user
    )
    appointment = token.appointment

    if request.method == 'POST':
        # Doctor just marks as seen — no medical data entry
        appointment.status = 'COMPLETED'
        appointment.save()
        token.is_active = False
        token.save()

        messages.success(
            request,
            f"Patient {appointment.patient.get_full_name()} marked as seen. Admin will record consultation details."
        )
        return redirect('clinic:manage_queue')

    # Show patient info for doctor to review before marking
    return render(request, 'clinic/serve_patient.html', {
        'appointment': appointment,
        'token': token,
    })


# ─── Patient History ───────────────────────────────────────────────

@login_required
def view_history(request):
    if request.user.role == 'PATIENT':
        records = PatientHistory.objects.filter(
            patient=request.user
        ).select_related('doctor')
    elif request.user.role == 'DOCTOR':
        records = PatientHistory.objects.filter(
            doctor=request.user
        ).select_related('patient')
    else:
        records = PatientHistory.objects.select_related('patient', 'doctor')

    from django.core.paginator import Paginator
    page = request.GET.get('page', 1)
    paginator = Paginator(records, 15)
    records_page = paginator.get_page(page)

    return render(request, 'clinic/view_history.html', {
        'records': records_page,
        'page_obj': records_page,
    })


# ─── Follow-ups ────────────────────────────────────────────────────

@login_required
def view_follow_ups(request):
    today = date.today()
    base_qs = PatientHistory.objects.filter(
        follow_up_required=True
    ).select_related('patient', 'doctor')

    if request.user.role == 'PATIENT':
        follow_ups = base_qs.filter(patient=request.user)
    elif request.user.role == 'DOCTOR':
        follow_ups = base_qs.filter(doctor=request.user)
    else:
        follow_ups = base_qs

    follow_ups = follow_ups.order_by('follow_up_date')
    return render(request, 'clinic/view_follow_ups.html', {
        'follow_ups': follow_ups,
        'today': today,
    })



# ─── Medical Record PDF ────────────────────────────────────────────

@login_required
def print_medical_record(request, history_id):
    """Generate a PDF medical record/prescription."""
    record = get_object_or_404(PatientHistory, id=history_id)

    # Access control
    if request.user.role == 'PATIENT' and record.patient != request.user:
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    from weasyprint import HTML
    from django.template.loader import render_to_string

    context = {
        'record': record,
        'patient': record.patient,
        'doctor': record.doctor,
        'appointment': record.appointment,
    }

    html_string = render_to_string('clinic/medical_record_pdf.html', context)
    html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
    pdf_file = html.write_pdf()

    response = HttpResponse(pdf_file, content_type='application/pdf')
    filename = f"Medical_Record_{record.patient.patient_id or 'N/A'}_{record.visit_date}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ─── Notifications Signal Helper ───────────────────────────────────

def create_notification(recipient, title, message, notification_type='GENERAL',
                        send_email=True, send_sms=True):
    """Helper to create a notification with email/SMS delivery."""
    from .notification_service import create_notification as _create
    return _create(recipient, title, message, notification_type=notification_type,
                   send_email=send_email, send_sms=send_sms)


# ─── Doctor Schedule (Admin) ───────────────────────────────────────

@login_required
def manage_doctors(request):
    if request.user.role != 'ADMIN':
        return redirect('dashboard')
    doctors = User.objects.filter(role='DOCTOR')
    return render(request, 'clinic/manage_doctors.html', {
        'doctors': doctors,
    })


@login_required
def doctor_schedule(request, doctor_id):
    if request.user.role != 'ADMIN':
        return redirect('dashboard')
    doctor = get_object_or_404(User, id=doctor_id, role='DOCTOR')
    schedules = DoctorSchedule.objects.filter(doctor=doctor)

    if request.method == 'POST':
        form = DoctorScheduleForm(request.POST)
        if form.is_valid():
            sched = form.save(commit=False)
            sched.doctor = doctor
            sched.save()
            messages.success(request, "Schedule updated.")
            return redirect('clinic:doctor_schedule', doctor_id=doctor.id)
    else:
        form = DoctorScheduleForm()

    return render(request, 'clinic/doctor_schedule.html', {
        'doctor': doctor,
        'schedules': schedules,
        'form': form,
    })


# ─── Notifications ─────────────────────────────────────────────────

@login_required
def notifications(request):
    notifs = Notification.objects.filter(recipient=request.user)
    unread = notifs.filter(is_read=False).count()
    return render(request, 'clinic/notifications.html', {
        'notifications': notifs,
        'unread_count': unread,
    })


@login_required
def mark_notification_read(request, notif_id):
    notif = get_object_or_404(
        Notification, id=notif_id, recipient=request.user
    )
    notif.is_read = True
    notif.save()
    return redirect('clinic:notifications')


# ─── Doctor Reviews ─────────────────────────────────────────────

@login_required
def review_doctor(request, appointment_id):
    if request.user.role != 'PATIENT':
        return redirect('dashboard')
    appointment = get_object_or_404(
        Appointment, id=appointment_id, patient=request.user, status='COMPLETED'
    )
    if hasattr(appointment, 'review'):
        messages.info(request, "You have already reviewed this appointment.")
        return redirect('clinic:my_appointments')

    if request.method == 'POST':
        form = DoctorReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.patient = request.user
            review.doctor = appointment.doctor
            review.appointment = appointment
            review.save()
            messages.success(request, "Thank you for your review!")
            return redirect('clinic:my_appointments')
    else:
        form = DoctorReviewForm()

    return render(request, 'clinic/review_doctor.html', {
        'form': form,
        'appointment': appointment,
    })


@login_required
def doctor_reviews(request, doctor_id):
    doctor = get_object_or_404(User, id=doctor_id, role='DOCTOR')
    reviews = DoctorReview.objects.filter(
        doctor=doctor
    ).select_related('patient').order_by('-created_at')
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']
    return render(request, 'clinic/doctor_reviews.html', {
        'doctor': doctor,
        'reviews': reviews,
        'avg_rating': avg_rating,
    })


def doctor_profile(request, doctor_id):
    """Public-facing doctor profile with reviews and schedule."""
    doctor = get_object_or_404(User, id=doctor_id, role='DOCTOR')
    reviews = DoctorReview.objects.filter(
        doctor=doctor
    ).select_related('patient').order_by('-created_at')
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']

    return render(request, 'clinic/doctor_profile.html', {
        'doctor': doctor,
        'reviews': reviews,
        'avg_rating': avg_rating,
    })


# ─── Patient Profile ────────────────────────────────────────────

@login_required
def patient_profile(request):
    user = request.user
    total_appointments = Appointment.objects.filter(patient=user).count()
    completed_appointments = Appointment.objects.filter(
        patient=user, status='COMPLETED'
    ).count()
    total_spent = Payment.objects.filter(
        appointment__patient=user, status='PAID'
    ).aggregate(total=Sum('amount'))['total'] or 0

    recent_history = PatientHistory.objects.filter(
        patient=user
    ).select_related('doctor')[:5]

    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.phone = request.POST.get('phone', user.phone)
        user.email = request.POST.get('email', user.email)
        user.gender = request.POST.get('gender') or None
        user.date_of_birth = request.POST.get('date_of_birth') or None
        user.address = request.POST.get('address', user.address)

        # Handle profile photo upload
        if request.FILES.get('profile_photo'):
            # Delete old photo if exists
            if user.profile_photo:
                import os
                from django.conf import settings
                old_path = os.path.join(settings.MEDIA_ROOT, user.profile_photo.name)
                if os.path.isfile(old_path):
                    os.remove(old_path)
            user.profile_photo = request.FILES['profile_photo']

        user.save()
        messages.success(request, "Profile updated successfully!")
        return redirect('clinic:patient_profile')

    return render(request, 'clinic/patient_profile.html', {
        'total_appointments': total_appointments,
        'completed_appointments': completed_appointments,
        'total_spent': total_spent,
        'recent_history': recent_history,
    })


@login_required
def remove_profile_photo(request):
    """Remove the user's profile photo."""
    if request.method == 'POST' or request.method == 'GET':
        user = request.user
        if user.profile_photo:
            import os
            from django.conf import settings
            old_path = os.path.join(settings.MEDIA_ROOT, user.profile_photo.name)
            if os.path.isfile(old_path):
                os.remove(old_path)
            user.profile_photo.delete(save=True)
            messages.success(request, "Profile photo removed.")
        return redirect('clinic:patient_profile')


# ─── Confirm Cash Payment (Admin) ──────────────────────────────

@login_required
def confirm_cash_payment(request, payment_id):
    """Admin confirms cash payment received at clinic."""
    if request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    payment = get_object_or_404(Payment, id=payment_id, method='CASH', status='PENDING')
    payment.status = 'PAID'
    payment.save()
    appointment = payment.appointment
    appointment.status = 'CONFIRMED'
    appointment.save()

    # Generate queue token
    existing_count = QueueToken.objects.filter(
        appointment__doctor=appointment.doctor,
        appointment__appointment_date=appointment.appointment_date,
        is_active=True
    ).count()
    token_number = existing_count + 1
    estimated_wait = estimate_wait_time(
        appointment.doctor, appointment.appointment_date
    )
    QueueToken.objects.create(
        appointment=appointment,
        token_number=token_number,
        estimated_wait_minutes=estimated_wait
    )

    # Notify patient
    create_notification(
        recipient=appointment.patient,
        title="Appointment Confirmed",
        message=f"Your walk-in appointment with Dr. {appointment.doctor.get_full_name()} has been confirmed. Queue token: #{token_number}.",
        notification_type='APPOINTMENT_CONFIRMED',
    )

    messages.success(request, f"Cash payment confirmed for {appointment.patient.get_full_name()}. Appointment is now confirmed.")
    return redirect('clinic:payment_records')


# ─── Payment Settings (Admin) ──────────────────────────────────

@login_required
def payment_settings(request):
    """Admin manages clinic payment account details."""
    if request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    settings_obj, _ = PaymentSettings.objects.get_or_create(id=1)

    if request.method == 'POST':
        settings_obj.jazzcash_number = request.POST.get('jazzcash_number', '')
        settings_obj.easypaisa_number = request.POST.get('easypaisa_number', '')
        settings_obj.bank_name = request.POST.get('bank_name', '')
        settings_obj.bank_account_title = request.POST.get('bank_account_title', '')
        settings_obj.bank_account_number = request.POST.get('bank_account_number', '')
        settings_obj.save()
        messages.success(request, "Payment settings updated successfully!")
        return redirect('clinic:payment_settings')

    return render(request, 'clinic/payment_settings.html', {
        'settings': settings_obj,
    })


# ─── Walk-in Booking (Admin Only) ──────────────────────────────

@login_required
def walkin_booking(request):
    """Admin books a walk-in patient with cash payment — instant confirm."""
    if request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    doctors = User.objects.filter(role='DOCTOR')
    existing_patients = User.objects.filter(role='PATIENT')

    if request.method == 'POST':
        patient_type = request.POST.get('patient_type', 'existing')

        if patient_type == 'new':
            # Quick register a new patient
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            phone = request.POST.get('phone', '').strip()
            email = request.POST.get('email', '').strip()

            if not first_name:
                messages.error(request, "Patient name is required.")
                return redirect('clinic:walkin_booking')

            # Generate a unique username
            base_username = (first_name + last_name).lower().replace(' ', '')[:15]
            username = base_username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = base_username + str(counter)
                counter += 1

            patient = User.objects.create_user(
                username=username,
                password='patient123',
                first_name=first_name,
                last_name=last_name,
                email=email or '',
                phone=phone or '',
                gender=request.POST.get('gender') or None,
                date_of_birth=request.POST.get('date_of_birth') or None,
                address=request.POST.get('address', ''),
                role='PATIENT',
            )
        else:
            patient_id = request.POST.get('patient_id')
            patient = get_object_or_404(User, id=patient_id, role='PATIENT')

        doctor_id = request.POST.get('doctor_id')
        doctor = get_object_or_404(User, id=doctor_id, role='DOCTOR')
        appt_date = request.POST.get('appointment_date')
        time_slot = request.POST.get('time_slot')
        reason = request.POST.get('reason', 'Walk-in consultation')

        # Create appointment — CONFIRMED immediately
        appointment = Appointment.objects.create(
            patient=patient,
            doctor=doctor,
            appointment_date=appt_date,
            time_slot=time_slot,
            status='CONFIRMED',
            reason=reason,
        )

        # Create cash payment — PAID immediately
        Payment.objects.create(
            appointment=appointment,
            amount=doctor.consultation_fee,
            method='CASH',
            status='PAID',
        )

        # Generate queue token
        existing_count = QueueToken.objects.filter(
            appointment__doctor=doctor,
            appointment__appointment_date=appt_date,
            is_active=True,
        ).count()
        token_number = existing_count + 1
        estimated_wait = estimate_wait_time(doctor, appt_date)
        QueueToken.objects.create(
            appointment=appointment,
            token_number=token_number,
            estimated_wait_minutes=estimated_wait,
        )

        pid = patient.patient_id or "N/A"
        messages.success(
            request,
            f"Walk-in booking confirmed! Patient ID: {pid} — {patient.get_full_name()} with Dr. {doctor.get_full_name()}. Queue Token #{token_number}."
        )
        return redirect('clinic:manage_queue')

    return render(request, 'clinic/walkin_booking.html', {
        'doctors': doctors,
        'existing_patients': existing_patients,
    })


# ─── Register Patient (Receptionist) ─────────────────────────────

@login_required
def register_patient(request):
    """Receptionist registers a new patient account."""
    if request.user.role not in ('ADMIN', 'RECEPTIONIST'):
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        gender = request.POST.get('gender') or None
        date_of_birth = request.POST.get('date_of_birth') or None
        address = request.POST.get('address', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        # Validation
        if not first_name or not last_name:
            messages.error(request, "First name and last name are required.")
            return redirect('clinic:register_patient')
        if not username:
            messages.error(request, "Username is required.")
            return redirect('clinic:register_patient')
        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' is already taken.")
            return redirect('clinic:register_patient')
        if not password1 or not password2:
            messages.error(request, "Password is required.")
            return redirect('clinic:register_patient')
        if password1 != password2:
            messages.error(request, "Passwords do not match.")
            return redirect('clinic:register_patient')

        patient = User.objects.create_user(
            username=username,
            password=password1,
            first_name=first_name,
            last_name=last_name,
            email=email or '',
            phone=phone or '',
            gender=gender,
            date_of_birth=date_of_birth,
            address=address,
            role='PATIENT',
        )

        pid = patient.patient_id or "N/A"
        messages.success(
            request,
            f"Patient registered successfully! ID: {pid} — {patient.get_full_name()}. Default login: {username}"
        )
        return redirect('clinic:patient_detail', patient_id=patient.patient_id)

    return render(request, 'clinic/register_patient.html')


# ─── Record Consultation (Admin) ────────────────────────────────

@login_required
def record_consultation(request, appointment_id):
    """Admin or Receptionist records consultation details."""
    if request.user.role not in ('ADMIN', 'RECEPTIONIST'):
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    appointment = get_object_or_404(Appointment, id=appointment_id)

    # Check if already recorded
    if hasattr(appointment, 'medical_record'):
        messages.info(request, "Consultation already recorded for this appointment.")
        return redirect('clinic:patient_detail', patient_id=appointment.patient.patient_id)

    if request.method == 'POST':
        form = PatientHistoryForm(request.POST, request.FILES)
        if form.is_valid():
            history = form.save(commit=False)
            history.patient = appointment.patient
            history.doctor = appointment.doctor
            history.appointment = appointment
            history.save()

            # Create LabTest records if tests were ordered
            lab_tests_text = form.cleaned_data.get('lab_tests_ordered', '').strip()
            if lab_tests_text:
                import re
                test_names = [t.strip() for t in re.split(r'[\n,]+', lab_tests_text) if t.strip()]
                for test_name in test_names:
                    LabTest.objects.create(
                        patient=appointment.patient,
                        doctor=appointment.doctor,
                        history=history,
                        test_name=test_name,
                        status='ORDERED',
                    )

            appointment.status = 'COMPLETED'
            appointment.save()

            pid = appointment.patient.patient_id or "N/A"
            msg = f"Consultation recorded for {appointment.patient.get_full_name()} (ID: {pid})."
            if lab_tests_text:
                msg += f" {len(test_names)} lab test(s) ordered."

            # Notify patient about follow-up
            if form.cleaned_data.get('follow_up_required'):
                follow_up_date = form.cleaned_data.get('follow_up_date')
                if follow_up_date:
                    create_notification(
                        recipient=appointment.patient,
                        title="Follow-Up Reminder",
                        message=f"Dr. {appointment.doctor.get_full_name()} has scheduled a follow-up for {follow_up_date.strftime('%B %d, %Y')}. Please book an appointment.",
                        notification_type='FOLLOW_UP_DUE',
                    )

            messages.success(request, msg)
            return redirect('clinic:patient_detail', patient_id=appointment.patient.patient_id)
    else:
        form = PatientHistoryForm()

    return render(request, 'clinic/record_consultation.html', {
        'form': form,
        'appointment': appointment,
    })


# ─── Lab Test Management (Admin) ──────────────────────────────

@login_required
def lab_tests(request):
    """Admin views and manages all lab tests."""
    if request.user.role == 'PATIENT':
        lab_tests = LabTest.objects.filter(patient=request.user).select_related('doctor')
    elif request.user.role == 'DOCTOR':
        # Doctors can only view (not edit) — read only
        lab_tests = LabTest.objects.filter(doctor=request.user).select_related('patient')
    else:
        # Admin sees all and can edit
        lab_tests = LabTest.objects.select_related('patient', 'doctor').all()

    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        lab_tests = lab_tests.filter(status=status_filter)

    # Pagination
    from django.core.paginator import Paginator
    page = request.GET.get('page', 1)
    paginator = Paginator(lab_tests, 20)
    lab_tests_page = paginator.get_page(page)

    # Stats (use full queryset for counts)
    all_tests = LabTest.objects.all()
    stats = {
        'total': all_tests.count(),
        'ordered': all_tests.filter(status='ORDERED').count(),
        'in_lab': all_tests.filter(status__in=['SAMPLE_COLLECTED', 'IN_LAB']).count(),
        'results': all_tests.filter(status='RESULTS_RECEIVED').count(),
    }

    return render(request, 'clinic/lab_tests.html', {
        'lab_tests': lab_tests_page,
        'page_obj': lab_tests_page,
        'stats': stats,
        'status_filter': status_filter,
        'status_choices': LabTest.STATUS_CHOICES,
    })


@login_required
def update_lab_test(request, test_id):
    """Admin or Receptionist updates lab test status and uploads results."""
    if request.user.role not in ('ADMIN', 'RECEPTIONIST'):
        messages.error(request, "Only admin or receptionist can update lab tests.")
        return redirect('clinic:lab_tests')

    lab_test = get_object_or_404(LabTest, id=test_id)

    if request.method == 'POST':
        lab_test.status = request.POST.get('status', lab_test.status)
        lab_test.results = request.POST.get('results', lab_test.results)
        lab_test.notes = request.POST.get('notes', lab_test.notes)

        if request.POST.get('result_date'):
            lab_test.result_date = request.POST.get('result_date')
        elif lab_test.status == 'RESULTS_RECEIVED' and not lab_test.result_date:
            from datetime import date
            lab_test.result_date = date.today()

        # Handle file upload
        if request.FILES.get('report_file'):
            lab_test.report_file = request.FILES['report_file']

        lab_test.save()

        # Notify patient when results are received
        if lab_test.status == 'RESULTS_RECEIVED':
            create_notification(
                recipient=lab_test.patient,
                title="Lab Results Ready",
                message=f"Your {lab_test.test_name} lab test results are now available. Please visit the clinic or check your online records.",
                notification_type='LAB_RESULTS_READY',
            )

        messages.success(request, f"Lab test '{lab_test.test_name}' updated.")
        return redirect('clinic:lab_tests')

    return render(request, 'clinic/update_lab_test.html', {
        'lab_test': lab_test,
        'status_choices': LabTest.STATUS_CHOICES,
    })


# ─── Patient Lookup (Search by ID) ─────────────────────────────

@login_required
def patient_lookup(request):
    """Search patient by patient_id, name, or phone."""
    query = request.GET.get('q', '').strip()
    patients = None
    selected_patient = None

    if query:
        from django.db.models import Q
        patients = User.objects.filter(
            role='PATIENT'
        ).filter(
            Q(patient_id__icontains=query) |
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(phone__icontains=query) |
            Q(email__icontains=query)
        ).distinct()[:20]

        # If exact match by patient_id, show full details
        if len(query) <= 12:
            try:
                selected_patient = User.objects.get(
                    role='PATIENT', patient_id__iexact=query
                )
            except User.DoesNotExist:
                pass

    return render(request, 'clinic/patient_lookup.html', {
        'query': query,
        'patients': patients,
        'selected_patient': selected_patient,
    })


@login_required
def patient_detail(request, patient_id):
    """Full patient profile with all history, visits, lab tests."""
    patient = get_object_or_404(User, patient_id=patient_id, role='PATIENT')

    # Get all data
    appointments = Appointment.objects.filter(
        patient=patient
    ).select_related('doctor', 'queue_token', 'payment').order_by('-appointment_date')[:20]

    history = PatientHistory.objects.filter(
        patient=patient
    ).select_related('doctor').order_by('-visit_date')[:20]

    lab_tests = LabTest.objects.filter(
        patient=patient
    ).select_related('doctor').order_by('-ordered_date')[:20]

    follow_ups = PatientHistory.objects.filter(
        patient=patient, follow_up_required=True
    ).order_by('follow_up_date')[:10]

    # Stats
    stats = {
        'total_visits': Appointment.objects.filter(patient=patient).count(),
        'completed': Appointment.objects.filter(patient=patient, status='COMPLETED').count(),
        'total_spent': Payment.objects.filter(
            appointment__patient=patient, status='PAID'
        ).aggregate(total=Sum('amount'))['total'] or 0,
        'lab_tests': LabTest.objects.filter(patient=patient).count(),
    }

    return render(request, 'clinic/patient_detail.html', {
        'p': patient,
        'appointments': appointments,
        'history': history,
        'lab_tests': lab_tests,
        'follow_ups': follow_ups,
        'stats': stats,
    })
