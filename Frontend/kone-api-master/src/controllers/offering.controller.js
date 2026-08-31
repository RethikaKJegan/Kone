const fs = require('fs');
const path = require('path');
const httpStatus = require('http-status');
const catchAsync = require('../utils/catchAsync');
const ApiError = require('../utils/ApiError');
const { offeringService, projectService, brochureService, brochureIntegrationService, activityLogService } = require('../services');

const fsPromises = fs.promises;
const storageRoot = path.resolve(__dirname, '..', '..', 'storage');
const storagePublicUrl = (filePath) => {
  if (!filePath) return null;
  const resolved = path.resolve(filePath);
  if (!resolved.startsWith(storageRoot)) return null;
  return `/storage/${path.relative(storageRoot, resolved).split(path.sep).join('/')}`;
};

const getRequestMeta = (req) => ({
  ipAddress: req.ip,
  userAgent: req.get('user-agent') || null,
});

const getImageIdFromOffering = (offering) => {
  if (offering.imageId) return offering.imageId;
  if (!offering.inputImagePath) return null;
  const parts = offering.inputImagePath.split('/').filter(Boolean);
  const uploadsIndex = parts.lastIndexOf('uploads');
  if (uploadsIndex === -1 || !parts[uploadsIndex + 1]) return null;
  return parts[uploadsIndex + 1];
};

const exists = async (filePath) => {
  try {
    await fsPromises.access(filePath);
    return true;
  } catch {
    return false;
  }
};

const readJsonIfExists = async (filePath) => {
  try {
    return JSON.parse(await fsPromises.readFile(filePath, 'utf8'));
  } catch {
    return null;
  }
};

const validPlacementGeometry = (preprocessing) => {
  const geometry = preprocessing?.geometry;
  const originalWidth = Number(geometry?.original_size?.width);
  const originalHeight = Number(geometry?.original_size?.height);
  const matrix = geometry?.working_to_original;
  if (
    !Number.isFinite(originalWidth) ||
    originalWidth <= 0 ||
    !Number.isFinite(originalHeight) ||
    originalHeight <= 0 ||
    !Array.isArray(matrix) ||
    matrix.length !== 3
  ) {
    return null;
  }
  const normalizedMatrix = matrix.map((row) => (Array.isArray(row) ? row.map(Number) : []));
  if (normalizedMatrix.some((row) => row.length !== 3 || row.some((value) => !Number.isFinite(value)))) {
    return null;
  }
  return { originalWidth, originalHeight, workingToOriginal: normalizedMatrix };
};

const transformPlacementPoint = (matrix, x, y) => {
  const q0 = matrix[0][0] * x + matrix[0][1] * y + matrix[0][2];
  const q1 = matrix[1][0] * x + matrix[1][1] * y + matrix[1][2];
  const q2 = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2];
  if (!Number.isFinite(q0) || !Number.isFinite(q1) || !Number.isFinite(q2) || Math.abs(q2) < 1e-12) return null;
  return [q0 / q2, q1 / q2];
};

const clampPlacementCoordinate = (value, min, max) => Math.max(min, Math.min(max, value));

const placementBboxToOriginal = (bbox, geometry) => {
  if (!geometry) return null;
  const [x1, y1, x2, y2] = bbox;
  const points = [
    transformPlacementPoint(geometry.workingToOriginal, x1, y1),
    transformPlacementPoint(geometry.workingToOriginal, x2, y1),
    transformPlacementPoint(geometry.workingToOriginal, x2, y2),
    transformPlacementPoint(geometry.workingToOriginal, x1, y2),
  ];
  if (points.some((point) => !point)) return null;
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  const ox1 = clampPlacementCoordinate(Math.min(...xs), 0, geometry.originalWidth);
  const oy1 = clampPlacementCoordinate(Math.min(...ys), 0, geometry.originalHeight);
  const ox2 = clampPlacementCoordinate(Math.max(...xs), 0, geometry.originalWidth);
  const oy2 = clampPlacementCoordinate(Math.max(...ys), 0, geometry.originalHeight);
  if (ox2 <= ox1 || oy2 <= oy1) return null;
  return [ox1, oy1, ox2, oy2];
};

const componentPinsFromPlacement = async (storageDir) => {
  const placements = await readJsonIfExists(path.join(storageDir, 'pipeline', 'component_placements.json'));
  if (!Array.isArray(placements)) return [];
  const detections = await readJsonIfExists(path.join(storageDir, 'pipeline', 'elevator_detections.json'));
  const preprocessing = await readJsonIfExists(path.join(storageDir, 'pipeline', 'preprocessing.json'));
  const geometry = validPlacementGeometry(preprocessing);
  const legacyWidth = Number(detections?.metadata?.image_width) || 0;
  const legacyHeight = Number(detections?.metadata?.image_height) || 0;
  if ((!legacyWidth || !legacyHeight) && !geometry) return [];

  const supported = new Set(['kds', 'kds_2', 'kds_3', 'dcs1020', 'lci', 'cop', 'door', 'ceiling']);
  return placements
    .map((placement) => {
      const componentKey = String(placement.id || '').toLowerCase();
      if (!supported.has(componentKey)) return null;
      const bbox = placement.final_insertion_bbox || placement.final_component_placement?.bbox || placement.inpaint_bbox;
      if (!Array.isArray(bbox) || bbox.length !== 4) return null;
      const [x1, y1, x2, y2] = bbox.map(Number);
      if (![x1, y1, x2, y2].every(Number.isFinite)) return null;
      const rawBbox = [x1, y1, x2, y2];
      const transformedBbox = placementBboxToOriginal(rawBbox, geometry);
      const pinBbox = transformedBbox || rawBbox;
      const pinWidth = transformedBbox ? geometry.originalWidth : legacyWidth;
      const pinHeight = transformedBbox ? geometry.originalHeight : legacyHeight;
      if (!pinWidth || !pinHeight) return null;
      return {
        componentKey,
        x: Math.round(((pinBbox[0] + pinBbox[2]) / 2 / pinWidth) * 100),
        y: Math.round(((pinBbox[1] + pinBbox[3]) / 2 / pinHeight) * 100),
        aiPlaced: true,
        bbox: pinBbox,
        imageWidth: pinWidth,
        imageHeight: pinHeight,
        editableLayerUrl: storagePublicUrl(placement.editable_layer_path),
        repinBackgroundUrl: storagePublicUrl(placement.repin_background_path),
        repinBackgroundDisplayUrl: storagePublicUrl(placement.repin_background_web_path || placement.repin_background_path),
      };
    })
    .filter(Boolean);
};



const hydratePlacementPins = async (offering, userId) => {
  const pins = Array.isArray(offering.componentPins) ? offering.componentPins : [];
  if (pins.some((pin) => Array.isArray(pin.bbox) && pin.bbox.length === 4)) return offering;
  const imageId = getImageIdFromOffering(offering);
  if (!imageId) return offering;
  const storageDir = path.join(__dirname, '..', '..', 'storage', 'auth', String(userId), imageId);
  const recoveredPins = await componentPinsFromPlacement(storageDir);
  if (!recoveredPins.length) return offering;
  offering.componentPins = recoveredPins;
  await offering.save();
  return offering;
};

const assertProjectAccess = async (projectId, userId) => {
  const project = await projectService.getProjectById(projectId);
  if (!project) throw new ApiError(httpStatus.NOT_FOUND, 'Project not found');
  if (project.userId.toString() !== userId) {
    throw new ApiError(httpStatus.FORBIDDEN, 'Forbidden');
  }
  return project;
};

const assertOfferingAccess = async (offeringId, userId) => {
  const offering = await offeringService.getOfferingById(offeringId);
  if (!offering) throw new ApiError(httpStatus.NOT_FOUND, 'Offering not found');
  await assertProjectAccess(offering.projectId, userId);
  return offering;
};

const assertVisualizationAccess = async (projectId, visualizationId, userId) => {
  const project = await assertProjectAccess(projectId, userId);
  const offering = await offeringService.getOfferingById(visualizationId);
  if (!offering || offering.projectId.toString() !== projectId) {
    throw new ApiError(httpStatus.NOT_FOUND, 'Visualization not found');
  }
  return { project, offering };
};

const createOffering = catchAsync(async (req, res) => {
  await assertProjectAccess(req.params.projectId, req.user.id);
  const offering = await offeringService.createOffering(req.params.projectId);
  await projectService.setLastOpenedOffering(req.params.projectId, offering.id);
  await projectService.refreshProjectStatus(req.params.projectId);
  await activityLogService.createActivityLog({
    userId: req.user.id,
    projectId: req.params.projectId,
    offeringId: offering.id,
    action: 'created_offering',
    step: 1,
    ...getRequestMeta(req),
  });
  res.status(httpStatus.CREATED).send(offering);
});

const getOfferings = catchAsync(async (req, res) => {
  await assertProjectAccess(req.params.projectId, req.user.id);
  const offerings = await offeringService.getOfferingsByProject(req.params.projectId);
  await Promise.all(offerings.map((offering) => hydratePlacementPins(offering, req.user.id)));
  res.send(offerings);
});

const getOffering = catchAsync(async (req, res) => {
  const offering = await assertOfferingAccess(req.params.offeringId, req.user.id);
  await hydratePlacementPins(offering, req.user.id);
  res.send(offering);
});

const updateOffering = catchAsync(async (req, res) => {
  const existing = await assertOfferingAccess(req.params.offeringId, req.user.id);
  const offering = await offeringService.updateOffering(req.params.offeringId, req.body);
  if (!offering) throw new ApiError(httpStatus.NOT_FOUND, 'Offering not found');
  await projectService.setLastOpenedOffering(existing.projectId, offering.id);
  await projectService.refreshProjectStatus(existing.projectId);
  await activityLogService.createActivityLog({
    userId: req.user.id,
    projectId: existing.projectId,
    offeringId: offering.id,
    action: 'updated_offering',
    step: offering.savedStep,
    metadata: {
      fields: Object.keys(req.body),
    },
    ...getRequestMeta(req),
  });
  res.send(offering);
});

const updateVisualization = catchAsync(async (req, res) => {
  const { project, offering } = await assertVisualizationAccess(
    req.params.projectId,
    req.params.visualizationId,
    req.user.id
  );
  const updated = await offeringService.updateOffering(offering.id, { name: req.body.name });
  if (!updated) throw new ApiError(httpStatus.NOT_FOUND, 'Visualization not found');
  await projectService.setLastOpenedOffering(project.id, updated.id);
  await projectService.refreshProjectStatus(project.id);
  await activityLogService.createActivityLog({
    userId: req.user.id,
    projectId: project.id,
    offeringId: updated.id,
    action: 'renamed_visualization',
    step: updated.savedStep,
    metadata: { name: req.body.name },
    ...getRequestMeta(req),
  });
  res.send(updated);
});

const deleteVisualization = catchAsync(async (req, res) => {
  const { project, offering } = await assertVisualizationAccess(
    req.params.projectId,
    req.params.visualizationId,
    req.user.id
  );
  await offeringService.deleteOffering(offering.id, project.name);
  await brochureService.deleteBrochureByOfferingId(offering.id);
  if (String(project.lastOpenedOfferingId || '') === String(offering.id)) {
    await projectService.setLastOpenedOffering(project.id, null);
  }
  await projectService.refreshProjectStatus(project.id);
  await activityLogService.createActivityLog({
    userId: req.user.id,
    projectId: project.id,
    offeringId: offering.id,
    action: 'deleted_visualization',
    step: offering.savedStep,
    ...getRequestMeta(req),
  });
  res.status(httpStatus.NO_CONTENT).send();
});

const runAIPlacement = catchAsync(async (req, res) => {
  await assertOfferingAccess(req.params.offeringId, req.user.id);
  const pins = await offeringService.runAIPlacement(req.params.offeringId);
  if (!pins) throw new ApiError(httpStatus.NOT_FOUND, 'Offering not found');
  const offering = await offeringService.getOfferingById(req.params.offeringId);
  await projectService.refreshProjectStatus(offering.projectId);
  await activityLogService.createActivityLog({
    userId: req.user.id,
    projectId: offering.projectId,
    offeringId: offering.id,
    action: 'updated_pins',
    step: 3,
    metadata: { count: pins.length },
    ...getRequestMeta(req),
  });
  res.send(pins);
});

const triggerRender = catchAsync(async (req, res) => {
  const { offeringId } = req.params;
  const offering = await assertOfferingAccess(offeringId, req.user.id);

  let outputImageUrl = null;
  let outputVideoUrl = null;

  const imageId = getImageIdFromOffering(offering);
  const project = await projectService.getProjectById(offering.projectId);
  const projectName = project && project.name ? project.name : 'project';
  const safeName = projectName.replace(/[^a-z0-9]/gi, '_').toLowerCase();
  const destDir = path.join(__dirname, '..', '..', 'output', safeName, offeringId);
  const destImagePath = path.join(destDir, 'final_output.png');
  const destVideoPath = path.join(destDir, 'elevator_animation.mp4');
  const destVideoMetaPath = path.join(destDir, 'elevator_animation.json');

  if (imageId) {
    const srcDir = path.join(__dirname, '..', '..', 'output', imageId);
    try {
      await fsPromises.mkdir(destDir, { recursive: true });
      const files = await fsPromises.readdir(srcDir);
      await Promise.all(files.map((file) => fsPromises.copyFile(path.join(srcDir, file), path.join(destDir, file))));
    } catch (_) {
      // output files not yet generated — proceed without URLs
    }
  }

  if (await exists(destImagePath)) {
    outputImageUrl = `/output/${safeName}/${offeringId}/final_output.png`;
  }
  if (await exists(destVideoPath)) {
    const videoMeta = await readJsonIfExists(destVideoMetaPath);
    const expectedMotion = offering.videoMotionStyle || 'zoom-in';
    const expectedQuality = offering.videoQuality || '1080p';
    if (videoMeta.motion === expectedMotion && videoMeta.quality === expectedQuality) {
      outputVideoUrl = `/output/${safeName}/${offeringId}/elevator_animation.mp4`;
    }
  }

  const updated = await offeringService.triggerRender(offeringId, outputImageUrl, outputVideoUrl);
  if (!updated) throw new ApiError(httpStatus.NOT_FOUND, 'Offering not found');
  await projectService.refreshProjectStatus(updated.projectId);
  await activityLogService.createActivityLog({
    userId: req.user.id,
    projectId: updated.projectId,
    offeringId: updated.id,
    action: outputVideoUrl ? 'generated_video' : 'generated_preview',
    step: updated.savedStep,
    ...getRequestMeta(req),
  });
  res.send(updated);
});

const createBrochureRedirect = catchAsync(async (req, res) => {
  const offering = await assertOfferingAccess(req.params.offeringId, req.user.id);
  const project = await projectService.getProjectById(offering.projectId);
  if (!project) throw new ApiError(httpStatus.NOT_FOUND, 'Project not found');

  const beforePhotoID = offering.uploadedImageBlobPath;
  const afterPhotoID = offering.selectedImageBlobPath;

  if (!beforePhotoID || !afterPhotoID) {
    throw new ApiError(
      httpStatus.BAD_REQUEST,
      'Brochure assets are still syncing. Please wait a moment and try again.'
    );
  }

  const stableProjectId = `${String(project.id || project._id)}_${String(offering.id || offering._id)}`;
  const projectName = `${project.name || 'Project'} - ${offering.name || 'Visualization'}`.slice(0, 256);
  const requestId = req.get('x-request-id') || `brochure-${stableProjectId}`;

  const payload = {
    userId: String(req.user.id),
    userName: req.user.name || undefined,
    projectId: stableProjectId,
    projectName,
    beforePhotoID,
    afterPhotoID,
    ...(offering.finalVideoBlobPath ? { videoID: offering.finalVideoBlobPath } : {}),
  };

  const result = await brochureIntegrationService.createBrochureRedirect(payload, requestId);

  await activityLogService.createActivityLog({
    userId: req.user.id,
    projectId: project.id,
    offeringId: offering.id,
    action: 'generated_brochure_redirect',
    step: 6,
    metadata: {
      brochureProjectId: stableProjectId,
      correlationId: result.correlationId || null,
    },
    ...getRequestMeta(req),
  });

  res.send({
    redirectUrl: result.redirectUrl,
    correlationId: result.correlationId,
    requestId: result.requestId,
  });
});

const completeOffering = catchAsync(async (req, res) => {
  await assertOfferingAccess(req.params.offeringId, req.user.id);
  const offering = await offeringService.completeOffering(req.params.offeringId);
  if (!offering) throw new ApiError(httpStatus.NOT_FOUND, 'Offering not found');
  await projectService.refreshProjectStatus(offering.projectId);
  await activityLogService.createActivityLog({
    userId: req.user.id,
    projectId: offering.projectId,
    offeringId: offering.id,
    action: 'downloaded_output',
    step: 6,
    ...getRequestMeta(req),
  });
  res.send(offering);
});

module.exports = {
  createOffering,
  getOfferings,
  getOffering,
  updateOffering,
  updateVisualization,
  deleteVisualization,
  runAIPlacement,
  triggerRender,
  createBrochureRedirect,
  completeOffering,
};
