const express = require('express');
const auth = require('../../middlewares/auth');
const validate = require('../../middlewares/validate');
const offeringValidation = require('../../validations/offering.validation');
const brochureValidation = require('../../validations/brochure.validation');
const { offeringController, brochureController } = require('../../controllers');

const router = express.Router();

router.route('/:offeringId').patch(auth(), validate(offeringValidation.updateOffering), offeringController.updateOffering);

router.post('/:offeringId/ai-placement', auth(), validate(offeringValidation.offeringId), offeringController.runAIPlacement);
router.post('/:offeringId/render', auth(), validate(offeringValidation.offeringId), offeringController.triggerRender);
router.post('/:offeringId/complete', auth(), validate(offeringValidation.offeringId), offeringController.completeOffering);

router
  .route('/:offeringId/brochure')
  .get(auth(), validate(brochureValidation.brochureParams), brochureController.getBrochure)
  .post(auth(), validate(brochureValidation.createBrochure), brochureController.createBrochure)
  .patch(auth(), validate(brochureValidation.updateBrochure), brochureController.updateBrochure);

module.exports = router;
