const path = require("path");

function safeFileName(fileName, fallback) {
  return path.basename(fileName || fallback || "file");
}

function projectBasePath({ userId, projectId, offeringId }) {
  if (offeringId) {
    return `users/${userId}/projects/${projectId}/offerings/${offeringId}`;
  }

  return `users/${userId}/projects/${projectId}`;
}

function uploadedImageBlobPath({ userId, projectId, offeringId, fileName }) {
  return `${projectBasePath({ userId, projectId, offeringId })}/uploads/${safeFileName(fileName, "original-image.jpeg")}`;
}

function selectedImageBlobPath({ userId, projectId, offeringId, fileName }) {
  return `${projectBasePath({ userId, projectId, offeringId })}/selected/${safeFileName(fileName, "selected-for-video.jpeg")}`;
}

function finalVideoBlobPath({ userId, projectId, offeringId, fileName }) {
  return `${projectBasePath({ userId, projectId, offeringId })}/videos/${safeFileName(fileName, "final-video.mp4")}`;
}

module.exports = {
  uploadedImageBlobPath,
  selectedImageBlobPath,
  finalVideoBlobPath,
};