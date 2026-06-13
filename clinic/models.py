from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone


class DoctorSchedule(models.Model):
    """Weekly schedule for each doctor."""
    DAY_CHOICES = (
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='schedules'
    )
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_available = models.BooleanField(default=True)

    class Meta:
        unique_together = ('doctor', 'day_of_week')
        ordering = ['day_of_week']

    def __str__(self):
        return f"Dr. {self.doctor.username} - {self.get_day_of_week_display()} ({self.start_time}-{self.end_time})"


class Appointment(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('CANCELLED', 'Cancelled'),
        ('COMPLETED', 'Completed'),
        ('NO_SHOW', 'No Show'),
    )

    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='appointments'
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='doctor_appointments'
    )
    appointment_date = models.DateField()
    time_slot = models.TimeField()
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='PENDING'
    )
    reason = models.TextField(
        blank=True,
        help_text="Brief description of the health concern"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-appointment_date', '-time_slot']
        constraints = [
            models.UniqueConstraint(
                fields=['doctor', 'appointment_date', 'time_slot'],
                name='unique_doctor_timeslot'
            )
        ]

    def __str__(self):
        return f"{self.patient.username} -> Dr. {self.doctor.username} on {self.appointment_date} at {self.time_slot}"


class QueueToken(models.Model):
    """Queue token generated when appointment is confirmed."""
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name='queue_token'
    )
    token_number = models.PositiveIntegerField()
    estimated_wait_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Estimated wait in minutes"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['token_number']

    def __str__(self):
        return f"Token #{self.token_number} - {self.appointment.patient.username}"


class PatientHistory(models.Model):
    """Medical record created after a consultation."""
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='medical_history'
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='records_created'
    )
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='medical_record'
    )
    visit_date = models.DateField(auto_now_add=True)

    # Vitals
    blood_pressure = models.CharField(
        max_length=20, blank=True, null=True,
        help_text="e.g., 120/80"
    )
    temperature = models.CharField(
        max_length=10, blank=True, null=True,
        help_text="e.g., 98.6 F"
    )
    weight = models.CharField(
        max_length=10, blank=True, null=True,
        help_text="e.g., 70 kg"
    )
    pulse = models.CharField(
        max_length=10, blank=True, null=True,
        help_text="e.g., 72 bpm"
    )

    # Medical
    symptoms = models.TextField(
        blank=True,
        help_text="Patient's reported symptoms"
    )
    diagnosis = models.TextField()
    prescription = models.TextField()
    notes = models.TextField(blank=True)
    lab_tests_ordered = models.TextField(
        blank=True,
        help_text="Lab tests ordered (e.g., CBC, Blood Sugar, X-Ray)"
    )
    follow_up_required = models.BooleanField(default=False)
    follow_up_date = models.DateField(blank=True, null=True)

    # Previous medical records (upload from other doctors/hospitals)
    previous_records = models.FileField(
        upload_to='previous_records/%Y/%m/',
        blank=True, null=True,
        help_text="Upload previous doctor prescriptions, reports, or medical documents"
    )
    previous_records_notes = models.TextField(
        blank=True,
        help_text="Notes about previous medical records (doctor name, hospital, date)"
    )

    class Meta:
        ordering = ['-visit_date']

    def __str__(self):
        return f"{self.patient.username} - {self.visit_date}"

    def get_age_at_visit(self):
        if self.patient.date_of_birth and self.visit_date:
            return self.visit_date.year - self.patient.date_of_birth.year - (
                (self.visit_date.month, self.visit_date.day) <
                (self.patient.date_of_birth.month, self.patient.date_of_birth.day)
            )
        return None


class LabTest(models.Model):
    """Lab test ordered by doctor, with results uploaded later."""
    STATUS_CHOICES = (
        ('ORDERED', 'Ordered'),
        ('SAMPLE_COLLECTED', 'Sample Collected'),
        ('IN_LAB', 'In Lab'),
        ('RESULTS_RECEIVED', 'Results Received'),
        ('CANCELLED', 'Cancelled'),
    )

    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='lab_tests'
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='lab_tests_ordered'
    )
    history = models.ForeignKey(
        PatientHistory,
        on_delete=models.CASCADE,
        related_name='lab_tests',
        null=True, blank=True
    )
    test_name = models.CharField(
        max_length=200,
        help_text="e.g., CBC, Blood Sugar, X-Ray, Ultrasound"
    )
    test_category = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="e.g., Blood Test, Radiology, Urine Test"
    )
    cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Cost of this lab test in PKR"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='ORDERED'
    )
    results = models.TextField(
        blank=True,
        help_text="Lab test results / findings"
    )
    report_file = models.FileField(
        upload_to='lab_reports/%Y/%m/',
        blank=True, null=True
    )
    notes = models.TextField(blank=True)
    ordered_date = models.DateField(auto_now_add=True)
    result_date = models.DateField(blank=True, null=True)

    class Meta:
        ordering = ['-ordered_date']

    def __str__(self):
        return f"{self.test_name} - {self.patient.username} ({self.get_status_display()})"


class LabTestCategory(models.Model):
    """Predefined lab test types with default costs."""
    name = models.CharField(max_length=200, unique=True)
    category = models.CharField(
        max_length=100,
        help_text="e.g., Blood Test, Radiology, Urine Test, Microbiology"
    )
    default_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Default cost in PKR"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category', 'name']
        verbose_name = "Lab Test Category"
        verbose_name_plural = "Lab Test Categories"

    def __str__(self):
        return f"{self.name} ({self.category}) — PKR {self.default_cost}"


class Payment(models.Model):
    METHOD_CHOICES = (
        ('CASH', 'Cash'),
        ('JAZZCASH', 'JazzCash'),
        ('EASYPAISA', 'EasyPaisa'),
        ('BANK', 'Bank Transfer'),
    )
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PAID', 'Paid'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
    )

    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name='payment'
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    method = models.CharField(
        max_length=10,
        choices=METHOD_CHOICES,
        default='CASH'
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='PENDING'
    )
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    payment_proof = models.ImageField(
        upload_to='payment_proofs/%Y/%m/',
        blank=True,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"PKR {self.amount} ({self.get_method_display()}) - {self.get_status_display()}"


class Notification(models.Model):
    """System notifications with email/SMS delivery tracking."""
    TYPE_CHOICES = (
        ('APPOINTMENT_CONFIRMED', 'Appointment Confirmed'),
        ('APPOINTMENT_REMINDER', 'Appointment Reminder'),
        ('APPOINTMENT_CANCELLED', 'Appointment Cancelled'),
        ('QUEUE_YOUR_TURN', 'Your Turn Next'),
        ('LAB_RESULTS_READY', 'Lab Results Ready'),
        ('FOLLOW_UP_DUE', 'Follow-Up Due'),
        ('PAYMENT_RECEIVED', 'Payment Received'),
        ('PAYMENT_VERIFIED', 'Payment Verified'),
        ('GENERAL', 'General'),
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    notification_type = models.CharField(
        max_length=25, choices=TYPE_CHOICES, default='GENERAL',
        db_index=True
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)

    # Delivery tracking
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(blank=True, null=True)
    sms_sent = models.BooleanField(default=False)
    sms_sent_at = models.DateTimeField(blank=True, null=True)
    delivery_error = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['notification_type', 'created_at']),
        ]

    def __str__(self):
        return f"{self.recipient.username}: {self.title} ({self.get_notification_type_display()})"


class PaymentSettings(models.Model):
    """Clinic payment account details displayed to patients."""
    jazzcash_number = models.CharField(
        max_length=20, blank=True, null=True,
        help_text="JazzCash mobile account number (e.g., 0300-1234567)"
    )
    easypaisa_number = models.CharField(
        max_length=20, blank=True, null=True,
        help_text="EasyPaisa mobile account number (e.g., 0311-7654321)"
    )
    bank_name = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Bank name (e.g., HBL, UBL, Meezan Bank)"
    )
    bank_account_title = models.CharField(
        max_length=200, blank=True, null=True,
        help_text="Bank account title"
    )
    bank_account_number = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="Bank account number / IBAN"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Payment Settings"
        verbose_name_plural = "Payment Settings"

    def __str__(self):
        return "Clinic Payment Settings"


class DoctorReview(models.Model):
    """Patient review and rating for a doctor."""
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews_given'
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews_received'
    )
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name='review'
    )
    rating = models.IntegerField(choices=RATING_CHOICES)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('patient', 'appointment')

    def __str__(self):
        return f"{self.patient.username} rated Dr. {self.doctor.username} — {self.rating}/5"
