const mongoose = require('mongoose');

const EmailLogSchema = new mongoose.Schema({
  recipientEmail: { type: String, required: true },
  subject: { type: String, required: true },
  type: {
    type: String,
    enum: [
      'EVENT_REGISTRATION_CONFIRMATION',
      'EVENT_UPDATE_NOTIFICATION',
      'ORGANIZER_EDIT_AUDIT_ADMIN',
      'PROFILE_EDITED_ORGANIZER',
      'FORCE_PASSWORD_RESET',
      'NEW_USER_REGISTRATION_ALERT',
    ],
  },
  status: { type: String, enum: ['sent', 'failed'], default: 'sent' },
  error: { type: String },
  sentAt: { type: Date, default: Date.now },
});

module.exports = mongoose.model('EmailLog', EmailLogSchema);
