const mongoose = require('mongoose');
const { toJSON } = require('./plugins');

const brochureContentSchema = mongoose.Schema(
  {
    offeringOverview: { type: String, default: '' },
    competitorComparison: { type: String, default: '' },
    uniqueSellingPoints: { type: String, default: '' },
    customerBenefits: { type: String, default: '' },
    additionalNotes: { type: String, default: '' },
  },
  { _id: false }
);

const brochureSchema = mongoose.Schema(
  {
    offeringId: {
      type: mongoose.SchemaTypes.ObjectId,
      ref: 'Offering',
      required: true,
    },
    projectId: {
      type: mongoose.SchemaTypes.ObjectId,
      ref: 'Project',
      required: true,
    },
    content: {
      type: brochureContentSchema,
      default: () => ({}),
    },
    tenderPdfUrl: {
      type: String,
      default: null,
    },
    sectionsComplete: {
      type: Number,
      default: 0,
    },
  },
  {
    timestamps: true,
  }
);

brochureSchema.plugin(toJSON);

const Brochure = mongoose.model('Brochure', brochureSchema);

module.exports = Brochure;
