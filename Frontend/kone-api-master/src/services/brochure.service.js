const Brochure = require('../models/brochure.model');

const CONTENT_FIELDS = [
  'offeringOverview',
  'competitorComparison',
  'uniqueSellingPoints',
  'customerBenefits',
  'additionalNotes',
];

const getBrochureByOfferingId = async (offeringId) => {
  return Brochure.findOne({ offeringId });
};

const createBrochure = async (offeringId, projectId) => {
  const existing = await Brochure.findOne({ offeringId });
  if (existing) return existing;
  return Brochure.create({ offeringId, projectId });
};

const updateBrochure = async (offeringId, contentUpdates) => {
  const brochure = await Brochure.findOne({ offeringId });
  if (!brochure) return null;

  if (contentUpdates) {
    Object.assign(brochure.content, contentUpdates);
    brochure.markModified('content');
  }

  brochure.sectionsComplete = CONTENT_FIELDS.filter((f) => {
    const value = brochure.content[f];
    return value && value.trim().length > 0;
  }).length;

  await brochure.save();
  return brochure;
};

module.exports = {
  getBrochureByOfferingId,
  createBrochure,
  updateBrochure,
};
