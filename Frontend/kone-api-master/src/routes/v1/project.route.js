const express = require('express');
const auth = require('../../middlewares/auth');
const validate = require('../../middlewares/validate');
const projectValidation = require('../../validations/project.validation');
const { projectController, offeringController } = require('../../controllers');

const router = express.Router();

router
  .route('/')
  .get(auth(), projectController.getProjects)
  .post(auth(), validate(projectValidation.createProject), projectController.createProject);

router.route('/:projectId').delete(auth(), validate(projectValidation.projectId), projectController.deleteProject);

router
  .route('/:projectId/offerings')
  .get(auth(), validate(projectValidation.projectId), offeringController.getOfferings)
  .post(auth(), validate(projectValidation.projectId), offeringController.createOffering);

module.exports = router;
