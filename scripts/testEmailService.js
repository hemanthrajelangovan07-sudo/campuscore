require('dotenv').config();
const nodemailer = require('nodemailer');
const templates = require('../services/emailTemplates');

const delay = (ms) => new Promise(r => setTimeout(r, ms));

const send = async (to, subject, html) => {
  const transporter = nodemailer.createTransport({
    host: process.env.SMTP_HOST,
    port: Number(process.env.SMTP_PORT),
    secure: false,
    auth: {
      user: process.env.SMTP_USER,
      pass: process.env.SMTP_PASS,
    },
    pool: false,
  });
  const info = await transporter.sendMail({
    from: `"${process.env.EMAIL_FROM_NAME}" <${process.env.EMAIL_FROM}>`,
    to,
    subject,
    html,
  });
  console.log(`✅ Sent — Message ID: ${info.messageId}`);
  transporter.close();
};

(async () => {
  const testEmail = 'hemanthraje7@gmail.com';

  const mockStudent = { _id: '507f1f77bcf86cd799439011', firstName: 'Test', lastName: 'Student', email: testEmail, role: 'student' };
  const mockEvent = { _id: '507f1f77bcf86cd799439012', title: 'Tech Hackathon 2026', date: new Date('2026-06-15'), time: '10:00 AM', venue: 'Main Auditorium', organizerName: 'Dr. Sharma' };
  const mockChanges = [
    { field: 'Venue', oldValue: 'Room 101', newValue: 'Main Auditorium' },
    { field: 'Date', oldValue: 'June 20', newValue: 'June 15' },
  ];
  const mockAdmin = { _id: '507f1f77bcf86cd799439013', firstName: 'Admin', lastName: 'User', email: 'admin@campuscore.com' };
  const mockUser = { _id: '507f1f77bcf86cd799439014', firstName: 'John', lastName: 'Doe', email: testEmail };

  console.log('\n--- Test 1: Event Registration Confirmation ---');
  await send(testEmail, `✅ You're registered for ${mockEvent.title} — CampusCore`,
    templates.eventRegistrationConfirmation({ student: mockStudent, event: mockEvent }));

  await delay(3000);

  console.log('\n--- Test 2: Event Update Notification ---');
  await send(testEmail, `🔔 Update for "${mockEvent.title}" — CampusCore`,
    templates.eventUpdateNotification({ event: mockEvent, changes: mockChanges }));

  await delay(3000);

  console.log('\n--- Test 3: Admin Audit Log ---');
  await send(testEmail, `🛡️ Audit: Admin edited Organizer's profile`,
    templates.organizerEditAuditForAdmins({ actingAdmin: mockAdmin, organizer: mockUser, changes: mockChanges }));

  await delay(3000);

  console.log('\n--- Test 4: Profile Edited (to Organizer) ---');
  await send(testEmail, `📝 Your CampusCore profile was updated by an Admin`,
    templates.profileEditedForOrganizer({ organizer: mockUser, actingAdmin: mockAdmin, changes: mockChanges }));

  await delay(3000);

  console.log('\n--- Test 5: Force Password Reset ---');
  await send(testEmail, `🔐 Your CampusCore password was reset by an Administrator`,
    templates.forcePasswordReset({ user: mockUser, actingAdmin: mockAdmin, resetLink: `${process.env.FRONTEND_URL}/reset-password?token=test123` }));

  await delay(3000);

  console.log('\n--- Test 6: New User Registration Alert ---');
  await send(testEmail, `👤 New student registered — Test Student`,
    templates.newUserRegistrationAlert({ newUser: mockStudent }));

  console.log('\n✅ All 6 templates sent — check your inbox at hemanthraje7@gmail.com');
})();
