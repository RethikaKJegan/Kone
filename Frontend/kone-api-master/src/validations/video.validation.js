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

const repinTransform = Joi.object().keys({
  componentKey: Joi.string().valid('ceiling', 'lci', 'door', 'cop').required(),
  componentType: Joi.string().valid('ceiling', 'lci', 'door', 'cop').required(),
  sourceVersion: Joi.number().integer().min(1).max(5).required(),
  targetVersion: Joi.number().integer().min(2).max(5).required(),
  x: Joi.number().required(),
  y: Joi.number().required(),
  width: Joi.number().positive().required(),
  height: Joi.number().positive().required(),
  rotation: Joi.number().required(),
  skewX: Joi.number().required(),
  skewY: Joi.number().required(),
  perspective: Joi.array().items(Joi.object({ x: Joi.number().required(), y: Joi.number().required() })).length(4).default([]),
  feedbackOption: Joi.string().valid('wrong_placement', 'wrong_component', 'bad_perspective', 'bad_lighting_shadow', 'poor_blending_unrealistic').allow(null),
});

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

const repinPreview = {
  body: Joi.object().keys({
    imageId: Joi.string().required(),
    offeringId: Joi.string().required(),
    components: Joi.array().items(Joi.string().valid('ceiling', 'lci', 'door', 'cop')).default([]),
    environments: Joi.array().items(Joi.string().valid('car', 'lobby')).default([]),
    component_assets: Joi.object().pattern(Joi.string(), Joi.string()).default({}),
    preview_request_key: Joi.string().allow(null, ''),
    transform: repinTransform.required(),
  }),
};

module.exports = {
  imageIdBody,
  selectEnvironment,
  selectComponents,
  repinPreview,
};
