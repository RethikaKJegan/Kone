const Joi = require('joi');

const componentKeys = ['ceiling', 'kds', 'kds_2', 'kds_3', 'dcs1020', 'dcs1020_2', 'dcs1020_3', 'lci', 'door', 'cop'];
const semanticComponentKeys = ['ceiling', 'kds', 'dcs1020', 'lci', 'door', 'cop'];
const kdsInstanceKeys = ['kds', 'kds_2', 'kds_3'];
const dcsInstanceKeys = ['dcs1020', 'dcs1020_2', 'dcs1020_3'];
const equipmentInstanceKeys = [...kdsInstanceKeys, ...dcsInstanceKeys];

const componentTypeForInstanceId = (id) => {
  if (kdsInstanceKeys.includes(id)) return 'kds';
  if (dcsInstanceKeys.includes(id)) return 'dcs1020';
  return null;
};

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
  componentId: Joi.string().allow(null, ''),
  componentKey: Joi.string().valid(...componentKeys).required(),
  componentType: Joi.string().valid(...semanticComponentKeys).required(),
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
  sourceVersionComponent: Joi.string().valid(...componentKeys).allow(null, ''),
  sourceVersionComponentId: Joi.string().allow(null, ''),
  parentVersionId: Joi.number().integer().min(1).max(5).allow(null),
  parentFinalImagePath: Joi.string().allow(null, ''),
  activeComponentId: Joi.string().allow(null, ''),
  activeComponentType: Joi.string().valid(...semanticComponentKeys).allow(null, ''),
  currentComponentMaskOrCrop: Joi.array().ordered(Joi.number(), Joi.number(), Joi.number(), Joi.number()).allow(null),
  magicEraserApplied: Joi.boolean().default(false),
});

const componentInstance = Joi.object().keys({
  id: Joi.string().valid(...equipmentInstanceKeys).required(),
  componentType: Joi.string().valid('kds', 'dcs1020').required(),
  variantId: Joi.string().required(),
  assetUrl: Joi.string().required(),
}).custom((value, helpers) => {
  if (componentTypeForInstanceId(value.id) !== value.componentType) return helpers.error('any.invalid');
  return value;
});

const componentInstances = Joi.array().items(componentInstance).custom((value, helpers) => {
  const kdsItems = value.filter((item) => item.componentType === 'kds');
  const dcsItems = value.filter((item) => item.componentType === 'dcs1020');
  const hasDuplicateVariant = (items) => new Set(items.map((item) => item.variantId)).size !== items.length;
  if (kdsItems.length > 3 || dcsItems.length > 3 || kdsItems.length + dcsItems.length > 4) return helpers.error('array.max');
  if (hasDuplicateVariant(kdsItems) || hasDuplicateVariant(dcsItems)) return helpers.error('array.unique');
  return value;
});

const selectComponents = {
  body: Joi.object().keys({
    imageId: Joi.string().required(),
    offeringId: Joi.string().required(),
    components: Joi.array().items(Joi.string().valid(...componentKeys)).min(1).required(),
    environments: Joi.array().items(Joi.string().valid('car', 'lobby')).default([]),
    component_assets: Joi.object().pattern(Joi.string(), Joi.string()).default({}),
    component_instances: componentInstances.default([]),
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
    components: Joi.array().items(Joi.string().valid(...componentKeys)).default([]),
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
