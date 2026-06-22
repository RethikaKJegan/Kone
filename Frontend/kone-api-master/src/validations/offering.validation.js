const Joi = require('joi');
const { objectId } = require('./custom.validation');

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
      status: Joi.string().valid('draft', 'active', 'complete'),
      savedStep: Joi.number().integer().min(1).max(6),
      imageId: Joi.string().allow(null),
      uploadedFileName: Joi.string().allow(null),
      uploadedFileType: Joi.string().valid('image', 'video').allow(null),
      uploadedFileUrl: Joi.string().allow(null),
      inputImagePath: Joi.string().allow(null),
      previewImagePath: Joi.string().allow(null),
      outputImagePath: Joi.string().allow(null),
      outputVideoPath: Joi.string().allow(null),
      downloadZipPath: Joi.string().allow(null),
      environments: Joi.array().items(Joi.string()),
      selectedComponents: Joi.array().items(Joi.string()),
      componentPins: Joi.array().items(
        Joi.object().keys({
          componentKey: Joi.string().required(),
          x: Joi.number().required(),
          y: Joi.number().required(),
          aiPlaced: Joi.boolean(),
        })
      ),
      annotationsEnabled: Joi.boolean(),
      activeAnnotationFilters: Joi.array().items(Joi.string()),
      videoMotionStyle: Joi.string(),
      videoSpeed: Joi.number(),
      videoQuality: Joi.string(),
      pipelineStatus: Joi.string().valid(
        'idle',
        'uploaded',
        'processing',
        'preview_ready',
        'video_ready',
        'ready_for_download',
        'failed'
      ),
      previewRequestKey: Joi.string().allow(null, ''),
      outputImageUrl: Joi.string().allow(null),
      outputVideoUrl: Joi.string().allow(null),
      downloadUrl: Joi.string().allow(null),
      lastError: Joi.string().allow(null),
      renderComplete: Joi.boolean(),
    })
    .min(1),
};

module.exports = {
  offeringId,
  updateOffering,
};
