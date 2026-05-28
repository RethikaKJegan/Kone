// // const { v4: uuidv4 } = require('uuid');

// // const generateDummyVideo = require('../utils/dummyGenerator');

// // // STEP 1
// // const uploadImage = async (req, res) => {
// //   if (!req.file) {
// //     return res.status(400).json({
// //       success: false,
// //       message: 'Image required',
// //     });
// //   }

// //   const imageId = uuidv4();

// //   return res.status(200).json({
// //     success: true,
// //     message: 'Image uploaded',
// //     imageId,
// //   });
// // };

// // // STEP 2
// // const selectEnvironment = async (req, res) => {
// //   const { environment } = req.body;

// //   return res.status(200).json({
// //     success: true,
// //     selectedEnvironment: environment,
// //   });
// // };

// // // STEP 3
// // const selectComponents = async (req, res) => {
// //   const { components } = req.body;

// //   return res.status(200).json({
// //     success: true,
// //     selectedComponents: components,
// //   });
// // };

// // // STEP 4
// // const generateVideo = async (req, res) => {
// //   const video = await generateDummyVideo();

// //   return res.status(200).json({
// //     success: true,
// //     message: 'Video generated successfully',
// //     data: {
// //       videoUrl: video.videoUrl,
// //     },
// //   });
// // };

// // module.exports = {
// //   uploadImage,
// //   selectEnvironment,
// //   selectComponents,
// //   generateVideo,
// // };

// const { v4: uuidv4 } = require('uuid');

// const fs = require('fs-extra');
// const path = require('path');
// const sharp = require('sharp');

// const generateDummyVideo = require('../utils/dummyGenerator');

// // temporary guest storage
// const guestJobs = new Map();

// // STEP 1
// const uploadImage = async (req, res) => {
//   try {
//     if (!req.file) {
//       return res.status(400).json({
//         success: false,
//         message: 'Image required',
//       });
//     }

//     const imageId = uuidv4();

//     // store temporary guest data
//     guestJobs.set(imageId, {
//       imagePath: req.file.path,
//       environment: null,
//       components: null,
//     });

//     return res.status(200).json({
//       success: true,
//       message: 'Image uploaded',
//       imageId,
//     });
//   } catch (error) {
//     return res.status(500).json({
//       success: false,
//       message: error.message,
//     });
//   }
// };

// // STEP 2
// const selectEnvironment = async (req, res) => {
//   try {
//     const { imageId, environment } = req.body;

//     const job = guestJobs.get(imageId);

//     if (!job) {
//       return res.status(404).json({
//         success: false,
//         message: 'Invalid imageId',
//       });
//     }

//     job.environment = environment;

//     guestJobs.set(imageId, job);

//     return res.status(200).json({
//       success: true,
//       selectedEnvironment: environment,
//     });
//   } catch (error) {
//     return res.status(500).json({
//       success: false,
//       message: error.message,
//     });
//   }
// };

// // STEP 3
// const selectComponents = async (req, res) => {
//   try {
//     const { imageId, components } = req.body;

//     const job = guestJobs.get(imageId);

//     if (!job) {
//       return res.status(404).json({
//         success: false,
//         message: 'Invalid imageId',
//       });
//     }

//     job.components = components;

//     guestJobs.set(imageId, job);

//     return res.status(200).json({
//       success: true,
//       selectedComponents: components,
//     });
//   } catch (error) {
//     return res.status(500).json({
//       success: false,
//       message: error.message,
//     });
//   }
// };

// // STEP 4
// const generateVideo = async (req, res) => {
//   try {
//     const { imageId } = req.body;

//     const job = guestJobs.get(imageId);

//     if (!job) {
//       return res.status(404).json({
//         success: false,
//         message: 'Invalid imageId',
//       });
//     }

//     // create folder
//     const jobDir = path.join(__dirname, '..', '..', 'jobs', imageId);

//     await fs.ensureDir(jobDir);

//     const inputPath = path.join(jobDir, 'input.jpg');
//     const outputPath = path.join(jobDir, 'output.jpg');
//     const videoPath = path.join(jobDir, 'output.mp4');

//     // save uploaded image
//     await fs.copy(job.imagePath, inputPath);

//     // generate dummy output image
//     await sharp(inputPath)
//       .resize(900)
//       .grayscale()
//       .toFile(outputPath);

//     // generate dummy video
//     const video = await generateDummyVideo();

//     await fs.writeFile(
//       videoPath,
//       video.videoBuffer || Buffer.from('FAKE_VIDEO_DATA')
//     );

//     // clear uploads folder
//     await fs.emptyDir(path.join(__dirname, '..', '..', 'uploads'));

//     // clear guest memory
//     guestJobs.delete(imageId);

//     return res.status(200).json({
//       success: true,
//       message: 'Video generated successfully',
//       data: {
//         imageId,
//         inputImage: inputPath,
//         outputImage: outputPath,
//         video: videoPath,
//       },
//     });
//   } catch (error) {
//     return res.status(500).json({
//       success: false,
//       message: error.message,
//     });
//   }
// };

// module.exports = {
//   uploadImage,
//   selectEnvironment,
//   selectComponents,
//   generateVideo,
// };
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const generateDummyVideo = require('../utils/dummyGenerator');

const fsPromises = fs.promises;

// in-memory guest store
const guestJobs = new Map();

/* STEP 1 - Upload Image */
const uploadImage = async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({
        success: false,
        message: 'Image required',
      });
    }

    const imageId = crypto.randomUUID();

    const userDir = path.join(__dirname, '..', '..', 'uploads', imageId);
    await fsPromises.mkdir(userDir, { recursive: true });

    const inputPath = path.join(userDir, 'input.jpg');

    // move uploaded file into user folder
    await fsPromises.rename(req.file.path, inputPath);

    guestJobs.set(imageId, {
      inputPath,
      userId: req.user.id,
      environment: null,
      components: null,
    });

    return res.status(200).json({
      success: true,
      message: 'Image uploaded',
      imageId,
    });
  } catch (error) {
    return res.status(500).json({
      success: false,
      message: error.message,
    });
  }
};

/* STEP 2 - Select Environment */
const selectEnvironment = async (req, res) => {
  try {
    const { imageId, environment } = req.body;

    const job = guestJobs.get(imageId);

    if (!job) {
      return res.status(404).json({
        success: false,
        message: 'Invalid imageId',
      });
    }
    if (job.userId !== req.user.id) {
      return res.status(403).json({
        success: false,
        message: 'Forbidden',
      });
    }

    job.environment = environment;
    guestJobs.set(imageId, job);

    return res.status(200).json({
      success: true,
      selectedEnvironment: environment,
    });
  } catch (error) {
    return res.status(500).json({
      success: false,
      message: error.message,
    });
  }
};

/* STEP 3 - Select Components */
const selectComponents = async (req, res) => {
  try {
    const { imageId, components } = req.body;

    const job = guestJobs.get(imageId);

    if (!job) {
      return res.status(404).json({
        success: false,
        message: 'Invalid imageId',
      });
    }
    if (job.userId !== req.user.id) {
      return res.status(403).json({
        success: false,
        message: 'Forbidden',
      });
    }

    job.components = components;
    guestJobs.set(imageId, job);

    return res.status(200).json({
      success: true,
      selectedComponents: components,
    });
  } catch (error) {
    return res.status(500).json({
      success: false,
      message: error.message,
    });
  }
};

/* STEP 4 - Generate Video */
const generateVideo = async (req, res) => {
  try {
    const { imageId } = req.body;

    const job = guestJobs.get(imageId);

    if (!job) {
      return res.status(404).json({
        success: false,
        message: 'Invalid imageId',
      });
    }
    if (job.userId !== req.user.id) {
      return res.status(403).json({
        success: false,
        message: 'Forbidden',
      });
    }

    const uploadsDir = path.join(__dirname, '..', '..', 'uploads', imageId);
    const outputDir = path.join(__dirname, '..', '..', 'output', imageId);

    await fsPromises.mkdir(outputDir, { recursive: true });

    const { inputPath } = job;

    // Save original image
    await fsPromises.copyFile(inputPath, path.join(outputDir, '01_original.jpg'));
    // Stub final output — copy of input until real pipeline runs
    await fsPromises.copyFile(inputPath, path.join(outputDir, 'final_output.png'));

    // Generate dummy video
    const video = await generateDummyVideo();
    await fsPromises.writeFile(path.join(outputDir, 'elevator_animation.mp4'), video.videoBuffer);

    // Write manifest
    await fsPromises.writeFile(
      path.join(outputDir, 'pipeline_manifest.json'),
      JSON.stringify(
        {
          imageId,
          generatedAt: new Date().toISOString(),
          environment: job.environment,
          components: job.components,
          files: ['01_original.jpg', 'final_output.png', 'elevator_animation.mp4'],
        },
        null,
        2
      )
    );

    // Clean up only the uploads folder for this imageId
    await fsPromises.rm(uploadsDir, { recursive: true, force: true });

    // Clear memory
    guestJobs.delete(imageId);

    return res.status(200).json({
      success: true,
      message: 'Video generated successfully',
      data: { imageId },
    });
  } catch (error) {
    return res.status(500).json({
      success: false,
      message: error.message,
    });
  }
};

module.exports = {
  uploadImage,
  selectEnvironment,
  selectComponents,
  generateVideo,
};
