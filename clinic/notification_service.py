"""
Healthcare Notification Service
Handles in-app notifications + email (Gmail SMTP) + SMS (Twilio) delivery.

Email: Configure EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in settings/.env
  - For Gmail, use an App Password (not your regular password)
  - Google Account > Security > 2-Step Verification > App Passwords

SMS: Configure TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
  - Sign up at https://www.twilio.com (free trial gives ~$15 credit)
  - Pakistani numbers supported via Twilio

For development without real credentials, notifications are saved in-app only
and delivery errors are logged.
"""
import logging
from datetime import datetime
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone

logger = logging.getLogger(__name__)


def create_notification(recipient, title, message, notification_type='GENERAL',
                        send_email=True, send_sms=True):
    """
    Create an in-app notification and optionally send via email and SMS.

    Usage:
        create_notification(
            recipient=user,
            title="Appointment Confirmed",
            message="Your appointment with Dr. Hira is confirmed for tomorrow at 10:00 AM.",
            notification_type="APPOINTMENT_CONFIRMED",
            send_email=True,
            send_sms=True
        )
    """
    from .models import Notification

    notif = Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
    )

    # Send email if user has email and send_email is True
    if send_email and recipient.email:
        _send_notification_email(notif, recipient, title, message)

    # Send SMS if user has phone and send_sms is True
    if send_sms and recipient.phone:
        _send_notification_sms(notif, recipient, title, message)

    return notif


def _send_notification_email(notif, recipient, title, message):
    """Send notification via email using Gmail SMTP."""
    try:
        subject = f"Healthcare: {title}"

        # Build HTML email
        html_message = render_to_string('clinic/emails/notification.html', {
            'title': title,
            'message': message,
            'recipient_name': recipient.get_full_name() or recipient.username,
            'notification_type': notif.get_notification_type_display(),
        })
        plain_message = strip_tags(html_message)

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'Healthcare <noreply@mediqueque.com>'),
            recipient_list=[recipient.email],
            html_message=html_message,
            fail_silently=True,
        )

        notif.email_sent = True
        notif.email_sent_at = timezone.now()
        notif.save(update_fields=['email_sent', 'email_sent_at'])
        logger.info(f"Email sent to {recipient.email}: {title}")

    except Exception as e:
        notif.delivery_error = f"Email failed: {str(e)}"
        notif.save(update_fields=['delivery_error'])
        logger.error(f"Email failed for {recipient.email}: {e}")


def _send_notification_sms(notif, recipient, title, message):
    """Send notification via SMS using Twilio."""
    try:
        account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
        auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
        from_number = getattr(settings, 'TWILIO_FROM_NUMBER', '')

        if not all([account_sid, auth_token, from_number]):
            # No Twilio credentials -- skip SMS silently in dev
            logger.info(f"SMS skipped (no Twilio config) for {recipient.phone}")
            return

        from twilio.rest import Client
        client = Client(account_sid, auth_token)

        sms_body = f"Healthcare: {title}\n{message[:140]}"
        # Normalize phone number
        phone = recipient.phone.strip()
        if not phone.startswith('+'):
            # Assume Pakistani number if no country code
            if phone.startswith('0'):
                phone = '+92' + phone[1:]
            elif not phone.startswith('92'):
                phone = '+92' + phone

        client.messages.create(
            body=sms_body,
            from_=from_number,
            to=phone,
        )

        notif.sms_sent = True
        notif.sms_sent_at = timezone.now()
        notif.save(update_fields=['sms_sent', 'sms_sent_at'])
        logger.info(f"SMS sent to {recipient.phone}: {title}")

    except ImportError:
        logger.info("Twilio not installed. Run: pip install twilio")
    except Exception as e:
        notif.delivery_error = f"SMS failed: {str(e)}"
        notif.save(update_fields=['delivery_error'])
        logger.error(f"SMS failed for {recipient.phone}: {e}")


def send_appointment_reminders():
    """
    Cron job: Send reminders for appointments scheduled tomorrow.
    Call this daily (e.g., at 6 PM) so patients know about tomorrow's appointments.
    """
    from datetime import date, timedelta
    from .models import Appointment, Notification

    tomorrow = date.today() + timedelta(days=1)
    appointments = Appointment.objects.filter(
        appointment_date=tomorrow,
        status='CONFIRMED',
    ).select_related('patient', 'doctor')

    count = 0
    for appt in appointments:
        # Check if reminder already sent today
        already_sent = Notification.objects.filter(
            recipient=appt.patient,
            notification_type='APPOINTMENT_REMINDER',
            created_at__date=date.today(),
        ).exists()
        if already_sent:
            continue

        create_notification(
            recipient=appt.patient,
            title="Appointment Reminder",
            message=(
                f"Reminder: You have an appointment tomorrow ({tomorrow.strftime('%B %d, %Y')}) "
                f"with Dr. {appt.doctor.get_full_name() or appt.doctor.username} "
                f"at {appt.time_slot.strftime('%I:%M %p') if hasattr(appt.time_slot, 'strftime') else appt.time_slot}. "
                f"Please arrive 15 minutes early."
            ),
            notification_type='APPOINTMENT_REMINDER',
            send_email=True,
            send_sms=True,
        )
        count += 1

    logger.info(f"Appointment reminders sent: {count}")
    return count


def send_follow_up_reminders():
    """
    Cron job: Send reminders for follow-up appointments that are due today.
    """
    from datetime import date
    from .models import PatientHistory

    today = date.today()
    follow_ups = PatientHistory.objects.filter(
        follow_up_required=True,
        follow_up_date=today,
    ).select_related('patient', 'doctor')

    count = 0
    for fu in follow_ups:
        create_notification(
            recipient=fu.patient,
            title="Follow-Up Due Today",
            message=(
                f"Dr. {fu.doctor.get_full_name() or fu.doctor.username} "
                f"scheduled a follow-up for today ({today.strftime('%B %d, %Y')}). "
                f"Please visit the clinic or book an appointment."
            ),
            notification_type='FOLLOW_UP_DUE',
            send_email=True,
            send_sms=True,
        )
        count += 1

    logger.info(f"Follow-up reminders sent: {count}")
    return count
