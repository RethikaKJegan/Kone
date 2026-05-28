const Project = require('../models/project.model');
const Offering = require('../models/offering.model');
const Brochure = require('../models/brochure.model');

const createProject = async (name, userId) => {
  return Project.create({ name, userId });
};

const getProjectsByUser = async (userId) => {
  return Project.find({ userId }).sort({ createdAt: -1 });
};

const getProjectById = async (id) => {
  return Project.findById(id);
};

const deleteProject = async (id) => {
  const project = await Project.findByIdAndDelete(id);
  if (!project) return null;
  const offerings = await Offering.find({ projectId: id }).select('_id');
  const offeringIds = offerings.map((offering) => offering._id);
  await Offering.deleteMany({ projectId: id });
  await Brochure.deleteMany({ $or: [{ projectId: id }, { offeringId: { $in: offeringIds } }] });
  return project;
};

const incrementOfferingCount = async (projectId, delta = 1) => {
  await Project.findByIdAndUpdate(projectId, { $inc: { offeringCount: delta } });
};

module.exports = {
  createProject,
  getProjectsByUser,
  getProjectById,
  deleteProject,
  incrementOfferingCount,
};
