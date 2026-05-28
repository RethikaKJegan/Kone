const Joi = require('joi');
const { objectId } = require('./custom.validation');

const componentKeys = ['ceiling', 'lci', 'door', 'cop'];
const environments = ['car', 'lobby'];

const offeringId = {
  params: Joi.object().keys({
    offeringId: Joi.string().custom(objectId).required(),
  }),
};

const updateOffering = {
  params: offeringId.params,
  body: Joi.object()
    .keys({
      name: Joi.string().trim(),
      imageId: Joi.string().allow(null),
      uploadedFileName: Joi.string().allow(null),
      uploadedFileType: Joi.string().valid('image', 'video').allow(null),
      environments: Joi.array().items(Joi.string().valid(...environments)),
      selectedComponents: Joi.array().items(Joi.string().valid(...componentKeys)),
      componentPins: Joi.array().items(
        Joi.object().keys({
          componentKey: Joi.string()
            .valid(...componentKeys)
            .required(),
          x: Joi.number().min(0).max(100).required(),
          y: Joi.number().min(0).max(100).required(),
          aiPlaced: Joi.boolean(),
        })
      ),
      annotationsEnabled: Joi.boolean(),
      activeAnnotationFilters: Joi.array().items(Joi.string().valid(...componentKeys)),
      videoMotionStyle: Joi.string().valid('zoom-in', 'pan-lr', 'pan-rl'),
      videoSpeed: Joi.number().valid(0.5, 1, 1.5),
      videoQuality: Joi.string().valid('360p', '480p', '720p', '1080p'),
    })
    .min(1),
};

module.exports = {
  offeringId,
  updateOffering,
};
