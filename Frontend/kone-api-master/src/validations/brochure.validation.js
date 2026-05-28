const Joi = require('joi');
const { objectId } = require('./custom.validation');

const brochureParams = {
  params: Joi.object().keys({
    offeringId: Joi.string().custom(objectId).required(),
  }),
};

const createBrochure = {
  params: brochureParams.params,
  body: Joi.object().keys({
    projectId: Joi.string().custom(objectId).required(),
  }),
};

const updateBrochure = {
  params: brochureParams.params,
  body: Joi.object().keys({
    content: Joi.object()
      .keys({
        offeringOverview: Joi.string().allow(''),
        competitorComparison: Joi.string().allow(''),
        uniqueSellingPoints: Joi.string().allow(''),
        customerBenefits: Joi.string().allow(''),
        additionalNotes: Joi.string().allow(''),
      })
      .min(1)
      .required(),
  }),
};

module.exports = {
  brochureParams,
  createBrochure,
  updateBrochure,
};
