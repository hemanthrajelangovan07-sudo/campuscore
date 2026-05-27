const mongoose = require('mongoose');

const AdminAuditLogSchema = new mongoose.Schema({
  performedBy: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
  action: {
    type: String,
    enum: [
      'FORCE_PASSWORD_RESET',
      'EDIT_USER_PROFILE',
      'DELETE_USER',
      'CHANGE_USER_ROLE',
    ],
    required: true,
  },
  targetUser: { type: mongoose.Schema.Types.ObjectId, ref: 'User' },
  changes: [{ field: String, oldValue: String, newValue: String }],
  timestamp: { type: Date, default: Date.now },
});

module.exports = mongoose.model('AdminAuditLog', AdminAuditLogSchema);
