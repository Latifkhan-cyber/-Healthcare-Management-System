from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import CustomUserCreationForm, StaffCreationForm
from .models import User
from django.db import models
from datetime import date


def home(request):
    return render(request, 'accounts/home.html')


def signup_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = 'PATIENT'
            user.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = CustomUserCreationForm()
    return render(request, 'accounts/signup.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            # Redirect to 'next' URL if provided, otherwise dashboard
            next_url = request.GET.get('next') or request.POST.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


def dashboard(request):
    if not request.user.is_authenticated:
        return redirect('login')

    context = {}
    today = date.today()

    if request.user.role == 'ADMIN':
        from clinic.models import Appointment, Payment, QueueToken, Notification
        context['doctors_count'] = User.objects.filter(role='DOCTOR').count()
        context['patients_count'] = User.objects.filter(role='PATIENT').count()
        context['appointments_today'] = Appointment.objects.filter(
            appointment_date=today
        ).count()
        context['total_revenue'] = Payment.objects.filter(
            status='PAID'
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        context['queue_length'] = QueueToken.objects.filter(is_active=True).count()
        context['pending_payments'] = Payment.objects.filter(status='PENDING').count()
        # Appointments needing consultation recording (doctor saw patient, admin hasn't recorded yet)
        from django.db.models import Q
        completed_no_history = Appointment.objects.filter(
            status='COMPLETED'
        ).exclude(
            medical_record__isnull=False
        ).select_related('patient', 'doctor').order_by('-appointment_date')[:5]
        context['pending_consultations'] = completed_no_history
        context['pending_consultations_count'] = Appointment.objects.filter(
            status='COMPLETED'
        ).exclude(medical_record__isnull=False).count()
        # Recent activity
        context['recent_appointments'] = Appointment.objects.select_related(
            'patient', 'doctor'
        ).order_by('-created_at')[:5]
        return render(request, 'accounts/admin_dashboard.html', context)

    elif request.user.role == 'DOCTOR':
        from clinic.models import Appointment, QueueToken
        context['pending_count'] = Appointment.objects.filter(
            doctor=request.user,
            appointment_date=today,
            status='CONFIRMED'
        ).count()
        context['completed_count'] = Appointment.objects.filter(
            doctor=request.user,
            appointment_date=today,
            status='COMPLETED'
        ).count()
        context['upcoming_appointments'] = Appointment.objects.filter(
            doctor=request.user,
            appointment_date=today,
            status='CONFIRMED'
        ).order_by('time_slot')[:5]
        context['active_token'] = QueueToken.objects.filter(
            appointment__doctor=request.user,
            is_active=True
        ).order_by('token_number').first()
        return render(request, 'accounts/doctor_dashboard.html', context)

    else:
        from clinic.models import Appointment, PatientHistory, QueueToken
        context['upcoming_count'] = Appointment.objects.filter(
            patient=request.user,
            status='CONFIRMED',
            appointment_date__gte=today
        ).count()
        context['prescriptions_count'] = PatientHistory.objects.filter(
            patient=request.user
        ).count()
        # Real queue position
        active_token = QueueToken.objects.filter(
            appointment__patient=request.user,
            is_active=True
        ).select_related('appointment').first()
        if active_token:
            context['queue_position'] = active_token.token_number
            context['wait_time'] = active_token.estimated_wait_minutes
            context['queue_doctor'] = active_token.appointment.doctor
        else:
            context['queue_position'] = None
            context['wait_time'] = None
        return render(request, 'accounts/patient_dashboard.html', context)


# ─── Staff Management (Admin) ─────────────────────────────────────

@login_required
def manage_staff(request):
    """Admin views and manages all staff accounts."""
    if request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    doctors = User.objects.filter(role='DOCTOR').order_by('first_name')
    receptionists = User.objects.filter(role='RECEPTIONIST').order_by('first_name')

    return render(request, 'accounts/manage_staff.html', {
        'doctors': doctors,
        'receptionists': receptionists,
    })


@login_required
def create_staff(request):
    """Admin creates a new staff account (Doctor or Receptionist)."""
    if request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    if request.method == 'POST':
        form = StaffCreationForm(request.POST)
        if form.is_valid():
            staff = form.save(commit=False)
            staff.save()
            messages.success(
                request,
                f"{staff.get_role_display()} account created for {staff.get_full_name() or staff.username}. "
                f"Default password: staff123"
            )
            return redirect('accounts:manage_staff')
    else:
        form = StaffCreationForm()

    return render(request, 'accounts/create_staff.html', {'form': form})


@login_required
def edit_staff(request, user_id):
    """Admin edits a staff account."""
    if request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    staff = get_object_or_404(User, id=user_id, role__in=['DOCTOR', 'RECEPTIONIST'])

    if request.method == 'POST':
        staff.first_name = request.POST.get('first_name', staff.first_name)
        staff.last_name = request.POST.get('last_name', staff.last_name)
        staff.email = request.POST.get('email', staff.email)
        staff.phone = request.POST.get('phone', staff.phone)
        staff.gender = request.POST.get('gender') or None
        staff.specialization = request.POST.get('specialization', staff.specialization)
        fee = request.POST.get('consultation_fee')
        if fee:
            staff.consultation_fee = fee
        staff.save()
        messages.success(request, f"Staff account updated for {staff.get_full_name() or staff.username}.")
        return redirect('accounts:manage_staff')

    return render(request, 'accounts/edit_staff.html', {'staff': staff})


@login_required
def delete_staff(request, user_id):
    """Admin deletes a staff account."""
    if request.user.role != 'ADMIN':
        messages.error(request, "Access denied.")
        return redirect('dashboard')

    staff = get_object_or_404(User, id=user_id, role__in=['DOCTOR', 'RECEPTIONIST'])

    if request.method == 'POST':
        name = staff.get_full_name() or staff.username
        staff.delete()
        messages.success(request, f"Staff account '{name}' has been deleted.")
        return redirect('accounts:manage_staff')

    return render(request, 'accounts/delete_staff.html', {'staff': staff})
