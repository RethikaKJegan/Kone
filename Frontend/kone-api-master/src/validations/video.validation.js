const Joi = require('joi');

const imageIdBody = {
  body: Joi.object().keys({
    imageId: Joi.string().required(),
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
    components: Joi.array().items(Joi.string().valid('ceiling', 'lci', 'door', 'cop')).min(1).required(),
  }),
};

module.exports = {
  imageIdBody,
  selectEnvironment,
  selectComponents,
};
