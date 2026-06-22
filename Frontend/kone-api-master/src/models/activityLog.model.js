const mongoose = require('mongoose');
const { toJSON, paginate } = require('./plugins');

const activityLogSchema = mongoose.Schema(
  {
    userId: {
      type: mongoose.SchemaTypes.ObjectId,
      ref: 'User',
      required: true,
      index: true,
    },
    projectId: {
      type: mongoose.SchemaTypes.ObjectId,
      ref: 'Project',
      default: null,
      index: true,
    },
    offeringId: {
      type: mongoose.SchemaTypes.ObjectId,
      ref: 'Offering',
      default: null,
      index: true,
    },
    action: {
      type: String,
      required: true,
      trim: true,
      index: true,
    },
    step: {
      type: Number,
      min: 1,
      max: 6,
      default: null,
    },
    metadata: {
      type: mongoose.SchemaTypes.Mixed,
      default: {},
    },
    ipAddress: {
      type: String,
      default: null,
    },
    userAgent: {
      type: String,
      default: null,
    },
  },
  {
    timestamps: { createdAt: true, updatedAt: false },
  }
);

activityLogSchema.plugin(toJSON);
activityLogSchema.plugin(paginate);

const ActivityLog = mongoose.model('ActivityLog', activityLogSchema, 'activity_logs');

module.exports = ActivityLog;
