from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, time, timedelta
import random

from accounts.models import User
from clinic.models import (
    DoctorSchedule, Appointment, QueueToken,
    Payment, PatientHistory, Notification
)


class Command(BaseCommand):
    help = 'Seed test data for Healthcare demo'

    def handle(self, *args, **options):
        self.stdout.write('Seeding test data...')

        # ─── Create Sample Patients ────────────────────────────────
        patients_data = [
            {'username': 'hamza', 'first_name': 'Hamza', 'last_name': 'Khan',
             'email': 'hamza@email.com', 'phone': '03001234567',
             'gender': 'MALE', 'date_of_birth': '2015-03-15'},
            {'username': 'sara', 'first_name': 'Sara', 'last_name': 'Ali',
             'email': 'sara@email.com', 'phone': '03111234567',
             'gender': 'FEMALE', 'date_of_birth': '2018-07-22'},
            {'username': 'usman', 'first_name': 'Usman', 'last_name': 'Raza',
             'email': 'usman@email.com', 'phone': '03221234567',
             'gender': 'MALE', 'date_of_birth': '2020-01-10'},
        ]

        for p in patients_data:
            user, created = User.objects.get_or_create(
                username=p['username'],
                defaults={
                    'email': p['email'],
                    'first_name': p['first_name'],
                    'last_name': p['last_name'],
                    'role': 'PATIENT',
                    'phone': p['phone'],
                    'gender': p.get('gender'),
                    'date_of_birth': p.get('date_of_birth'),
                }
            )
            if created:
                user.set_password('patient123')
                user.save()
                self.stdout.write(f'  Created patient: {p["username"]}')

        # ─── Doctor Schedules (Mon-Fri 9-5, Sat 9-1) ──────────────
        doctors = User.objects.filter(role='DOCTOR')
        for doc in doctors:
            for day in range(5):
                DoctorSchedule.objects.get_or_create(
                    doctor=doc,
                    day_of_week=day,
                    defaults={
                        'start_time': time(9, 0),
                        'end_time': time(17, 0),
                        'is_available': True,
                    }
                )
            DoctorSchedule.objects.get_or_create(
                doctor=doc,
                day_of_week=5,
                defaults={
                    'start_time': time(9, 0),
                    'end_time': time(13, 0),
                    'is_available': True,
                }
            )
        self.stdout.write('  Created doctor schedules (Mon-Fri 9-5, Sat 9-1)')

        # ─── Sample Appointments ───────────────────────────────────
        today = date.today()
        all_doctors = list(User.objects.filter(role='DOCTOR'))
        all_patients = list(User.objects.filter(role='PATIENT'))

        if not all_patients or not all_doctors:
            self.stdout.write(self.style.WARNING('No patients/doctors to create appointments.'))
            return

        # Past completed appointment with history
        past_date = today - timedelta(days=3)
        appt1 = Appointment.objects.create(
            patient=all_patients[0],
            doctor=all_doctors[0],
            appointment_date=past_date,
            time_slot=time(10, 0),
            status='COMPLETED',
            reason='Routine checkup'
        )
        Payment.objects.create(
            appointment=appt1,
            amount=all_doctors[0].consultation_fee,
            method='CASH',
            status='PAID'
        )
        PatientHistory.objects.create(
            patient=all_patients[0],
            doctor=all_doctors[0],
            appointment=appt1,
            diagnosis='Routine examination - all normal',
            prescription='Continue healthy diet, follow up in 3 months',
            follow_up_required=True,
            follow_up_date=today + timedelta(days=90)
        )
        self.stdout.write('  Created past completed appointment with history')

        # Today's confirmed appointments (in queue)
        queue_times = [time(9, 0), time(9, 30), time(10, 0), time(10, 30)]
        for i, t in enumerate(queue_times):
            patient = all_patients[i % len(all_patients)]
            doctor = all_doctors[i % len(all_doctors)]
            appt = Appointment.objects.create(
                patient=patient,
                doctor=doctor,
                appointment_date=today,
                time_slot=t,
                status='CONFIRMED',
                reason='Regular checkup'
            )
            Payment.objects.create(
                appointment=appt,
                amount=doctor.consultation_fee,
                method=random.choice(['CASH', 'JAZZCASH', 'EASYPAISA']),
                status='PAID'
            )
            QueueToken.objects.create(
                appointment=appt,
                token_number=i + 1,
                estimated_wait_minutes=i * 15,
                is_active=True
            )
        self.stdout.write(f'  Created {len(queue_times)} today\'s appointments in queue')

        # Future pending appointment
        future_date = today + timedelta(days=2)
        appt_future = Appointment.objects.create(
            patient=all_patients[1],
            doctor=all_doctors[1],
            appointment_date=future_date,
            time_slot=time(11, 0),
            status='PENDING',
            reason='Consultation'
        )
        self.stdout.write('  Created future pending appointment')

        # ─── Notifications ─────────────────────────────────────────
        Notification.objects.create(
            recipient=all_patients[0],
            title='Follow-up Reminder',
            message='Your follow-up is in 3 months. Book your appointment early.',
            is_read=False,
        )
        Notification.objects.create(
            recipient=all_patients[1],
            title='Appointment Booked',
            message=f'Your appointment is on {future_date} at 11:00 AM.',
            is_read=False,
        )
        self.stdout.write('  Created sample notifications')

        self.stdout.write(self.style.SUCCESS('Done! Test data seeded.'))
        self.stdout.write('')
        self.stdout.write('ACCOUNTS:')
        self.stdout.write('  Admin:    hassan  / hassan123')
        self.stdout.write('  Admin:    admin   / admin123  (backup)')
        self.stdout.write('  Doctor:   dr_hira  / doctor123  (Dr. Hira Sheheryar - Gynaecologist)')
        self.stdout.write('  Doctor:   dr_saba  / doctor123  (Dr. Saba Gul - Gynaecologist)')
        self.stdout.write('  Doctor:   dr_taj   / doctor123  (Dr. Taj Bahadar Khan - Pediatrician)')
        self.stdout.write('  Doctor:   dr_idrees / doctor123 (Dr. Mohammed Idrees - Pediatrician)')
        self.stdout.write('  Patient:  hamza   / patient123')
        self.stdout.write('  Patient:  sara    / patient123')
        self.stdout.write('  Patient:  usman   / patient123')
