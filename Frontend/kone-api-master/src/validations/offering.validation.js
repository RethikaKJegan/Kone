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
const { objectId } = require('./custom.validation');

const repinPoint = Joi.object().keys({
  x: Joi.number().required(),
  y: Joi.number().required(),
});

const eraserHistoryEntry = Joi.object().keys({
  repinBackgroundUrl: Joi.string().allow(null, ''),
  repinBackgroundDisplayUrl: Joi.string().allow(null, ''),
});

const repinSharedBackgroundState = Joi.object().keys({
  repinBackgroundUrl: Joi.string().allow(null, ''),
  repinBackgroundDisplayUrl: Joi.string().allow(null, ''),
  eraserHistory: Joi.array().items(eraserHistoryEntry).default([]),
  eraserRedoStack: Joi.array().items(eraserHistoryEntry).default([]),
});

const repinSharedBackgrounds = Joi.object().pattern(
  Joi.string().valid('1', '2', '3', '4', '5'),
  repinSharedBackgroundState
);

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
  coordinateSpace: Joi.string().valid('pixels', 'percent').default('pixels'),
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
  feedbackOption: Joi.string()
    .valid('edge_alignment', 'perspective_depth', 'lighting_shadow', 'material_reflections', 'seamless_blending')
    .allow(null),
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

const previewVersion = Joi.object().keys({
  version: Joi.number().integer().min(1).max(5).required(),
  url: Joi.string().required(),
  createdAt: Joi.alternatives().try(Joi.string(), Joi.date()).allow(null),
  sourceVersion: Joi.number().integer().min(1).max(5).allow(null),
  transform: repinTransform.allow(null),
  transforms: Joi.array().items(repinTransform).default([]),
  feedbackOption: Joi.string()
    .valid('edge_alignment', 'perspective_depth', 'lighting_shadow', 'material_reflections', 'seamless_blending')
    .allow(null),
  feedbackOptions: Joi.array().items(Joi.string().valid('edge_alignment', 'perspective_depth', 'lighting_shadow', 'material_reflections', 'seamless_blending')).default([]),
  sourceBaseMode: Joi.string().valid('original', 'version').default('version'),
  sourceVersionComponent: Joi.string().valid(...componentKeys).allow(null, ''),
});

const offeringId = {
  params: Joi.object().keys({
    offeringId: Joi.string().custom(objectId).required(),
  }),
};

const componentInstance = Joi.object().keys({
  id: Joi.string()
    .valid(...equipmentInstanceKeys)
    .required(),
  componentType: Joi.string().valid('kds', 'dcs1020').required(),
  variantId: Joi.string().required(),
  assetUrl: Joi.string().required(),
}).custom((value, helpers) => {
  if (componentTypeForInstanceId(value.id) !== value.componentType) return helpers.error('any.invalid');
  return value;
});

const componentInstances = Joi.array()
  .items(componentInstance)
  .custom((value, helpers) => {
    const kdsItems = value.filter((item) => item.componentType === 'kds');
    const dcsItems = value.filter((item) => item.componentType === 'dcs1020');
    const hasDuplicateVariant = (items) => new Set(items.map((item) => item.variantId)).size !== items.length;
    if (kdsItems.length > 3 || dcsItems.length > 3 || kdsItems.length + dcsItems.length > 4) return helpers.error('array.max');
    if (hasDuplicateVariant(kdsItems) || hasDuplicateVariant(dcsItems)) return helpers.error('array.unique');
    return value;
  });

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
      selectedComponents: Joi.array().items(Joi.string().valid(...componentKeys)),
      selectedComponentAssets: Joi.object().pattern(Joi.string(), Joi.string().allow(null, '')),
      componentInstances,
      componentPins: Joi.array().items(
        Joi.object().keys({
          componentKey: Joi.string().valid(...componentKeys).required(),
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
      activeAnnotationFilters: Joi.array().items(Joi.string().valid(...componentKeys)),
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
      repinTransforms: Joi.object().pattern(Joi.string().valid(...componentKeys), repinTransform),
      repinSharedBackgrounds,
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
