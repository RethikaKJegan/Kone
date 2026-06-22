const Project = require('../models/project.model');
const Offering = require('../models/offering.model');
const Brochure = require('../models/brochure.model');
const offeringService = require('./offering.service');

const createProject = async (name, userId) => {
  return Project.create({ name, userId });
};

const getProjectsByUser = async (userId) => {
  const projects = await Project.find({ userId }).sort({ createdAt: -1 });
  return Promise.all(projects.map((project) => refreshProjectStatus(project.id)));
};

const getProjectById = async (id) => {
  return Project.findById(id);
};

const deriveProjectStatus = (offerings) => {
  if (offerings.length === 0) return 'draft';
  if (offerings.every((offering) => offering.status === 'complete')) return 'complete';
  if (offerings.some((offering) => offering.status === 'active' || offering.status === 'complete')) return 'active';
  return 'draft';
};

const refreshProjectStatus = async (projectId) => {
  const offerings = await offeringService.getOfferingsByProject(projectId);
  return Project.findByIdAndUpdate(projectId, { status: deriveProjectStatus(offerings) }, { new: true });
};

const updateProject = async (id, updateBody) => {
  return Project.findByIdAndUpdate(id, updateBody, { new: true });
};

const deleteProject = async (id) => {
  const project = await Project.findByIdAndDelete(id);
  if (!project) return null;
  const offerings = await Offering.find({ projectId: id });
  const offeringIds = offerings.map((offering) => offering._id);
  await Promise.all(offerings.map((offering) => offeringService.deleteOfferingFiles(offering, project.name)));
  await Offering.deleteMany({ projectId: id });
  await Brochure.deleteMany({ $or: [{ projectId: id }, { offeringId: { $in: offeringIds } }] });
  return project;
};

const incrementOfferingCount = async (projectId) => {
  return Project.findById(projectId);
};

const setLastOpenedOffering = async (projectId, offeringId) => {
  return Project.findByIdAndUpdate(projectId, { lastOpenedOfferingId: offeringId }, { new: true });
};

module.exports = {
  createProject,
  getProjectsByUser,
  getProjectById,
  deriveProjectStatus,
  refreshProjectStatus,
  updateProject,
  deleteProject,
  incrementOfferingCount,
  setLastOpenedOffering,
};
