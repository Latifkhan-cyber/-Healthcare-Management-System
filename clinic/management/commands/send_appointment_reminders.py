from django.core.management.base import BaseCommand
from clinic.notification_service import send_appointment_reminders


class Command(BaseCommand):
    help = 'Send appointment reminders for tomorrow\'s appointments'

    def handle(self, *args, **options):
        count = send_appointment_reminders()
        if count:
            self.stdout.write(self.style.SUCCESS(f'Sent {count} appointment reminder(s)'))
        else:
            self.stdout.write('No reminders needed (no confirmed appointments for tomorrow)')
