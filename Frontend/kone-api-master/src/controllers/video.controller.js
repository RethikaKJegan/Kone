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
const axios = require('axios');
const { execFile } = require('child_process');
const { promisify } = require('util');
const Offering = require('../models/offering.model');
const Project = require('../models/project.model');
const { projectService } = require('../services');

const fsPromises = fs.promises;
const execFileAsync = promisify(execFile);
const LOGIC_URL = process.env.LOGIC_URL || 'http://localhost:8001';

// in-memory guest store
const guestJobs = new Map();
const componentRuns = new Map();

const getUploadInputPath = (imageId) => path.join(__dirname, '..', '..', 'uploads', imageId, 'input.jpg');
const getOutputDir = (imageId) => path.join(__dirname, '..', '..', 'output', imageId);
const getLogicStorageDir = (userId, imageId) => path.join(__dirname, '..', '..', 'storage', 'auth', String(userId), imageId);

const localOutputPathFromUrl = (url) => {
  if (!url || typeof url !== 'string') return null;
  const [pathname] = url.split('?');
  if (!pathname.startsWith('/output/')) return null;
  const outputRoot = path.resolve(__dirname, '..', '..', 'output');
  const localPath = path.resolve(outputRoot, pathname.replace('/output/', ''));
  return localPath.startsWith(outputRoot) ? localPath : null;
};

const fileExists = async (filePath) => {
  try {
    await fsPromises.access(filePath);
    return true;
  } catch {
    return false;
  }
};

const readJsonIfExists = async (filePath) => {
  if (!(await fileExists(filePath))) return {};
  try {
    return JSON.parse(await fsPromises.readFile(filePath, 'utf-8'));
  } catch {
    return {};
  }
};

const componentPinsFromPlacement = async (storageDir) => {
  const placements = await readJsonIfExists(path.join(storageDir, 'pipeline', 'component_placements.json'));
  if (!Array.isArray(placements)) return [];
  const detections = await readJsonIfExists(path.join(storageDir, 'pipeline', 'elevator_detections.json'));
  const width = Number(detections.metadata?.image_width) || 0;
  const height = Number(detections.metadata?.image_height) || 0;
  if (!width || !height) return [];

  const supported = new Set(['lci', 'cop', 'door', 'ceiling']);
  return placements
    .map((placement) => {
      const componentKey = String(placement.id || '').toLowerCase();
      if (!supported.has(componentKey)) return null;
      const bbox = placement.final_insertion_bbox || placement.final_component_placement?.bbox || placement.inpaint_bbox;
      if (!Array.isArray(bbox) || bbox.length !== 4) return null;
      const [x1, y1, x2, y2] = bbox.map(Number);
      if (![x1, y1, x2, y2].every(Number.isFinite)) return null;
      return {
        componentKey,
        x: Math.round(((x1 + x2) / 2 / width) * 100),
        y: Math.round(((y1 + y2) / 2 / height) * 100),
        aiPlaced: true,
      };
    })
    .filter(Boolean);
};

const runLogicComponents = async ({
  imageId,
  userId,
  inputPath,
  components,
  componentAssets,
  environments,
  previewRequestKey,
}) => {
  const storageDir = getLogicStorageDir(userId, imageId);
  const uploadsDir = path.join(storageDir, 'uploads');
  const previewDir = path.join(storageDir, 'preview');
  const pipelineDir = path.join(storageDir, 'pipeline');
  const outputDir = getOutputDir(imageId);

  await Promise.all(
    [uploadsDir, previewDir, pipelineDir, outputDir].map((dir) => fsPromises.mkdir(dir, { recursive: true }))
  );
  await fsPromises.rm(pipelineDir, { recursive: true, force: true });
  await fsPromises.rm(previewDir, { recursive: true, force: true });
  await Promise.all([pipelineDir, previewDir].map((dir) => fsPromises.mkdir(dir, { recursive: true })));
  await fsPromises.copyFile(inputPath, path.join(uploadsDir, 'input.jpg'));

  const { data } = await axios.post(
    `${LOGIC_URL}/run-components`,
    {
      session_id: `auth_${userId}`,
      project_id: imageId,
      project_name: imageId,
      storage_dir: storageDir,
      selected_components: components,
      component_assets: componentAssets,
      environments,
      preview_request_key: previewRequestKey,
    },
    { timeout: 0 }
  );

  if (!data?.ok) {
    throw new Error(data?.error || 'Logic component placement failed');
  }

  await fsPromises.copyFile(path.join(previewDir, 'final_output.png'), path.join(outputDir, 'final_output.png'));
  const pins = await componentPinsFromPlacement(storageDir);
  return {
    storageDir,
    previewUrl: `/output/${imageId}/final_output.png`,
    pins,
  };
};

const getOwnedOffering = async (offeringId, userId) => {
  if (!offeringId) return null;
  const offering = await Offering.findById(offeringId);
  if (!offering) return null;
  const project = await Project.findById(offering.projectId);
  if (!project || project.userId.toString() !== userId) return null;
  return offering;
};

const runUploadPrecheck = async (req, res) => {
  try {
    const { imageId } = req.body;
    const inputPath = getUploadInputPath(imageId);
    if (!(await fileExists(inputPath))) {
      return res.status(404).json({
        ok: false,
        next_action: 'reupload',
        reason: 'Uploaded image was not found. Please upload the image again.',
      });
    }

    const storageDir = getLogicStorageDir(req.user.id, imageId);
    const uploadsDir = path.join(storageDir, 'uploads');
    await fsPromises.mkdir(uploadsDir, { recursive: true });
    await fsPromises.copyFile(inputPath, path.join(uploadsDir, 'input.jpg'));

    const { data } = await axios.post(
      `${LOGIC_URL}/precheck`,
      {
        session_id: `auth_${req.user.id}`,
        project_id: imageId,
        project_name: imageId,
        storage_dir: storageDir,
      },
      { timeout: 20000 }
    );

    return res.status(200).json(data);
  } catch (error) {
    return res.status(500).json({
      ok: false,
      next_action: 'reupload',
      reason: error.message || 'Image validation failed. Please try again.',
    });
  }
};

const startComponentRun = ({ offeringId, imageId, userId, inputPath, components, componentAssets, environments, previewRequestKey }) => {
  const runKey = `${offeringId}:${previewRequestKey || 'default'}`;
  if (componentRuns.has(runKey)) return;

  const run = (async () => {
    try {
      const placement = await runLogicComponents({
        imageId,
        userId,
        inputPath,
        components,
        componentAssets,
        environments,
        previewRequestKey,
      });
      const previewUrl = `${placement.previewUrl}?v=${Date.now()}`;
      await Offering.findByIdAndUpdate(offeringId, {
        componentPins: placement.pins,
        outputImageUrl: previewUrl,
        outputImagePath: placement.previewUrl,
        previewImagePath: placement.previewUrl,
        outputVideoUrl: null,
        outputVideoPath: null,
        downloadUrl: null,
        pipelineStatus: 'preview_ready',
        savedStep: 3,
        status: 'active',
        lastError: null,
        previewRequestKey,
      });
    } catch (error) {
      await Offering.findByIdAndUpdate(offeringId, {
        componentPins: [],
        outputImageUrl: null,
        outputImagePath: null,
        outputVideoUrl: null,
        outputVideoPath: null,
        downloadUrl: null,
        pipelineStatus: 'failed',
        lastError: error.message,
        previewRequestKey,
      });
    } finally {
      componentRuns.delete(runKey);
    }
  })();

  componentRuns.set(runKey, run);
};

const getOrRecoverJob = async (imageId, userId) => {
  const existing = guestJobs.get(imageId);
  if (existing) return existing;

  const inputPath = getUploadInputPath(imageId);
  if (!(await fileExists(inputPath))) return null;

  const recovered = {
    inputPath,
    userId,
    environment: null,
    components: null,
  };
  guestJobs.set(imageId, recovered);
  return recovered;
};

const normalizeVideoOptions = (videoOptions = {}) => {
  const motion = videoOptions.motion || videoOptions.motionStyle;
  if (motion === 'door-functionality') {
    return {
      engine: videoOptions.engine,
      mode: 'door_functionality',
      duration_seconds: videoOptions.duration_seconds || 8,
      speed: videoOptions.speed,
      quality: videoOptions.quality,
    };
  }
  return {
    engine: videoOptions.engine,
    motion,
    speed: videoOptions.speed,
    quality: videoOptions.quality,
  };
};

const generateFallbackVideo = async (inputImagePath, outputVideoPath) => {
  await execFileAsync('ffmpeg', [
    '-y',
    '-loop',
    '1',
    '-i',
    inputImagePath,
    '-t',
    '4',
    '-vf',
    'scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p',
    '-r',
    '30',
    '-c:v',
    'libx264',
    '-movflags',
    '+faststart',
    outputVideoPath,
  ]);
};

const generateLogicVideo = async ({ imageId, userId, inputPath, outputDir, videoOptions }) => {
  const storageDir = getLogicStorageDir(userId, imageId);
  const uploadsDir = path.join(storageDir, 'uploads');
  const previewDir = path.join(storageDir, 'preview');
  const pipelineDir = path.join(storageDir, 'pipeline');
  const videoDir = path.join(storageDir, 'video');

  await Promise.all(
    [uploadsDir, previewDir, pipelineDir, videoDir].map((dir) => fsPromises.mkdir(dir, { recursive: true }))
  );
  await fsPromises.copyFile(inputPath, path.join(uploadsDir, 'input.jpg'));
  await fsPromises.copyFile(inputPath, path.join(previewDir, 'final_output.png'));

  const { data } = await axios.post(
    `${LOGIC_URL}/generate-video`,
    {
      session_id: `auth_${userId}`,
      project_id: imageId,
      project_name: imageId,
      storage_dir: storageDir,
      video_options: normalizeVideoOptions(videoOptions),
    },
    { timeout: 0 }
  );

  if (!data?.ok) {
    throw new Error(data?.error || 'Logic video generation failed');
  }

  await fsPromises.copyFile(path.join(previewDir, 'final_output.png'), path.join(outputDir, 'final_output.png'));
  await fsPromises.copyFile(path.join(videoDir, 'elevator_animation.mp4'), path.join(outputDir, 'elevator_animation.mp4'));
  const metadataPath = path.join(videoDir, 'elevator_animation.json');
  if (await fileExists(metadataPath)) {
    await fsPromises.copyFile(metadataPath, path.join(outputDir, 'elevator_animation.json'));
  }
};

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

    const job = await getOrRecoverJob(imageId, req.user.id);

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
    const {
      imageId,
      offeringId,
      components,
      environments = [],
      component_assets: componentAssets = {},
      preview_request_key: previewRequestKey = null,
    } = req.body;

    const job = await getOrRecoverJob(imageId, req.user.id);

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

    const offering = await getOwnedOffering(offeringId, req.user.id);
    if (!offering) {
      return res.status(404).json({
        success: false,
        message: 'Invalid offeringId',
      });
    }

    const effectiveEnvironments = environments.length ? environments : job.environment ? [job.environment] : [];

    if (
      offering.previewRequestKey === previewRequestKey &&
      offering.pipelineStatus === 'preview_ready' &&
      offering.outputImageUrl
    ) {
      return res.status(200).json({
        success: true,
        status: 'preview_ready',
        selectedComponents: components,
        preview_url: offering.outputImageUrl,
        component_pins: offering.componentPins,
        preview_request_key: previewRequestKey,
      });
    }

    job.components = components;
    guestJobs.set(imageId, job);

    await Offering.findByIdAndUpdate(offeringId, {
      environments: effectiveEnvironments,
      selectedComponents: components,
      componentPins: [],
      activeAnnotationFilters: components,
      outputImageUrl: null,
      outputImagePath: null,
      outputVideoUrl: null,
      outputVideoPath: null,
      downloadUrl: null,
      pipelineStatus: 'processing',
      lastError: null,
      savedStep: 3,
      status: 'active',
      previewRequestKey,
    });
    await projectService.refreshProjectStatus(offering.projectId);

    startComponentRun({
      offeringId,
      imageId,
      userId: req.user.id,
      inputPath: job.inputPath,
      components,
      componentAssets,
      environments: effectiveEnvironments,
      previewRequestKey,
    });

    return res.status(200).json({
      success: true,
      status: 'processing',
      selectedComponents: components,
      preview_request_key: previewRequestKey,
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

    const { sourceImageUrl, videoOptions = {} } = req.body;
    let job = await getOrRecoverJob(imageId, req.user.id);
    const outputDir = getOutputDir(imageId);

    if (!job) {
      const sourceImagePath = localOutputPathFromUrl(sourceImageUrl);
      const fallbackInputPath = sourceImagePath && (await fileExists(sourceImagePath))
        ? sourceImagePath
        : path.join(outputDir, 'final_output.png');
      if (await fileExists(fallbackInputPath)) {
        job = {
          inputPath: fallbackInputPath,
          userId: req.user.id,
          environment: null,
          components: null,
        };
      } else {
        return res.status(404).json({
          success: false,
          message: 'Uploaded image is no longer available. Please re-upload the image and try again.',
        });
      }
    }
    if (job.userId !== req.user.id) {
      return res.status(403).json({
        success: false,
        message: 'Forbidden',
      });
    }

    await fsPromises.mkdir(outputDir, { recursive: true });

    const requestedSourcePath = localOutputPathFromUrl(sourceImageUrl);
    const inputPath = requestedSourcePath && (await fileExists(requestedSourcePath))
      ? requestedSourcePath
      : job.inputPath;

    const originalOutputPath = path.join(outputDir, '01_original.jpg');
    const finalOutputPath = path.join(outputDir, 'final_output.png');
    if (path.resolve(inputPath) !== path.resolve(originalOutputPath)) {
      await fsPromises.copyFile(inputPath, originalOutputPath);
    }
    if (path.resolve(inputPath) !== path.resolve(finalOutputPath)) {
      await fsPromises.copyFile(inputPath, finalOutputPath);
    }

    try {
      await generateLogicVideo({
        imageId,
        userId: req.user.id,
        inputPath: finalOutputPath,
        outputDir,
        videoOptions,
      });
    } catch (logicError) {
      if (
        videoOptions.engine === 'wan2.2'
        || videoOptions.motion === 'door-functionality'
        || videoOptions.mode === 'door_functionality'
      ) {
        throw logicError;
      }
      await generateFallbackVideo(finalOutputPath, path.join(outputDir, 'elevator_animation.mp4'));
    }

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
  runUploadPrecheck,
  selectEnvironment,
  selectComponents,
  generateVideo,
};
