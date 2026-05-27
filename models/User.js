const mongoose = require('mongoose');

const UserSchema = new mongoose.Schema({
  firstName: { type: String, required: true },
  lastName: { type: String, required: true },
  email: { type: String, required: true, unique: true },
  password: { type: String, required: true },
  role: { type: String, enum: ['student', 'organizer', 'admin'], default: 'student' },
  college: { type: String },
  preferences: {
    emailNotifications: { type: Boolean, default: true },
  },
  passwordResetToken: { type: String },
  passwordResetExpiry: { type: Date },
  forcePasswordChange: { type: Boolean, default: false },
}, { timestamps: true });

module.exports = mongoose.model('User', UserSchema);
