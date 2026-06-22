const Joi = require('joi');

const imageIdBody = {
  body: Joi.object().keys({
    imageId: Joi.string().required(),
    sourceImageUrl: Joi.string(),
    videoOptions: Joi.object().unknown(true),
  }),
};

const selectEnvironment = {
  body: Joi.object().keys({
    imageId: Joi.string().required(),
    environment: Joi.string().valid('car', 'lobby').required(),
  }),
};

const selectComponents = {
  body: Joi.object().keys({
    imageId: Joi.string().required(),
    offeringId: Joi.string().required(),
    components: Joi.array().items(Joi.string().valid('ceiling', 'lci', 'door', 'cop')).min(1).required(),
    environments: Joi.array().items(Joi.string().valid('car', 'lobby')).default([]),
    component_assets: Joi.object().pattern(Joi.string(), Joi.string()).default({}),
    preview_request_key: Joi.string().allow(null, ''),
  }),
};

module.exports = {
  imageIdBody,
  selectEnvironment,
  selectComponents,
};
