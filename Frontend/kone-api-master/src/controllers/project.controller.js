const httpStatus = require('http-status');
const catchAsync = require('../utils/catchAsync');
const ApiError = require('../utils/ApiError');
const { projectService, activityLogService } = require('../services');

const getRequestMeta = (req) => ({
  ipAddress: req.ip,
  userAgent: req.get('user-agent') || null,
});

const createProject = catchAsync(async (req, res) => {
  const project = await projectService.createProject(req.body.name, req.user.id);
  await activityLogService.createActivityLog({
    userId: req.user.id,
    projectId: project.id,
    action: 'created_project',
    ...getRequestMeta(req),
  });
  res.status(httpStatus.CREATED).send(project);
});

const getProjects = catchAsync(async (req, res) => {
  const projects = await projectService.getProjectsByUser(req.user.id);
  res.send(projects);
});

const updateProject = catchAsync(async (req, res) => {
  const project = await projectService.getProjectById(req.params.projectId);
  if (!project) throw new ApiError(httpStatus.NOT_FOUND, 'Project not found');
  if (project.userId.toString() !== req.user.id) {
    throw new ApiError(httpStatus.FORBIDDEN, 'Forbidden');
  }
  const updated = await projectService.updateProject(req.params.projectId, { name: req.body.name });
  await activityLogService.createActivityLog({
    userId: req.user.id,
    projectId: req.params.projectId,
    action: 'renamed_project',
    metadata: { name: req.body.name },
    ...getRequestMeta(req),
  });
  res.send(updated);
});

const deleteProject = catchAsync(async (req, res) => {
  const project = await projectService.getProjectById(req.params.projectId);
  if (!project) throw new ApiError(httpStatus.NOT_FOUND, 'Project not found');
  if (project.userId.toString() !== req.user.id) {
    throw new ApiError(httpStatus.FORBIDDEN, 'Forbidden');
  }
  await projectService.deleteProject(req.params.projectId);
  await activityLogService.createActivityLog({
    userId: req.user.id,
    projectId: req.params.projectId,
    action: 'deleted_project',
    ...getRequestMeta(req),
  });
  res.status(httpStatus.NO_CONTENT).send();
});

module.exports = {
  createProject,
  getProjects,
  updateProject,
  deleteProject,
};
