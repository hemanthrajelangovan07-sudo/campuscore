const transporter = require('../config/mailer');
const templates = require('./emailTemplates');
const EmailLog = require('../models/EmailLog');

const send = async ({ to, subject, html, type }) => {
  const recipients = Array.isArray(to) ? to.join(', ') : to;

  const mailOptions = {
    from: `"${process.env.EMAIL_FROM_NAME}" <${process.env.EMAIL_FROM}>`,
    to: recipients,
    subject,
    html,
  };

  try {
    await transporter.sendMail(mailOptions);

    await EmailLog.create({
      recipientEmail: recipients,
      subject,
      type,
      status: 'sent',
      sentAt: new Date(),
    });

    console.log(`[EMAIL] ✅ ${type} → ${recipients}`);
  } catch (error) {
    await EmailLog.create({
      recipientEmail: recipients,
      subject,
      type,
      status: 'failed',
      error: error.message,
      sentAt: new Date(),
    });

    console.error(`[EMAIL] ❌ ${type} failed → ${error.message}`);
  }
};

const sendIfEnabled = async (user, sendFn, skipPreferenceCheck = false) => {
  if (!skipPreferenceCheck && user.preferences?.emailNotifications === false) {
    console.log(`[EMAIL] Skipped — ${user.email} opted out.`);
    return;
  }
  return sendFn();
};

exports.sendEventRegistrationConfirmation = async (student, event) => {
  await sendIfEnabled(student, () =>
    send({
      to: student.email,
      subject: `✅ You're registered for ${event.title} — CampusCore`,
      html: templates.eventRegistrationConfirmation({ student, event }),
      type: 'EVENT_REGISTRATION_CONFIRMATION',
    })
  );
};

exports.sendEventUpdateNotification = async (students, event, changes) => {
  const eligible = students.filter(s => s.preferences?.emailNotifications !== false);

  for (const student of eligible) {
    await send({
      to: student.email,
      subject: `🔔 Update for "${event.title}" — CampusCore`,
      html: templates.eventUpdateNotification({ event, changes }),
      type: 'EVENT_UPDATE_NOTIFICATION',
    });
  }
};

exports.sendOrganizerEditAuditToAdmins = async (admins, actingAdmin, organizer, changes) => {
  for (const admin of admins) {
    await send({
      to: admin.email,
      subject: `🛡️ Audit: ${actingAdmin.firstName} edited ${organizer.firstName}'s profile`,
      html: templates.organizerEditAuditForAdmins({ actingAdmin, organizer, changes }),
      type: 'ORGANIZER_EDIT_AUDIT_ADMIN',
    });
  }
};

exports.sendProfileEditedNotificationToOrganizer = async (organizer, actingAdmin, changes) => {
  await sendIfEnabled(organizer, () =>
    send({
      to: organizer.email,
      subject: `📝 Your CampusCore profile was updated by an Admin`,
      html: templates.profileEditedForOrganizer({ organizer, actingAdmin, changes }),
      type: 'PROFILE_EDITED_ORGANIZER',
    })
  );
};

exports.sendForcePasswordResetNotification = async (user, actingAdmin, resetLink) => {
  await sendIfEnabled(
    user,
    () => send({
      to: user.email,
      subject: `🔐 Your CampusCore password was reset by an Administrator`,
      html: templates.forcePasswordReset({ user, actingAdmin, resetLink }),
      type: 'FORCE_PASSWORD_RESET',
    }),
    true
  );
};

exports.sendNewUserRegistrationAlertToAdmins = async (admins, newUser) => {
  for (const admin of admins) {
    await send({
      to: admin.email,
      subject: `👤 New ${newUser.role} registered — ${newUser.firstName} ${newUser.lastName}`,
      html: templates.newUserRegistrationAlert({ newUser }),
      type: 'NEW_USER_REGISTRATION_ALERT',
    });
  }
};
