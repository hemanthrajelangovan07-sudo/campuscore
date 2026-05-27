from flask import render_template
from flask_mail import Message
from app.extensions import mail
from app.extensions import db
from app.models.user import User
from app.models.user_setting import UserSetting


def send_html_email(recipient_email, subject, template_name, **context):
    from flask import current_app as app
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        return
    try:
        html = render_template(f'email/{template_name}', **context)
        msg = Message(subject, recipients=[recipient_email], html=html)
        mail.send(msg)
    except Exception as e:
        print(f"Email send failed to {recipient_email}: {e}")


def send_registration_confirmation(student, event):
    organizer = User.query.get(event.created_by)
    organizer_name = organizer.name if organizer else 'Organizer'
    send_html_email(
        student.email,
        f"✅ You're registered for {event.title}",
        'event_registration_confirmation.html',
        student=student,
        event=event,
        organizer_name=organizer_name
    )


def send_event_update_notification(user, event, change_description):
    settings = UserSetting.query.filter_by(user_id=user.id).first()
    if settings and not settings.email_notifications:
        return
    send_html_email(
        user.email,
        f"📋 Update: {event.title}",
        'event_update_notification.html',
        user=user,
        event=event,
        change_description=change_description
    )


def send_password_reset_notification(user, forced=False):
    settings = UserSetting.query.filter_by(user_id=user.id).first()
    if settings and not settings.email_notifications:
        return
    subject = '🔐 Password Reset - CampusCore' if not forced else '🔐 Password Reset Required - CampusCore'
    send_html_email(
        user.email,
        subject,
        'password_reset_notification.html',
        user=user,
        forced=forced
    )


def send_account_update_notification(user, changes):
    settings = UserSetting.query.filter_by(user_id=user.id).first()
    if settings and not settings.email_notifications:
        return
    send_html_email(
        user.email,
        f"🔔 Your CampusCore Account Has Been Updated",
        'account_update_notification.html',
        user=user,
        changes=changes
    )


def send_new_user_notification(new_user):
    admins = User.query.filter_by(role='admin').all()
    for admin in admins:
        settings = UserSetting.query.filter_by(user_id=admin.id).first()
        if settings and not settings.email_notifications:
            continue
        send_html_email(
            admin.email,
            f"👤 New User Registration: {new_user.name}",
            'new_user_notification.html',
            admin=admin,
            new_user=new_user
        )
