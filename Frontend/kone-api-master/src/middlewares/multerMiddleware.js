// const multer = require('multer');

// const storage = multer.memoryStorage();

// const allowedMimeTypes = ['image/jpeg', 'image/jpg', 'image/png'];

// const fileFilter = (req, file, cb) => {
//   // Validate MIME type
//   if (!allowedMimeTypes.includes(file.mimetype)) {
//     return cb(new Error('Only JPG, JPEG, and PNG image files are allowed.'), false);
//   }

//   cb(null, true);
// };

// const upload = multer({
//   storage,

//   limits: {
//     fileSize: 5 * 1024 * 1024, // 5MB
//   },

//   fileFilter,
// });

// module.exports = upload;
const multer = require('multer');
const fs = require('fs');
const path = require('path');

const uploadDir = path.join(__dirname, '..', '..', 'uploads');

const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    fs.mkdirSync(uploadDir, { recursive: true });
    cb(null, uploadDir);
  },
  filename: (req, file, cb) => {
    cb(null, `${Date.now()}-${file.originalname}`);
  },
});

const allowedMimeTypes = ['image/jpeg', 'image/jpg', 'image/png'];

const fileFilter = (req, file, cb) => {
  if (!allowedMimeTypes.includes(file.mimetype)) {
    return cb(new Error('Only JPG, JPEG, and PNG files allowed'), false);
  }
  cb(null, true);
};

const upload = multer({
  storage,
  limits: {
    fileSize: 5 * 1024 * 1024, // 5MB
  },
  fileFilter,
});

module.exports = upload;
