const Joi = require('joi');
const { objectId } = require('./custom.validation');

const repinPoint = Joi.object().keys({
  x: Joi.number().required(),
  y: Joi.number().required(),
});

const eraserHistoryEntry = Joi.object().keys({
  repinBackgroundUrl: Joi.string().allow(null, ''),
  repinBackgroundDisplayUrl: Joi.string().allow(null, ''),
});

const repinTransform = Joi.object().keys({
  componentKey: Joi.string().valid('ceiling', 'lci', 'door', 'cop').required(),
  componentType: Joi.string().valid('ceiling', 'lci', 'door', 'cop').required(),
  sourceVersion: Joi.number().integer().min(1).max(5).required(),
  targetVersion: Joi.number().integer().min(2).max(5).required(),
  x: Joi.number().required(),
  y: Joi.number().required(),
  width: Joi.number().positive().required(),
  height: Joi.number().positive().required(),
  rotation: Joi.number().default(0),
  skewX: Joi.number().required(),
  skewY: Joi.number().required(),
  points: Joi.array().ordered(repinPoint, repinPoint, repinPoint, repinPoint),
  coordinateSpace: Joi.string().valid('pixels', 'percent').default('pixels'),
  imageWidth: Joi.number().positive(),
  imageHeight: Joi.number().positive(),
  originalBbox: Joi.array().ordered(Joi.number(), Joi.number(), Joi.number(), Joi.number()).allow(null),
  originalImageWidth: Joi.number().positive().allow(null),
  originalImageHeight: Joi.number().positive().allow(null),
  editableLayerUrl: Joi.string().allow(null, ''),
  repinBackgroundUrl: Joi.string().allow(null, ''),
  repinBackgroundDisplayUrl: Joi.string().allow(null, ''),
  eraserHistory: Joi.array().items(eraserHistoryEntry).default([]),
  eraserRedoStack: Joi.array().items(eraserHistoryEntry).default([]),
  editableLayerPath: Joi.string().allow(null, ''),
  repinBackgroundPath: Joi.string().allow(null, ''),
  feedbackOption: Joi.string()
    .valid('edge_alignment', 'perspective_depth', 'lighting_shadow', 'material_reflections', 'seamless_blending')
    .allow(null),
  feedbackOptions: Joi.array().items(Joi.string().valid('edge_alignment', 'perspective_depth', 'lighting_shadow', 'material_reflections', 'seamless_blending')).default([]),
  sourceBaseMode: Joi.string().valid('original', 'version').default('version'),
  sourceVersionComponent: Joi.string().valid('ceiling', 'lci', 'door', 'cop').allow(null, ''),
});

const previewVersion = Joi.object().keys({
  version: Joi.number().integer().min(1).max(5).required(),
  url: Joi.string().required(),
  createdAt: Joi.alternatives().try(Joi.string(), Joi.date()).allow(null),
  sourceVersion: Joi.number().integer().min(1).max(5).allow(null),
  transform: repinTransform.allow(null),
  feedbackOption: Joi.string()
    .valid('edge_alignment', 'perspective_depth', 'lighting_shadow', 'material_reflections', 'seamless_blending')
    .allow(null),
  feedbackOptions: Joi.array().items(Joi.string().valid('edge_alignment', 'perspective_depth', 'lighting_shadow', 'material_reflections', 'seamless_blending')).default([]),
  sourceBaseMode: Joi.string().valid('original', 'version').default('version'),
  sourceVersionComponent: Joi.string().valid('ceiling', 'lci', 'door', 'cop').allow(null, ''),
});

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
      selectedComponentAssets: Joi.object().pattern(Joi.string(), Joi.string().allow(null, '')),
      componentPins: Joi.array().items(
        Joi.object().keys({
          componentKey: Joi.string().required(),
          x: Joi.number().required(),
          y: Joi.number().required(),
          aiPlaced: Joi.boolean(),
          bbox: Joi.array().items(Joi.number()).length(4),
          imageWidth: Joi.number().positive(),
          imageHeight: Joi.number().positive(),
          editableLayerUrl: Joi.string().allow(null, ''),
          repinBackgroundUrl: Joi.string().allow(null, ''),
          repinBackgroundDisplayUrl: Joi.string().allow(null, ''),
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
      previewVersions: Joi.array().items(previewVersion),
      repinPass: Joi.number().integer().min(0).max(5),
      repinTransforms: Joi.object().pattern(Joi.string().valid('ceiling', 'lci', 'door', 'cop'), repinTransform),
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
