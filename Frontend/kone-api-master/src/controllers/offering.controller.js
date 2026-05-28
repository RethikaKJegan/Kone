const fs = require('fs');
const path = require('path');
const httpStatus = require('http-status');
const catchAsync = require('../utils/catchAsync');
const ApiError = require('../utils/ApiError');
const { offeringService, projectService } = require('../services');

const fsPromises = fs.promises;

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

const createOffering = catchAsync(async (req, res) => {
  await assertProjectAccess(req.params.projectId, req.user.id);
  const offering = await offeringService.createOffering(req.params.projectId);
  await projectService.incrementOfferingCount(req.params.projectId, 1);
  res.status(httpStatus.CREATED).send(offering);
});

const getOfferings = catchAsync(async (req, res) => {
  await assertProjectAccess(req.params.projectId, req.user.id);
  const offerings = await offeringService.getOfferingsByProject(req.params.projectId);
  res.send(offerings);
});

const updateOffering = catchAsync(async (req, res) => {
  await assertOfferingAccess(req.params.offeringId, req.user.id);
  const offering = await offeringService.updateOffering(req.params.offeringId, req.body);
  if (!offering) throw new ApiError(httpStatus.NOT_FOUND, 'Offering not found');
  res.send(offering);
});

const runAIPlacement = catchAsync(async (req, res) => {
  await assertOfferingAccess(req.params.offeringId, req.user.id);
  const pins = await offeringService.runAIPlacement(req.params.offeringId);
  if (!pins) throw new ApiError(httpStatus.NOT_FOUND, 'Offering not found');
  res.send(pins);
});

const triggerRender = catchAsync(async (req, res) => {
  const { offeringId } = req.params;
  const offering = await assertOfferingAccess(offeringId, req.user.id);

  let outputImageUrl = null;
  let outputVideoUrl = null;

  if (offering.imageId) {
    const project = await projectService.getProjectById(offering.projectId);
    const projectName = project && project.name ? project.name : 'project';
    const safeName = projectName.replace(/[^a-z0-9]/gi, '_').toLowerCase();

    const srcDir = path.join(__dirname, '..', '..', 'output', offering.imageId);
    const destDir = path.join(__dirname, '..', '..', 'output', safeName, offeringId);

    try {
      await fsPromises.mkdir(destDir, { recursive: true });
      const files = await fsPromises.readdir(srcDir);
      await Promise.all(files.map((file) => fsPromises.rename(path.join(srcDir, file), path.join(destDir, file))));
      await fsPromises.rmdir(srcDir).catch(() => {});
      outputImageUrl = `/output/${safeName}/${offeringId}/final_output.png`;
      outputVideoUrl = `/output/${safeName}/${offeringId}/elevator_animation.mp4`;
    } catch (_) {
      // output files not yet generated — proceed without URLs
    }
  }

  const updated = await offeringService.triggerRender(offeringId, outputImageUrl, outputVideoUrl);
  if (!updated) throw new ApiError(httpStatus.NOT_FOUND, 'Offering not found');
  res.send(updated);
});

const completeOffering = catchAsync(async (req, res) => {
  await assertOfferingAccess(req.params.offeringId, req.user.id);
  const offering = await offeringService.completeOffering(req.params.offeringId);
  if (!offering) throw new ApiError(httpStatus.NOT_FOUND, 'Offering not found');
  res.send(offering);
});

module.exports = {
  createOffering,
  getOfferings,
  updateOffering,
  runAIPlacement,
  triggerRender,
  completeOffering,
};
