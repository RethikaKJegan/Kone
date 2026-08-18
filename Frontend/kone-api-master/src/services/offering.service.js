const fs = require('fs');
const path = require('path');
const Offering = require('../models/offering.model');

const fsPromises = fs.promises;

const AI_PLACEMENT_DEFAULTS = {
  ceiling: { x: 50, y: 15 },
  lci: { x: 20, y: 50 },
  door: { x: 80, y: 60 },
  cop: { x: 35, y: 70 },
};

const createOffering = async (projectId) => {
  const existing = await Offering.findOne({ projectId }).sort({ createdAt: -1 });
  if (existing) return normalizeOfferingStatus(existing);
  return Offering.create({ projectId });
};

const deriveOfferingStatus = (offering) => {
  if (
    offering.status === 'complete' ||
    offering.pipelineStatus === 'ready_for_download' ||
    offering.downloadUrl ||
    (offering.savedStep || 1) >= 6
  ) {
    return 'complete';
  }

  if (
    offering.status === 'active' ||
    offering.imageId ||
    offering.inputImagePath ||
    offering.previewImagePath ||
    offering.outputImagePath ||
    offering.outputVideoPath ||
    offering.outputImageUrl ||
    offering.outputVideoUrl ||
    offering.uploadedFileName ||
    (offering.environments || []).length > 0 ||
    (offering.selectedComponents || []).length > 0 ||
    (offering.componentPins || []).length > 0 ||
    (offering.savedStep || 1) > 1 ||
    ['uploaded', 'processing', 'preview_ready', 'video_ready'].includes(offering.pipelineStatus)
  ) {
    return 'active';
  }

  return 'draft';
};

const normalizeOfferingStatus = async (offering) => {
  if (!offering) return offering;
  const status = deriveOfferingStatus(offering);
  if (offering.status === status) return offering;
  offering.status = status;
  return offering.save();
};

const getOfferingsByProject = async (projectId) => {
  const offering = await Offering.findOne({ projectId }).sort({ createdAt: -1 });
  if (!offering) return [];
  return [await normalizeOfferingStatus(offering)];
};

const getOfferingById = async (id) => {
  const offering = await Offering.findById(id);
  return normalizeOfferingStatus(offering);
};

const removeDir = async (dir) => {
  if (!dir) return;
  await fsPromises.rm(dir, { recursive: true, force: true }).catch(() => {});
};

const imageIdFromOffering = (offering) => {
  if (offering.imageId) return offering.imageId;
  const match = String(offering.inputImagePath || '').match(/\/uploads\/([^/]+)\/input\.jpg(?:\?.*)?$/);
  return match?.[1] || null;
};

const deleteOfferingFiles = async (offering, projectName = null) => {
  const root = path.join(__dirname, '..', '..');
  const imageId = imageIdFromOffering(offering);
  if (imageId) {
    await removeDir(path.join(root, 'uploads', imageId));
    await removeDir(path.join(root, 'output', imageId));
    const authStorageRoot = path.join(root, 'storage', 'auth');
    const userDirs = await fsPromises.readdir(authStorageRoot).catch(() => []);
    await Promise.all(userDirs.map((userDir) => removeDir(path.join(authStorageRoot, userDir, imageId))));
  }

  if (projectName) {
    const safeName = projectName.replace(/[^a-z0-9]/gi, '_').toLowerCase();
    await removeDir(path.join(root, 'output', safeName, String(offering.id || offering._id)));
  }
};

const updateOffering = async (id, updateBody) => {
  const allowedBody = { ...updateBody };

  if (allowedBody.imageId) {
    allowedBody.inputImagePath = `/uploads/${allowedBody.imageId}/input.jpg`;
    allowedBody.pipelineStatus = allowedBody.pipelineStatus || 'uploaded';
  }

  if (allowedBody.uploadedFileUrl) {
    allowedBody.previewImagePath = allowedBody.uploadedFileUrl;
    delete allowedBody.uploadedFileUrl;
  }

  if (allowedBody.renderComplete !== undefined && allowedBody.pipelineStatus === undefined) {
    allowedBody.pipelineStatus = allowedBody.renderComplete ? 'preview_ready' : 'idle';
  }
  if (allowedBody.renderComplete !== undefined) {
    delete allowedBody.renderComplete;
  }

  if (allowedBody.videoMotionStyle || allowedBody.videoQuality) {
    const existing = await Offering.findById(id).select('videoMotionStyle videoQuality');
    const motionChanged =
      allowedBody.videoMotionStyle !== undefined &&
      existing &&
      allowedBody.videoMotionStyle !== existing.videoMotionStyle;
    const qualityChanged =
      allowedBody.videoQuality !== undefined &&
      existing &&
      allowedBody.videoQuality !== existing.videoQuality;

    if (motionChanged || qualityChanged || allowedBody.pipelineStatus === 'processing') {
      allowedBody.outputVideoUrl = null;
      allowedBody.outputVideoPath = null;
      allowedBody.downloadUrl = null;
    }
  }

  if (
    !allowedBody.status &&
    (allowedBody.imageId ||
      allowedBody.uploadedFileUrl ||
      (Array.isArray(allowedBody.environments) && allowedBody.environments.length > 0) ||
      (Array.isArray(allowedBody.selectedComponents) && allowedBody.selectedComponents.length > 0) ||
      ['uploaded', 'processing', 'preview_ready', 'video_ready'].includes(allowedBody.pipelineStatus))
  ) {
    allowedBody.status = 'active';
  }

  return Offering.findByIdAndUpdate(id, allowedBody, { new: true });
};

const deleteOffering = async (id, projectName = null) => {
  const offering = await Offering.findById(id);
  if (!offering) return null;
  await deleteOfferingFiles(offering, projectName);
  return Offering.findByIdAndDelete(id);
};

const runAIPlacement = async (id) => {
  const offering = await Offering.findById(id);
  if (!offering) return null;

  const pins = offering.selectedComponents.map((key) => ({
    componentKey: key,
    x: AI_PLACEMENT_DEFAULTS[key] ? AI_PLACEMENT_DEFAULTS[key].x : 50,
    y: AI_PLACEMENT_DEFAULTS[key] ? AI_PLACEMENT_DEFAULTS[key].y : 50,
    aiPlaced: true,
  }));

  offering.componentPins = pins;
  offering.savedStep = Math.max(offering.savedStep || 1, 3);
  if (offering.status !== 'complete') {
    offering.status = 'active';
  }
  await offering.save();
  return pins;
};

const triggerRender = async (id, outputImageUrl = null, outputVideoUrl = null) => {
  const existing = await Offering.findById(id);
  if (!existing) return null;

  const waitingForVideo =
    existing.pipelineStatus === 'processing' &&
    (existing.savedStep || 1) >= 5 &&
    !outputVideoUrl;
  const failedVideo =
    existing.pipelineStatus === 'failed' &&
    (existing.savedStep || 1) >= 5 &&
    !outputVideoUrl;

  const update = {
    savedStep: outputVideoUrl
      ? Math.max(existing.savedStep || 1, 5)
      : waitingForVideo || failedVideo
        ? existing.savedStep
        : Math.max(existing.savedStep || 1, 4),
    pipelineStatus: outputVideoUrl
      ? 'video_ready'
      : waitingForVideo
        ? 'processing'
        : failedVideo
          ? 'failed'
          : 'preview_ready',
    status: 'active',
  };

  if (failedVideo && existing.lastError) {
    update.lastError = existing.lastError;
  }

  if (!outputVideoUrl && !waitingForVideo && (existing.savedStep || 1) >= 5) {
    update.outputVideoUrl = null;
    update.outputVideoPath = null;
    update.downloadUrl = null;
  }
  if (outputImageUrl) {
    update.outputImageUrl = outputImageUrl;
    update.outputImagePath = outputImageUrl;
  }
  if (outputVideoUrl) {
    update.outputVideoUrl = outputVideoUrl;
    update.outputVideoPath = outputVideoUrl;
  }
  return Offering.findByIdAndUpdate(id, update, { new: true });
};

const completeOffering = async (id) => {
  return Offering.findByIdAndUpdate(
    id,
    { status: 'complete', savedStep: 6, pipelineStatus: 'ready_for_download' },
    { new: true }
  );
};

module.exports = {
  createOffering,
  getOfferingsByProject,
  getOfferingById,
  updateOffering,
  deleteOffering,
  deleteOfferingFiles,
  runAIPlacement,
  triggerRender,
  completeOffering,
};
