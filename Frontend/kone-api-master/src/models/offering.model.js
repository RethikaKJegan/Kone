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
      enum: ['draft', 'complete'],
      default: 'draft',
    },
    imageId: {
      type: String,
      default: null,
    },
    uploadedFileUrl: {
      type: String,
      default: null,
    },
    uploadedFileName: {
      type: String,
      default: null,
    },
    uploadedFileType: {
      type: String,
      enum: ['image', 'video'],
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
      enum: ['zoom-in', 'pan-lr', 'pan-rl'],
      default: 'zoom-in',
    },
    videoSpeed: {
      type: Number,
      enum: [0.5, 1, 1.5],
      default: 1,
    },
    videoQuality: {
      type: String,
      enum: ['360p', '480p', '720p', '1080p'],
      default: '1080p',
    },
    renderComplete: {
      type: Boolean,
      default: false,
    },
    outputImageUrl: {
      type: String,
      default: null,
    },
    outputVideoUrl: {
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
