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

module.exports = {
  createProject,
  projectId,
};
