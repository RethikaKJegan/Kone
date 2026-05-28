const httpStatus = require('http-status');
const catchAsync = require('../utils/catchAsync');
const ApiError = require('../utils/ApiError');
const { brochureService, offeringService, projectService } = require('../services');

const assertOfferingAccess = async (offeringId, userId) => {
  const offering = await offeringService.getOfferingById(offeringId);
  if (!offering) throw new ApiError(httpStatus.NOT_FOUND, 'Offering not found');
  const project = await projectService.getProjectById(offering.projectId);
  if (!project) throw new ApiError(httpStatus.NOT_FOUND, 'Project not found');
  if (project.userId.toString() !== userId) {
    throw new ApiError(httpStatus.FORBIDDEN, 'Forbidden');
  }
  return offering;
};

const getBrochure = catchAsync(async (req, res) => {
  await assertOfferingAccess(req.params.offeringId, req.user.id);
  const brochure = await brochureService.getBrochureByOfferingId(req.params.offeringId);
  if (!brochure) throw new ApiError(httpStatus.NOT_FOUND, 'Brochure not found');
  res.send(brochure);
});

const createBrochure = catchAsync(async (req, res) => {
  const offering = await assertOfferingAccess(req.params.offeringId, req.user.id);
  if (offering.projectId.toString() !== req.body.projectId) {
    throw new ApiError(httpStatus.BAD_REQUEST, 'Brochure project must match offering project');
  }
  const brochure = await brochureService.createBrochure(req.params.offeringId, req.body.projectId);
  res.status(httpStatus.CREATED).send(brochure);
});

const updateBrochure = catchAsync(async (req, res) => {
  await assertOfferingAccess(req.params.offeringId, req.user.id);
  const brochure = await brochureService.updateBrochure(req.params.offeringId, req.body.content);
  if (!brochure) throw new ApiError(httpStatus.NOT_FOUND, 'Brochure not found');
  res.send(brochure);
});

module.exports = {
  getBrochure,
  createBrochure,
  updateBrochure,
};
