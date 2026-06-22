const { ActivityLog } = require('../models');

const createActivityLog = async ({
  userId,
  projectId = null,
  offeringId = null,
  action,
  step = null,
  metadata = {},
  ipAddress = null,
  userAgent = null,
}) => {
  return ActivityLog.create({
    userId,
    projectId,
    offeringId,
    action,
    step,
    metadata,
    ipAddress,
    userAgent,
  });
};

module.exports = {
  createActivityLog,
};
