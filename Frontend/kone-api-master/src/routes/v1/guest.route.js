const express = require('express');
const multer = require('multer');
const guestController = require('../../controllers/guest.controller');

const router = express.Router();
const upload = multer({ dest: 'tmp_uploads/' });

router.post('/session', guestController.createSession);
router.post('/upload', upload.single('image'), guestController.uploadImage);
router.post('/precheck', guestController.precheck);
router.post('/components', guestController.runComponents);
router.get('/status', guestController.status);
router.post('/video', guestController.generateVideo);
router.post('/finalize', guestController.finalize);
router.get('/download', guestController.download);

module.exports = router;
