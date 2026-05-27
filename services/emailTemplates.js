const layout = (content) => `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
</head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:12px;overflow:hidden;
                    box-shadow:0 4px 24px rgba(0,0,0,0.08);">
        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#1a2f5e 0%,#2d4f9e 100%);
                     padding:28px 40px;text-align:center;">
            <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;
                       letter-spacing:1px;">CampusCore</h1>
            <p style="margin:4px 0 0;color:#a8b8e8;font-size:13px;">
              Sathyabama Institute of Science and Technology
            </p>
          </td>
        </tr>
        <!-- Body -->
        <tr><td style="padding:36px 40px;">${content}</td></tr>
        <!-- Footer -->
        <tr>
          <td style="background:#f8f9fc;padding:20px 40px;text-align:center;
                     border-top:1px solid #e8ecf4;">
            <p style="margin:0;color:#9aa3b5;font-size:12px;line-height:1.6;">
              This email was sent by <strong>CampusCore SIST</strong>.<br/>
              Sathyabama Institute of Science and Technology, Chennai.<br/>
              <a href="${process.env.FRONTEND_URL}/settings"
                 style="color:#2d4f9e;text-decoration:none;">
                Manage notification preferences
              </a>
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>`;

const infoRow = (label, value) => `
  <tr>
    <td style="padding:6px 0;color:#666;font-size:14px;width:140px;">${label}</td>
    <td style="padding:6px 0;color:#1a1a1a;font-size:14px;font-weight:600;">${value}</td>
  </tr>`;

const ctaButton = (text, url) => `
  <a href="${url}"
     style="display:inline-block;margin-top:24px;
            background:linear-gradient(135deg,#1a2f5e,#2d4f9e);
            color:#fff;text-decoration:none;padding:13px 28px;
            border-radius:8px;font-size:15px;font-weight:600;">
    ${text}
  </a>`;

const changeRow = (c) => `
  <tr>
    <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;">
      <strong style="color:#1a2f5e;">${c.field}</strong>
    </td>
    <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;
               color:#e53e3e;text-decoration:line-through;font-size:13px;">
      ${c.oldValue || '—'}
    </td>
    <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;
               color:#38a169;font-size:13px;">
      ${c.newValue || '—'}
    </td>
  </tr>`;

const IST = (date = new Date()) =>
  date.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) + ' IST';

exports.eventRegistrationConfirmation = ({ student, event }) =>
  layout(`
    <div style="text-align:center;margin-bottom:28px;">
      <div style="font-size:48px;">✅</div>
      <h2 style="margin:12px 0 4px;color:#1a2f5e;font-size:22px;">
        Registration Confirmed!
      </h2>
      <p style="color:#666;margin:0;">You're all set for the event below.</p>
    </div>
    <p style="color:#333;font-size:15px;">
      Hi <strong>${student.firstName}</strong>,<br/><br/>
      Your registration for the following event has been confirmed.
    </p>
    <div style="background:#f4f7ff;border-left:4px solid #2d4f9e;
                border-radius:8px;padding:20px 24px;margin:20px 0;">
      <h3 style="margin:0 0 16px;color:#1a2f5e;font-size:18px;">${event.title}</h3>
      <table cellpadding="0" cellspacing="0">
        ${infoRow('📅 Date', new Date(event.date).toDateString())}
        ${infoRow('🕒 Time', event.time || 'TBA')}
        ${infoRow('📍 Venue', event.venue || 'TBA')}
        ${infoRow('👤 Organizer', event.organizerName || 'SIST')}
      </table>
    </div>
    <p style="color:#555;font-size:14px;">
      You will receive email updates if there are any changes to this event.
    </p>
    ${ctaButton('View Event Details', `${process.env.FRONTEND_URL}/events/${event._id}`)}
  `);

exports.eventUpdateNotification = ({ event, changes }) =>
  layout(`
    <div style="text-align:center;margin-bottom:28px;">
      <div style="font-size:48px;">🔔</div>
      <h2 style="margin:12px 0 4px;color:#1a2f5e;font-size:22px;">Event Update</h2>
      <p style="color:#666;margin:0;">An event you registered for has been updated.</p>
    </div>
    <p style="color:#333;font-size:15px;">
      The following changes were made to <strong>${event.title}</strong>:
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border:1px solid #e8ecf4;border-radius:8px;
                  overflow:hidden;margin:16px 0;font-size:14px;">
      <tr style="background:#f4f7ff;">
        <th style="padding:10px 12px;text-align:left;color:#1a2f5e;">Field</th>
        <th style="padding:10px 12px;text-align:left;color:#e53e3e;">Old Value</th>
        <th style="padding:10px 12px;text-align:left;color:#38a169;">New Value</th>
      </tr>
      ${changes.map(changeRow).join('')}
    </table>
    <div style="background:#f4f7ff;border-radius:8px;padding:16px 20px;margin-top:16px;">
      <p style="margin:0;font-size:13px;color:#555;">
        <strong>Current event details:</strong><br/>
        📅 ${new Date(event.date).toDateString()} &nbsp;|&nbsp;
        🕒 ${event.time || 'TBA'} &nbsp;|&nbsp;
        📍 ${event.venue || 'TBA'}
      </p>
    </div>
    ${ctaButton('View Updated Event', `${process.env.FRONTEND_URL}/events/${event._id}`)}
  `);

exports.organizerEditAuditForAdmins = ({ actingAdmin, organizer, changes }) =>
  layout(`
    <div style="text-align:center;margin-bottom:28px;">
      <div style="font-size:48px;">🛡️</div>
      <h2 style="margin:12px 0 4px;color:#1a2f5e;font-size:22px;">Admin Audit Log</h2>
      <p style="color:#666;margin:0;">A user profile was modified.</p>
    </div>
    <table cellpadding="0" cellspacing="0" style="margin-bottom:20px;">
      ${infoRow('Performed By', `${actingAdmin.firstName} ${actingAdmin.lastName} (Admin)`)}
      ${infoRow('Target User', `${organizer.firstName} ${organizer.lastName}`)}
      ${infoRow('Role', 'Organizer')}
      ${infoRow('Email', organizer.email)}
      ${infoRow('Timestamp', IST())}
    </table>
    <p style="color:#333;font-size:14px;font-weight:600;margin-bottom:8px;">
      Fields Changed:
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border:1px solid #e8ecf4;border-radius:8px;overflow:hidden;font-size:14px;">
      <tr style="background:#f4f7ff;">
        <th style="padding:10px 12px;text-align:left;color:#1a2f5e;">Field</th>
        <th style="padding:10px 12px;text-align:left;color:#e53e3e;">Before</th>
        <th style="padding:10px 12px;text-align:left;color:#38a169;">After</th>
      </tr>
      ${changes.map(changeRow).join('')}
    </table>
    ${ctaButton('View User in Admin Panel',
      `${process.env.FRONTEND_URL}/admin/users/${organizer._id}`)}
  `);

exports.profileEditedForOrganizer = ({ organizer, actingAdmin, changes }) =>
  layout(`
    <div style="text-align:center;margin-bottom:28px;">
      <div style="font-size:48px;">📝</div>
      <h2 style="margin:12px 0 4px;color:#1a2f5e;font-size:22px;">
        Your Profile Was Updated
      </h2>
      <p style="color:#666;margin:0;">An administrator made changes to your account.</p>
    </div>
    <p style="color:#333;font-size:15px;">
      Hi <strong>${organizer.firstName}</strong>,<br/><br/>
      Your CampusCore profile was updated by Admin
      <strong>${actingAdmin.firstName} ${actingAdmin.lastName}</strong>
      on <strong>${IST()}</strong>.
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border:1px solid #e8ecf4;border-radius:8px;
                  overflow:hidden;margin:16px 0;font-size:14px;">
      <tr style="background:#f4f7ff;">
        <th style="padding:10px 12px;text-align:left;color:#1a2f5e;">Field</th>
        <th style="padding:10px 12px;text-align:left;color:#e53e3e;">Old</th>
        <th style="padding:10px 12px;text-align:left;color:#38a169;">New</th>
      </tr>
      ${changes.map(changeRow).join('')}
    </table>
    <div style="background:#fff8e1;border-left:4px solid #f6ad55;
                border-radius:8px;padding:16px 20px;margin-top:16px;">
      <p style="margin:0;font-size:13px;color:#744210;">
        ⚠️ If you did not expect these changes, contact your CampusCore
        Administrator at
        <a href="mailto:${actingAdmin.email}" style="color:#744210;">
          ${actingAdmin.email}
        </a> immediately.
      </p>
    </div>
    ${ctaButton('View My Profile', `${process.env.FRONTEND_URL}/settings`)}
  `);

exports.forcePasswordReset = ({ user, actingAdmin, resetLink }) =>
  layout(`
    <div style="text-align:center;margin-bottom:28px;">
      <div style="font-size:48px;">🔐</div>
      <h2 style="margin:12px 0 4px;color:#c53030;font-size:22px;">
        Your Password Was Reset
      </h2>
      <p style="color:#666;margin:0;">Action required — please set a new password.</p>
    </div>
    <p style="color:#333;font-size:15px;">
      Hi <strong>${user.firstName}</strong>,<br/><br/>
      Your CampusCore password was reset by Administrator
      <strong>${actingAdmin.firstName} ${actingAdmin.lastName}</strong>
      on <strong>${IST()}</strong>.
    </p>
    <div style="background:#fff5f5;border:1px solid #fed7d7;
                border-radius:8px;padding:20px 24px;margin:20px 0;">
      <p style="margin:0 0 12px;font-size:14px;color:#c53030;font-weight:600;">
        What you need to do:
      </p>
      <ol style="margin:0;padding-left:20px;color:#555;font-size:14px;line-height:1.8;">
        <li>Click the button below to set a new password</li>
        <li>This link expires in <strong>1 hour</strong></li>
        <li>After resetting, log in with your new password</li>
      </ol>
    </div>
    <div style="text-align:center;">
      <a href="${resetLink}"
         style="display:inline-block;margin-top:8px;
                background:linear-gradient(135deg,#c53030,#e53e3e);
                color:#fff;text-decoration:none;padding:14px 32px;
                border-radius:8px;font-size:15px;font-weight:700;">
        Set New Password
      </a>
    </div>
    <div style="background:#f4f7ff;border-left:4px solid #2d4f9e;
                border-radius:8px;padding:16px 20px;margin-top:24px;">
      <p style="margin:0;font-size:13px;color:#2d4f9e;">
        🔒 If you did not expect this, contact
        <a href="mailto:${actingAdmin.email}" style="color:#2d4f9e;">
          ${actingAdmin.email}
        </a> immediately.
      </p>
    </div>
  `);

exports.newUserRegistrationAlert = ({ newUser }) =>
  layout(`
    <div style="text-align:center;margin-bottom:28px;">
      <div style="font-size:48px;">👤</div>
      <h2 style="margin:12px 0 4px;color:#1a2f5e;font-size:22px;">
        New ${newUser.role.charAt(0).toUpperCase() + newUser.role.slice(1)} Registered
      </h2>
      <p style="color:#666;margin:0;">A new user has joined CampusCore.</p>
    </div>
    <div style="background:#f4f7ff;border-radius:8px;padding:20px 24px;margin:16px 0;">
      <table cellpadding="0" cellspacing="0">
        ${infoRow('Name', `${newUser.firstName} ${newUser.lastName}`)}
        ${infoRow('Email', newUser.email)}
        ${infoRow('Role', newUser.role)}
        ${infoRow('College', newUser.college || 'SIST')}
        ${infoRow('Registered At', IST())}
      </table>
    </div>
    ${ctaButton('View User in Admin Panel',
      `${process.env.FRONTEND_URL}/admin/users/${newUser._id}`)}
  `);
