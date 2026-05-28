const express = require('express');
const auth = require('../../middlewares/auth');
const upload = require('../../middlewares/multerMiddleware');
const { limiter } = require('../../middlewares/rateLimiter');
const validate = require('../../middlewares/validate');
const videoValidation = require('../../validations/video.validation');

const router = express.Router();

// router.post(
//   '/upload-image',

//   upload.single('image'),
//   (req, res) => {
//     res.status(200).json({
//       success: true,
//       message: 'Image uploaded successfully',
//       file: req.file.originalname,
//     });
//   }
// );

const { videoController } = require('../../controllers');

// STEP 1
router.post('/upload-image', auth(), limiter, upload.single('image'), videoController.uploadImage);

// STEP 2
router.post(
  '/select-environment',
  auth(),
  limiter,
  validate(videoValidation.selectEnvironment),
  videoController.selectEnvironment
);

// STEP 3
router.post(
  '/select-components',
  auth(),
  limiter,
  validate(videoValidation.selectComponents),
  videoController.selectComponents
);

// STEP 4
router.post('/generate', auth(), limiter, validate(videoValidation.imageIdBody), videoController.generateVideo);

module.exports = router;
