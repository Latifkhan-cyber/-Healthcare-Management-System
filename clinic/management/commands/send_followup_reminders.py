from django.core.management.base import BaseCommand
from clinic.notification_service import send_follow_up_reminders


class Command(BaseCommand):
    help = 'Send follow-up due reminders for today'

    def handle(self, *args, **options):
        count = send_follow_up_reminders()
        if count:
            self.stdout.write(self.style.SUCCESS(f'Sent {count} follow-up reminder(s)'))
        else:
            self.stdout.write('No follow-up reminders needed (none due today)')
