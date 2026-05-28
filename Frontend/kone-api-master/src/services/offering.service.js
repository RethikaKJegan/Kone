const Offering = require('../models/offering.model');

const AI_PLACEMENT_DEFAULTS = {
  ceiling: { x: 50, y: 15 },
  lci: { x: 20, y: 50 },
  door: { x: 80, y: 60 },
  cop: { x: 35, y: 70 },
};

const createOffering = async (projectId) => {
  return Offering.create({ projectId });
};

const getOfferingsByProject = async (projectId) => {
  return Offering.find({ projectId }).sort({ createdAt: -1 });
};

const getOfferingById = async (id) => {
  return Offering.findById(id);
};

const updateOffering = async (id, updateBody) => {
  return Offering.findByIdAndUpdate(id, updateBody, { new: true });
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
  await offering.save();
  return pins;
};

const triggerRender = async (id, outputImageUrl = null, outputVideoUrl = null) => {
  const update = { renderComplete: true };
  if (outputImageUrl) update.outputImageUrl = outputImageUrl;
  if (outputVideoUrl) update.outputVideoUrl = outputVideoUrl;
  return Offering.findByIdAndUpdate(id, update, { new: true });
};

const completeOffering = async (id) => {
  return Offering.findByIdAndUpdate(id, { status: 'complete' }, { new: true });
};

module.exports = {
  createOffering,
  getOfferingsByProject,
  getOfferingById,
  updateOffering,
  runAIPlacement,
  triggerRender,
  completeOffering,
};
