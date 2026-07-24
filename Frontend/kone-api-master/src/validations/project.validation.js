const Joi = require('joi');
const { objectId } = require('./custom.validation');

const createProject = {
  body: Joi.object().keys({
    name: Joi.string().min(2).max(80).required(),
  }),
};

const projectId = {
  params: Joi.object().keys({
    projectId: Joi.string().custom(objectId).required(),
  }),
};

const updateProject = {
  params: projectId.params,
  body: Joi.object().keys({
    name: Joi.string().min(2).max(80).required(),
  }),
};

const visualizationId = {
  params: Joi.object().keys({
    projectId: Joi.string().custom(objectId).required(),
    visualizationId: Joi.string().custom(objectId).required(),
  }),
};

const updateVisualization = {
  params: visualizationId.params,
  body: Joi.object().keys({
    name: Joi.string().min(2).max(80).required(),
  }),
};

module.exports = {
  createProject,
  projectId,
  updateProject,
  visualizationId,
  updateVisualization,
};
