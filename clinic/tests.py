<<<<<<< HEAD
from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User
from clinic.models import (
    Appointment, PatientHistory, Payment, QueueToken,
    DoctorSchedule, DoctorReview, LabTest, PaymentSettings
)
from datetime import date, timedelta


class AuthTests(TestCase):
    """Test authentication and role-based access."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username='admin', password='admin123', role='ADMIN'
        )
        self.doctor = User.objects.create_user(
            username='doctor1', password='doctor123', role='DOCTOR',
            first_name='Hira', specialization='Gynaecology', consultation_fee=1000
        )
        self.receptionist = User.objects.create_user(
            username='receptionist', password='receptionist123', role='RECEPTIONIST'
        )
        self.patient = User.objects.create_user(
            username='patient1', password='patient123', role='PATIENT',
            first_name='Ali', last_name='Khan'
        )

    def test_login_page_loads(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)

    def test_admin_login(self):
        self.client.login(username='admin', password='admin123')
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)

    def test_patient_cannot_access_admin_pages(self):
        self.client.login(username='patient1', password='patient123')
        response = self.client.get(reverse('clinic:payment_records'))
        self.assertNotEqual(response.status_code, 200)

    def test_doctor_cannot_access_admin_pages(self):
        self.client.login(username='doctor1', password='doctor123')
        response = self.client.get(reverse('clinic:payment_records'))
        self.assertNotEqual(response.status_code, 200)


class PatientRegistrationTests(TestCase):
    """Test patient registration and ID generation."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username='admin', password='admin123', role='ADMIN'
        )

    def test_patient_auto_id_generation(self):
        patient = User.objects.create_user(
            username='newpatient', password='test123', role='PATIENT'
        )
        self.assertIsNotNone(patient.patient_id)
        self.assertTrue(patient.patient_id.startswith('MQ-'))

    def test_register_patient_by_admin(self):
        self.client.login(username='admin', password='admin123')
        # Get the page first to get CSRF token
        self.client.get('/clinic/patient/register/')
        response = self.client.post('/clinic/patient/register/', {
            'first_name': 'Fatima',
            'last_name': 'Ahmed',
            'username': 'fatima123',
            'email': 'fatima@test.com',
            'phone': '0300-1234567',
            'gender': 'FEMALE',
            'password1': 'testpass123',
            'password2': 'testpass123',
        })
        print(f"DEBUG: response status={response.status_code}, url={getattr(response, 'url', 'N/A')}")
        print(f"DEBUG: User count={User.objects.filter(username='fatima123').count()}")
        # Verify patient was created successfully
        patient = User.objects.get(username='fatima123')
        self.assertEqual(patient.role, 'PATIENT')
        self.assertIsNotNone(patient.patient_id)
        self.assertTrue(patient.patient_id.startswith('MQ-'))
        # Registration should succeed (may redirect or render)
        self.assertLess(response.status_code, 500)

    def test_patient_id_sequential(self):
        p1 = User.objects.create_user(username='p1', password='test123', role='PATIENT')
        p2 = User.objects.create_user(username='p2', password='test123', role='PATIENT')
        num1 = int(p1.patient_id.split('-')[1])
        num2 = int(p2.patient_id.split('-')[1])
        self.assertEqual(num2, num1 + 1)


class AppointmentTests(TestCase):
    """Test appointment booking and workflow."""

    def setUp(self):
        self.client = Client()
        self.patient = User.objects.create_user(
            username='patient1', password='patient123', role='PATIENT',
            first_name='Ali'
        )
        self.doctor = User.objects.create_user(
            username='doctor1', password='doctor123', role='DOCTOR',
            first_name='Hira', specialization='Gynaecology', consultation_fee=1000
        )
        self.admin = User.objects.create_superuser(
            username='admin', password='admin123', role='ADMIN'
        )
        # Create doctor schedule for today
        today = date.today()
        DoctorSchedule.objects.create(
            doctor=self.doctor,
            day_of_week=today.weekday(),
            start_time='09:00',
            end_time='17:00',
            is_available=True
        )

    def test_book_appointment(self):
        self.client.login(username='patient1', password='patient123')
        response = self.client.post(reverse('clinic:book_appointment'), {
            'doctor': self.doctor.id,
            'appointment_date': date.today().isoformat(),
            'time_slot': '10:00',
            'reason': 'Regular checkup',
        })
        self.assertEqual(response.status_code, 302)  # redirect to payment
        appt = Appointment.objects.filter(patient=self.patient).first()
        self.assertIsNotNone(appt)
        self.assertEqual(appt.status, 'PENDING')

    def test_walkin_booking_creates_confirmed_appointment(self):
        self.client.login(username='admin', password='admin123')
        response = self.client.post(reverse('clinic:walkin_booking'), {
            'patient_type': 'existing',
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'appointment_date': date.today().isoformat(),
            'time_slot': '11:00',
            'reason': 'Walk-in',
        })
        self.assertEqual(response.status_code, 302)
        appt = Appointment.objects.filter(patient=self.patient).first()
        self.assertIsNotNone(appt)
        self.assertEqual(appt.status, 'CONFIRMED')
        # Check payment created
        payment = Payment.objects.filter(appointment=appt).first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.status, 'PAID')
        self.assertEqual(payment.method, 'CASH')
        # Check queue token created
        token = QueueToken.objects.filter(appointment=appt).first()
        self.assertIsNotNone(token)

    def test_cancel_appointment(self):
        self.client.login(username='patient1', password='patient123')
        appt = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today(),
            time_slot='10:00',
            status='PENDING',
        )
        response = self.client.post(
            reverse('clinic:cancel_appointment', kwargs={'appointment_id': appt.id})
        )
        self.assertEqual(response.status_code, 302)
        appt.refresh_from_db()
        self.assertEqual(appt.status, 'CANCELLED')


class PaymentTests(TestCase):
    """Test payment workflow."""

    def setUp(self):
        self.client = Client()
        self.patient = User.objects.create_user(
            username='patient1', password='patient123', role='PATIENT',
            first_name='Ali'
        )
        self.doctor = User.objects.create_user(
            username='doctor1', password='doctor123', role='DOCTOR',
            consultation_fee=1000
        )
        self.admin = User.objects.create_superuser(
            username='admin', password='admin123', role='ADMIN'
        )
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today(),
            time_slot='10:00',
            status='PENDING',
        )

    def test_verify_payment_confirms_appointment(self):
        self.client.login(username='admin', password='admin123')
        payment = Payment.objects.create(
            appointment=self.appointment,
            amount=1000,
            method='JAZZCASH',
            status='PENDING',
        )
        response = self.client.post(
            reverse('clinic:verify_payment', kwargs={'payment_id': payment.id})
        )
        self.assertEqual(response.status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, 'CONFIRMED')
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'PAID')
        # Queue token should be created
        token = QueueToken.objects.filter(appointment=self.appointment).first()
        self.assertIsNotNone(token)

    def test_reject_payment(self):
        self.client.login(username='admin', password='admin123')
        payment = Payment.objects.create(
            appointment=self.appointment,
            amount=1000,
            method='JAZZCASH',
            status='PENDING',
        )
        response = self.client.post(
            reverse('clinic:reject_payment', kwargs={'payment_id': payment.id})
        )
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'FAILED')


class QueueTests(TestCase):
    """Test queue management."""

    def setUp(self):
        self.client = Client()
        self.doctor = User.objects.create_user(
            username='doctor1', password='doctor123', role='DOCTOR',
            first_name='Hira', consultation_fee=1000
        )
        self.patient = User.objects.create_user(
            username='patient1', password='patient123', role='PATIENT',
            first_name='Ali'
        )
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today(),
            time_slot='10:00',
            status='CONFIRMED',
        )
        self.token = QueueToken.objects.create(
            appointment=self.appointment,
            token_number=1,
            estimated_wait_minutes=0,
        )

    def test_serve_patient_marks_completed(self):
        self.client.login(username='doctor1', password='doctor123')
        response = self.client.post(
            reverse('clinic:serve_patient', kwargs={'token_id': self.token.id})
        )
        self.assertEqual(response.status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, 'COMPLETED')
        self.token.refresh_from_db()
        self.assertFalse(self.token.is_active)

    def test_call_next_completes_current(self):
        self.client.login(username='doctor1', password='doctor123')
        response = self.client.post(reverse('clinic:call_next'))
        self.assertEqual(response.status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, 'COMPLETED')


class MedicalRecordTests(TestCase):
    """Test medical record creation and access."""

    def setUp(self):
        self.client = Client()
        self.patient = User.objects.create_user(
            username='patient1', password='patient123', role='PATIENT',
            first_name='Ali'
        )
        self.doctor = User.objects.create_user(
            username='doctor1', password='doctor123', role='DOCTOR',
            first_name='Hira'
        )
        self.admin = User.objects.create_superuser(
            username='admin', password='admin123', role='ADMIN'
        )
        self.receptionist = User.objects.create_user(
            username='receptionist', password='receptionist123', role='RECEPTIONIST'
        )
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today(),
            time_slot='10:00',
            status='COMPLETED',
        )

    def test_record_consultation(self):
        self.client.login(username='admin', password='admin123')
        response = self.client.post(
            reverse('clinic:record_consultation', kwargs={'appointment_id': self.appointment.id}),
            {
                'blood_pressure': '120/80',
                'temperature': '98.6 F',
                'weight': '70 kg',
                'pulse': '72 bpm',
                'symptoms': 'Fever and cough',
                'diagnosis': 'Upper respiratory infection',
                'prescription': 'Paracetamol 500mg, Cetirizine 10mg',
                'follow_up_required': False,
            }
        )
        self.assertEqual(response.status_code, 302)
        record = PatientHistory.objects.filter(patient=self.patient).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.diagnosis, 'Upper respiratory infection')

    def test_receptionist_can_record_consultation(self):
        self.client.login(username='receptionist', password='receptionist123')
        response = self.client.post(
            reverse('clinic:record_consultation', kwargs={'appointment_id': self.appointment.id}),
            {
                'symptoms': 'Headache',
                'diagnosis': 'Migraine',
                'prescription': 'Ibuprofen 400mg',
                'follow_up_required': False,
            }
        )
        self.assertEqual(response.status_code, 302)
        record = PatientHistory.objects.filter(patient=self.patient).first()
        self.assertIsNotNone(record)

    def test_patient_can_view_own_history(self):
        PatientHistory.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment=self.appointment,
            symptoms='Fever',
            diagnosis='Flu',
            prescription='Rest and fluids',
        )
        self.client.login(username='patient1', password='patient123')
        response = self.client.get(reverse('clinic:view_history'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Flu')


class LabTestTests(TestCase):
    """Test lab test workflow."""

    def setUp(self):
        self.client = Client()
        self.patient = User.objects.create_user(
            username='patient1', password='patient123', role='PATIENT',
            first_name='Ali'
        )
        self.doctor = User.objects.create_user(
            username='doctor1', password='doctor123', role='DOCTOR',
            first_name='Hira'
        )
        self.admin = User.objects.create_superuser(
            username='admin', password='admin123', role='ADMIN'
        )

    def test_lab_test_status_update(self):
        lab_test = LabTest.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            test_name='CBC',
            status='ORDERED',
        )
        self.client.login(username='admin', password='admin123')
        response = self.client.post(
            reverse('clinic:update_lab_test', kwargs={'test_id': lab_test.id}),
            {
                'status': 'RESULTS_RECEIVED',
                'results': 'All values within normal range',
            }
        )
        self.assertEqual(response.status_code, 302)
        lab_test.refresh_from_db()
        self.assertEqual(lab_test.status, 'RESULTS_RECEIVED')
        self.assertIsNotNone(lab_test.result_date)


class DoctorReviewTests(TestCase):
    """Test doctor review system."""

    def setUp(self):
        self.client = Client()
        self.patient = User.objects.create_user(
            username='patient1', password='patient123', role='PATIENT',
            first_name='Ali'
        )
        self.doctor = User.objects.create_user(
            username='doctor1', password='doctor123', role='DOCTOR',
            first_name='Hira'
        )
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today(),
            time_slot='10:00',
            status='COMPLETED',
        )

    def test_patient_can_review_doctor(self):
        self.client.login(username='patient1', password='patient123')
        response = self.client.post(
            reverse('clinic:review_doctor', kwargs={'appointment_id': self.appointment.id}),
            {'rating': 5, 'comment': 'Excellent doctor!'}
        )
        self.assertEqual(response.status_code, 302)
        review = DoctorReview.objects.filter(doctor=self.doctor).first()
        self.assertIsNotNone(review)
        self.assertEqual(review.rating, 5)

    def test_cannot_review_twice(self):
        DoctorReview.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment=self.appointment,
            rating=5,
        )
        self.client.login(username='patient1', password='patient123')
        response = self.client.post(
            reverse('clinic:review_doctor', kwargs={'appointment_id': self.appointment.id}),
            {'rating': 4, 'comment': 'Trying again'}
        )
        # Should redirect without creating duplicate
        reviews = DoctorReview.objects.filter(doctor=self.doctor, patient=self.patient)
        self.assertEqual(reviews.count(), 1)
=======
from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User
from clinic.models import (
    Appointment, PatientHistory, Payment, QueueToken,
    DoctorSchedule, DoctorReview, LabTest, PaymentSettings
)
from datetime import date, timedelta


class AuthTests(TestCase):
    """Test authentication and role-based access."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username='admin', password='admin123', role='ADMIN'
        )
        self.doctor = User.objects.create_user(
            username='doctor1', password='doctor123', role='DOCTOR',
            first_name='Hira', specialization='Gynaecology', consultation_fee=1000
        )
        self.receptionist = User.objects.create_user(
            username='receptionist', password='receptionist123', role='RECEPTIONIST'
        )
        self.patient = User.objects.create_user(
            username='patient1', password='patient123', role='PATIENT',
            first_name='Ali', last_name='Khan'
        )

    def test_login_page_loads(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)

    def test_admin_login(self):
        self.client.login(username='admin', password='admin123')
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)

    def test_patient_cannot_access_admin_pages(self):
        self.client.login(username='patient1', password='patient123')
        response = self.client.get(reverse('clinic:payment_records'))
        self.assertNotEqual(response.status_code, 200)

    def test_doctor_cannot_access_admin_pages(self):
        self.client.login(username='doctor1', password='doctor123')
        response = self.client.get(reverse('clinic:payment_records'))
        self.assertNotEqual(response.status_code, 200)


class PatientRegistrationTests(TestCase):
    """Test patient registration and ID generation."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username='admin', password='admin123', role='ADMIN'
        )

    def test_patient_auto_id_generation(self):
        patient = User.objects.create_user(
            username='newpatient', password='test123', role='PATIENT'
        )
        self.assertIsNotNone(patient.patient_id)
        self.assertTrue(patient.patient_id.startswith('MQ-'))

    def test_register_patient_by_admin(self):
        self.client.login(username='admin', password='admin123')
        # Get the page first to get CSRF token
        self.client.get('/clinic/patient/register/')
        response = self.client.post('/clinic/patient/register/', {
            'first_name': 'Fatima',
            'last_name': 'Ahmed',
            'username': 'fatima123',
            'email': 'fatima@test.com',
            'phone': '0300-1234567',
            'gender': 'FEMALE',
            'password1': 'testpass123',
            'password2': 'testpass123',
        })
        print(f"DEBUG: response status={response.status_code}, url={getattr(response, 'url', 'N/A')}")
        print(f"DEBUG: User count={User.objects.filter(username='fatima123').count()}")
        # Verify patient was created successfully
        patient = User.objects.get(username='fatima123')
        self.assertEqual(patient.role, 'PATIENT')
        self.assertIsNotNone(patient.patient_id)
        self.assertTrue(patient.patient_id.startswith('MQ-'))
        # Registration should succeed (may redirect or render)
        self.assertLess(response.status_code, 500)

    def test_patient_id_sequential(self):
        p1 = User.objects.create_user(username='p1', password='test123', role='PATIENT')
        p2 = User.objects.create_user(username='p2', password='test123', role='PATIENT')
        num1 = int(p1.patient_id.split('-')[1])
        num2 = int(p2.patient_id.split('-')[1])
        self.assertEqual(num2, num1 + 1)


class AppointmentTests(TestCase):
    """Test appointment booking and workflow."""

    def setUp(self):
        self.client = Client()
        self.patient = User.objects.create_user(
            username='patient1', password='patient123', role='PATIENT',
            first_name='Ali'
        )
        self.doctor = User.objects.create_user(
            username='doctor1', password='doctor123', role='DOCTOR',
            first_name='Hira', specialization='Gynaecology', consultation_fee=1000
        )
        self.admin = User.objects.create_superuser(
            username='admin', password='admin123', role='ADMIN'
        )
        # Create doctor schedule for today
        today = date.today()
        DoctorSchedule.objects.create(
            doctor=self.doctor,
            day_of_week=today.weekday(),
            start_time='09:00',
            end_time='17:00',
            is_available=True
        )

    def test_book_appointment(self):
        self.client.login(username='patient1', password='patient123')
        response = self.client.post(reverse('clinic:book_appointment'), {
            'doctor': self.doctor.id,
            'appointment_date': date.today().isoformat(),
            'time_slot': '10:00',
            'reason': 'Regular checkup',
        })
        self.assertEqual(response.status_code, 302)  # redirect to payment
        appt = Appointment.objects.filter(patient=self.patient).first()
        self.assertIsNotNone(appt)
        self.assertEqual(appt.status, 'PENDING')

    def test_walkin_booking_creates_confirmed_appointment(self):
        self.client.login(username='admin', password='admin123')
        response = self.client.post(reverse('clinic:walkin_booking'), {
            'patient_type': 'existing',
            'patient_id': self.patient.id,
            'doctor_id': self.doctor.id,
            'appointment_date': date.today().isoformat(),
            'time_slot': '11:00',
            'reason': 'Walk-in',
        })
        self.assertEqual(response.status_code, 302)
        appt = Appointment.objects.filter(patient=self.patient).first()
        self.assertIsNotNone(appt)
        self.assertEqual(appt.status, 'CONFIRMED')
        # Check payment created
        payment = Payment.objects.filter(appointment=appt).first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.status, 'PAID')
        self.assertEqual(payment.method, 'CASH')
        # Check queue token created
        token = QueueToken.objects.filter(appointment=appt).first()
        self.assertIsNotNone(token)

    def test_cancel_appointment(self):
        self.client.login(username='patient1', password='patient123')
        appt = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today(),
            time_slot='10:00',
            status='PENDING',
        )
        response = self.client.post(
            reverse('clinic:cancel_appointment', kwargs={'appointment_id': appt.id})
        )
        self.assertEqual(response.status_code, 302)
        appt.refresh_from_db()
        self.assertEqual(appt.status, 'CANCELLED')


class PaymentTests(TestCase):
    """Test payment workflow."""

    def setUp(self):
        self.client = Client()
        self.patient = User.objects.create_user(
            username='patient1', password='patient123', role='PATIENT',
            first_name='Ali'
        )
        self.doctor = User.objects.create_user(
            username='doctor1', password='doctor123', role='DOCTOR',
            consultation_fee=1000
        )
        self.admin = User.objects.create_superuser(
            username='admin', password='admin123', role='ADMIN'
        )
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today(),
            time_slot='10:00',
            status='PENDING',
        )

    def test_verify_payment_confirms_appointment(self):
        self.client.login(username='admin', password='admin123')
        payment = Payment.objects.create(
            appointment=self.appointment,
            amount=1000,
            method='JAZZCASH',
            status='PENDING',
        )
        response = self.client.post(
            reverse('clinic:verify_payment', kwargs={'payment_id': payment.id})
        )
        self.assertEqual(response.status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, 'CONFIRMED')
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'PAID')
        # Queue token should be created
        token = QueueToken.objects.filter(appointment=self.appointment).first()
        self.assertIsNotNone(token)

    def test_reject_payment(self):
        self.client.login(username='admin', password='admin123')
        payment = Payment.objects.create(
            appointment=self.appointment,
            amount=1000,
            method='JAZZCASH',
            status='PENDING',
        )
        response = self.client.post(
            reverse('clinic:reject_payment', kwargs={'payment_id': payment.id})
        )
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'FAILED')


class QueueTests(TestCase):
    """Test queue management."""

    def setUp(self):
        self.client = Client()
        self.doctor = User.objects.create_user(
            username='doctor1', password='doctor123', role='DOCTOR',
            first_name='Hira', consultation_fee=1000
        )
        self.patient = User.objects.create_user(
            username='patient1', password='patient123', role='PATIENT',
            first_name='Ali'
        )
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today(),
            time_slot='10:00',
            status='CONFIRMED',
        )
        self.token = QueueToken.objects.create(
            appointment=self.appointment,
            token_number=1,
            estimated_wait_minutes=0,
        )

    def test_serve_patient_marks_completed(self):
        self.client.login(username='doctor1', password='doctor123')
        response = self.client.post(
            reverse('clinic:serve_patient', kwargs={'token_id': self.token.id})
        )
        self.assertEqual(response.status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, 'COMPLETED')
        self.token.refresh_from_db()
        self.assertFalse(self.token.is_active)

    def test_call_next_completes_current(self):
        self.client.login(username='doctor1', password='doctor123')
        response = self.client.post(reverse('clinic:call_next'))
        self.assertEqual(response.status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, 'COMPLETED')


class MedicalRecordTests(TestCase):
    """Test medical record creation and access."""

    def setUp(self):
        self.client = Client()
        self.patient = User.objects.create_user(
            username='patient1', password='patient123', role='PATIENT',
            first_name='Ali'
        )
        self.doctor = User.objects.create_user(
            username='doctor1', password='doctor123', role='DOCTOR',
            first_name='Hira'
        )
        self.admin = User.objects.create_superuser(
            username='admin', password='admin123', role='ADMIN'
        )
        self.receptionist = User.objects.create_user(
            username='receptionist', password='receptionist123', role='RECEPTIONIST'
        )
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today(),
            time_slot='10:00',
            status='COMPLETED',
        )

    def test_record_consultation(self):
        self.client.login(username='admin', password='admin123')
        response = self.client.post(
            reverse('clinic:record_consultation', kwargs={'appointment_id': self.appointment.id}),
            {
                'blood_pressure': '120/80',
                'temperature': '98.6 F',
                'weight': '70 kg',
                'pulse': '72 bpm',
                'symptoms': 'Fever and cough',
                'diagnosis': 'Upper respiratory infection',
                'prescription': 'Paracetamol 500mg, Cetirizine 10mg',
                'follow_up_required': False,
            }
        )
        self.assertEqual(response.status_code, 302)
        record = PatientHistory.objects.filter(patient=self.patient).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.diagnosis, 'Upper respiratory infection')

    def test_receptionist_can_record_consultation(self):
        self.client.login(username='receptionist', password='receptionist123')
        response = self.client.post(
            reverse('clinic:record_consultation', kwargs={'appointment_id': self.appointment.id}),
            {
                'symptoms': 'Headache',
                'diagnosis': 'Migraine',
                'prescription': 'Ibuprofen 400mg',
                'follow_up_required': False,
            }
        )
        self.assertEqual(response.status_code, 302)
        record = PatientHistory.objects.filter(patient=self.patient).first()
        self.assertIsNotNone(record)

    def test_patient_can_view_own_history(self):
        PatientHistory.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment=self.appointment,
            symptoms='Fever',
            diagnosis='Flu',
            prescription='Rest and fluids',
        )
        self.client.login(username='patient1', password='patient123')
        response = self.client.get(reverse('clinic:view_history'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Flu')


class LabTestTests(TestCase):
    """Test lab test workflow."""

    def setUp(self):
        self.client = Client()
        self.patient = User.objects.create_user(
            username='patient1', password='patient123', role='PATIENT',
            first_name='Ali'
        )
        self.doctor = User.objects.create_user(
            username='doctor1', password='doctor123', role='DOCTOR',
            first_name='Hira'
        )
        self.admin = User.objects.create_superuser(
            username='admin', password='admin123', role='ADMIN'
        )

    def test_lab_test_status_update(self):
        lab_test = LabTest.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            test_name='CBC',
            status='ORDERED',
        )
        self.client.login(username='admin', password='admin123')
        response = self.client.post(
            reverse('clinic:update_lab_test', kwargs={'test_id': lab_test.id}),
            {
                'status': 'RESULTS_RECEIVED',
                'results': 'All values within normal range',
            }
        )
        self.assertEqual(response.status_code, 302)
        lab_test.refresh_from_db()
        self.assertEqual(lab_test.status, 'RESULTS_RECEIVED')
        self.assertIsNotNone(lab_test.result_date)


class DoctorReviewTests(TestCase):
    """Test doctor review system."""

    def setUp(self):
        self.client = Client()
        self.patient = User.objects.create_user(
            username='patient1', password='patient123', role='PATIENT',
            first_name='Ali'
        )
        self.doctor = User.objects.create_user(
            username='doctor1', password='doctor123', role='DOCTOR',
            first_name='Hira'
        )
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=date.today(),
            time_slot='10:00',
            status='COMPLETED',
        )

    def test_patient_can_review_doctor(self):
        self.client.login(username='patient1', password='patient123')
        response = self.client.post(
            reverse('clinic:review_doctor', kwargs={'appointment_id': self.appointment.id}),
            {'rating': 5, 'comment': 'Excellent doctor!'}
        )
        self.assertEqual(response.status_code, 302)
        review = DoctorReview.objects.filter(doctor=self.doctor).first()
        self.assertIsNotNone(review)
        self.assertEqual(review.rating, 5)

    def test_cannot_review_twice(self):
        DoctorReview.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment=self.appointment,
            rating=5,
        )
        self.client.login(username='patient1', password='patient123')
        response = self.client.post(
            reverse('clinic:review_doctor', kwargs={'appointment_id': self.appointment.id}),
            {'rating': 4, 'comment': 'Trying again'}
        )
        # Should redirect without creating duplicate
        reviews = DoctorReview.objects.filter(doctor=self.doctor, patient=self.patient)
        self.assertEqual(reviews.count(), 1)
>>>>>>> 2e565245d9ebda10d3916c12f324d412898853a9
