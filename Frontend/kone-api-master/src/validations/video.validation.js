const Joi = require('joi');

const repinPoint = Joi.object().keys({
  x: Joi.number().required(),
  y: Joi.number().required(),
});

const eraserHistoryEntry = Joi.object().keys({
  repinBackgroundUrl: Joi.string().allow(null, ''),
  repinBackgroundDisplayUrl: Joi.string().allow(null, ''),
});

const imageIdBody = {
  body: Joi.object().keys({
    imageId: Joi.string().required(),
    offeringId: Joi.string(),
    sourceImageUrl: Joi.string(),
    videoOptions: Joi.object().unknown(true),
  }),
};

const cancelVideo = {
  body: Joi.object().keys({
    imageId: Joi.string().required(),
    offeringId: Joi.string(),
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
  componentKey: Joi.string().valid('ceiling', 'kds', 'dcs1020', 'lci', 'door', 'cop').required(),
  componentType: Joi.string().valid('ceiling', 'kds', 'dcs1020', 'lci', 'door', 'cop').required(),
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
  coordinateSpace: Joi.string().valid('pixels').default('pixels'),
  imageWidth: Joi.number().positive(),
  imageHeight: Joi.number().positive(),
  assetAspectRatio: Joi.number().positive().allow(null),
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
  feedbackOption: Joi.string().valid('edge_alignment', 'perspective_depth', 'lighting_shadow', 'material_reflections', 'seamless_blending').allow(null),
  feedbackOptions: Joi.array().items(Joi.string().valid('edge_alignment', 'perspective_depth', 'lighting_shadow', 'material_reflections', 'seamless_blending')).default([]),
  sourceBaseMode: Joi.string().valid('original', 'version').default('version'),
  sourceVersionComponent: Joi.string().valid('ceiling', 'kds', 'dcs1020', 'lci', 'door', 'cop').allow(null, ''),
  parentVersionId: Joi.number().integer().min(1).max(5).allow(null),
  parentFinalImagePath: Joi.string().allow(null, ''),
  activeComponentId: Joi.string().valid('ceiling', 'kds', 'dcs1020', 'lci', 'door', 'cop').allow(null, ''),
  activeComponentType: Joi.string().valid('ceiling', 'kds', 'dcs1020', 'lci', 'door', 'cop').allow(null, ''),
  currentComponentMaskOrCrop: Joi.array().ordered(Joi.number(), Joi.number(), Joi.number(), Joi.number()).allow(null),
  magicEraserApplied: Joi.boolean().default(false),
});

const selectComponents = {
  body: Joi.object().keys({
    imageId: Joi.string().required(),
    offeringId: Joi.string().required(),
    components: Joi.array().items(Joi.string().valid('ceiling', 'kds', 'dcs1020', 'lci', 'door', 'cop')).min(1).required(),
    environments: Joi.array().items(Joi.string().valid('car', 'lobby')).default([]),
    component_assets: Joi.object().pattern(Joi.string(), Joi.string()).default({}),
    preview_request_key: Joi.string().allow(null, ''),
  }),
};


const repinEraser = {
  body: Joi.object().keys({
    imageId: Joi.string().required(),
    offeringId: Joi.string().required(),
    sourceVersion: Joi.number().integer().min(1).max(5).required(),
    sourceBaseMode: Joi.string().valid('original', 'version').default('version'),
    maskDataUrl: Joi.string().required(),
    transform: repinTransform.required(),
  }),
};

const repinPreview = {
  body: Joi.object().keys({
    imageId: Joi.string().required(),
    offeringId: Joi.string().required(),
    components: Joi.array().items(Joi.string().valid('ceiling', 'kds', 'dcs1020', 'lci', 'door', 'cop')).default([]),
    environments: Joi.array().items(Joi.string().valid('car', 'lobby')).default([]),
    component_assets: Joi.object().pattern(Joi.string(), Joi.string()).default({}),
    preview_request_key: Joi.string().allow(null, ''),
    transform: repinTransform.required(),
    transforms: Joi.array().items(repinTransform).default([]),
  }),
};

module.exports = {
  imageIdBody,
  cancelVideo,
  selectEnvironment,
  selectComponents,
  repinPreview,
  repinEraser,
};
