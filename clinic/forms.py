from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, timedelta

from .models import Appointment, PatientHistory, Payment, DoctorSchedule, DoctorReview
from accounts.models import User


class AppointmentForm(forms.ModelForm):
    doctor = forms.ModelChoiceField(
        queryset=User.objects.filter(role='DOCTOR'),
        empty_label="Select a Doctor",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    appointment_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'min': date.today().isoformat(),
        })
    )
    time_slot = forms.TimeField(
        widget=forms.TimeInput(attrs={
            'type': 'time',
            'class': 'form-control',
        })
    )
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Describe your health concern (optional)'
        })
    )

    class Meta:
        model = Appointment
        fields = ['doctor', 'appointment_date', 'time_slot', 'reason']

    def clean_appointment_date(self):
        selected = self.cleaned_data['appointment_date']
        today = date.today()
        if selected < today:
            raise ValidationError(
                f"You cannot book for a past date. Please select {today.strftime('%B %d, %Y')} or later."
            )
        max_date = today + timedelta(days=365)
        if selected > max_date:
            raise ValidationError(
                f"You can only book up to 1 year in advance (max: {max_date.strftime('%B %d, %Y')})."
            )
        return selected

    def clean(self):
        cleaned = super().clean()
        doctor = cleaned.get('doctor')
        appt_date = cleaned.get('appointment_date')
        time_slot = cleaned.get('time_slot')

        if doctor and appt_date and time_slot:
            # Check for duplicate booking
            if Appointment.objects.filter(
                doctor=doctor,
                appointment_date=appt_date,
                time_slot=time_slot
            ).exists():
                raise ValidationError(
                    "This doctor is already booked for this time slot. "
                    "Please choose a different time."
                )
        return cleaned


class PatientHistoryForm(forms.ModelForm):
    class Meta:
        model = PatientHistory
        fields = [
            'blood_pressure', 'temperature', 'weight', 'pulse',
            'symptoms', 'diagnosis', 'prescription', 'notes',
            'lab_tests_ordered', 'follow_up_required', 'follow_up_date',
            'previous_records', 'previous_records_notes',
        ]
        widgets = {
            'blood_pressure': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g., 120/80'
            }),
            'temperature': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g., 98.6 F'
            }),
            'weight': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g., 70 kg'
            }),
            'pulse': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g., 72 bpm'
            }),
            'symptoms': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Patient reported symptoms'
            }),
            'diagnosis': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Enter diagnosis'
            }),
            'prescription': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Enter prescription details'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Additional notes (optional)'
            }),
            'lab_tests_ordered': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'e.g., CBC, Blood Sugar Fasting, X-Ray Chest (leave empty if none)'
            }),
            'follow_up_required': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'follow_up_date': forms.DateInput(attrs={
                'type': 'date', 'class': 'form-control'
            }),
            'previous_records': forms.FileInput(attrs={
                'class': 'form-control', 'accept': 'image/*,.pdf'
            }),
            'previous_records_notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'e.g., Dr. Ahmed, City Hospital, Jan 2025 — Prescription for diabetes'
            }),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('follow_up_required') and not cleaned.get('follow_up_date'):
            self.add_error('follow_up_date',
                           "Provide a follow-up date if follow-up is required.")
        return cleaned


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['amount', 'method', 'transaction_id', 'payment_proof']
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Amount in PKR'
            }),
            'method': forms.Select(attrs={'class': 'form-control'}),
            'transaction_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Transaction / Reference ID'
            }),
            'payment_proof': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show digital payment methods (no CASH)
        self.fields['method'].choices = [
            c for c in Payment.METHOD_CHOICES if c[0] != 'CASH'
        ]

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get('method')
        transaction_id = cleaned.get('transaction_id')
        payment_proof = cleaned.get('payment_proof')

        if method and method != 'CASH':
            if not transaction_id:
                self.add_error(
                    'transaction_id',
                    f'{dict(Payment.METHOD_CHOICES)[method]} requires a transaction ID / reference number.'
                )
            if not payment_proof:
                self.add_error(
                    'payment_proof',
                    f'{dict(Payment.METHOD_CHOICES)[method]} requires a payment screenshot / proof.'
                )
        return cleaned


class DoctorScheduleForm(forms.ModelForm):
    class Meta:
        model = DoctorSchedule
        fields = ['day_of_week', 'start_time', 'end_time', 'is_available']
        widgets = {
            'day_of_week': forms.Select(attrs={'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={
                'type': 'time', 'class': 'form-control'
            }),
            'end_time': forms.TimeInput(attrs={
                'type': 'time', 'class': 'form-control'
            }),
        }


class DoctorReviewForm(forms.ModelForm):
    class Meta:
        model = DoctorReview
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.Select(attrs={'class': 'form-control'}),
            'comment': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Share your experience (optional)'
            }),
        }
