const mongoose = require('mongoose');
const { toJSON, paginate } = require('./plugins');

const componentPinSchema = mongoose.Schema(
  {
    componentKey: { type: String, required: true },
    x: { type: Number, required: true },
    y: { type: Number, required: true },
    aiPlaced: { type: Boolean, default: false },
  },
  { _id: false }
);

const previewVersionSchema = mongoose.Schema(
  {
    version: { type: Number, required: true },
    url: { type: String, required: true },
    createdAt: { type: Date, default: Date.now },
    sourceVersion: { type: Number, default: null },
    transform: { type: mongoose.Schema.Types.Mixed, default: null },
    feedbackOption: { type: String, default: null },
  },
  { _id: false }
);

const offeringSchema = mongoose.Schema(
  {
    projectId: {
      type: mongoose.SchemaTypes.ObjectId,
      ref: 'Project',
      required: true,
    },
    name: {
      type: String,
      required: true,
      trim: true,
      default: 'New Visualization',
    },
    status: {
      type: String,
      enum: ['draft', 'active', 'complete'],
      default: 'draft',
    },
    savedStep: {
      type: Number,
      min: 1,
      max: 6,
      default: 1,
    },
    uploadedFileName: {
      type: String,
      default: null,
    },
    uploadedFileType: {
      type: String,
      enum: ['image', 'video', null],
      default: null,
    },
    imageId: {
      type: String,
      default: null,
    },
    inputImagePath: {
      type: String,
      default: null,
    },
    previewImagePath: {
      type: String,
      default: null,
    },
    outputImagePath: {
      type: String,
      default: null,
    },
    outputVideoPath: {
      type: String,
      default: null,
    },
    downloadZipPath: {
      type: String,
      default: null,
    },
    environments: {
      type: [String],
      default: [],
    },
    selectedComponents: {
      type: [String],
      default: [],
    },
    componentPins: {
      type: [componentPinSchema],
      default: [],
    },
    annotationsEnabled: {
      type: Boolean,
      default: true,
    },
    activeAnnotationFilters: {
      type: [String],
      default: [],
    },
    videoMotionStyle: {
      type: String,
      enum: ['zoom-in', 'pan-lr', 'pan-rl', 'door-functionality'],
      default: 'zoom-in',
    },
    videoSpeed: {
      type: Number,
      enum: [0.5, 1, 1.5],
      default: 1,
    },
    videoQuality: {
      type: String,
      default: '1080p',
    },
    pipelineStatus: {
      type: String,
      enum: ['idle', 'uploaded', 'processing', 'preview_ready', 'video_ready', 'ready_for_download', 'failed'],
      default: 'idle',
    },
    previewRequestKey: {
      type: String,
      default: null,
    },
    previewVersions: {
      type: [previewVersionSchema],
      default: [],
    },
    repinPass: {
      type: Number,
      default: 0,
    },
    outputImageUrl: {
      type: String,
      default: null,
    },
    outputVideoUrl: {
      type: String,
      default: null,
    },
    downloadUrl: {
      type: String,
      default: null,
    },
    lastError: {
      type: String,
      default: null,
    },
  },
  {
    timestamps: true,
  }
);

offeringSchema.plugin(toJSON);
offeringSchema.plugin(paginate);

const Offering = mongoose.model('Offering', offeringSchema);

module.exports = Offering;
