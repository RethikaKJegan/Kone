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
const { execFile, spawn } = require('child_process');
const { promisify } = require('util');
const Offering = require('../models/offering.model');
const Project = require('../models/project.model');
const { projectService } = require('../services');
const { uploadFileToAzure } = require('../services/azureBlob.service');
const User = require('../models/user.model');
const {
  uploadedImageBlobPath,
  selectedImageBlobPath,
  finalVideoBlobPath,
} = require('../utils/azureBlobPaths');


const fsPromises = fs.promises;
const uploadAzureCopy = (localFilePath, blobPath, contentType, onSuccess) => {
  uploadFileToAzure(localFilePath, blobPath, contentType)
    .then(async (result) => {
      if (!result.success) {
        console.warn('[Azure] Copy failed/skipped:', result);
        return;
      }

      console.log('[Azure] Copied:', result.blobPath);

      if (onSuccess) {
        await onSuccess(result);
      }
    })
    .catch((error) => {
      console.error('[Azure] Copy crashed:', error.message);
    });
};
const execFileAsync = promisify(execFile);
const LOGIC_URL = process.env.LOGIC_URL || 'http://localhost:8001';
const COMFY_ROOT = process.env.COMFY_ROOT || '/workspace/Kone/vdotest';
const COMFY_URL = process.env.COMFY_URL || 'http://127.0.0.1:8188';
const COMFY_RUNNER = process.env.COMFY_RUNNER || path.join(COMFY_ROOT, 'run_i2v_api.py');
const COMFY_START_SCRIPT = process.env.COMFY_START_SCRIPT || path.join(COMFY_ROOT, 'scripts', 'start_comfy_logged.sh');
const COMFY_PYTHON = process.env.COMFY_PYTHON || '/usr/bin/python3';
let comfyStartPromise = null;

// in-memory guest store
const guestJobs = new Map();
const componentRuns = new Map();
const repinRuns = new Map();

const getUploadInputPath = (imageId) => path.join(__dirname, '..', '..', 'uploads', imageId, 'input.jpg');
const getOutputDir = (imageId) => path.join(__dirname, '..', '..', 'output', imageId);
const getLogicStorageDir = (userId, imageId) => path.join(__dirname, '..', '..', 'storage', 'auth', String(userId), imageId);
const storageRoot = path.resolve(__dirname, '..', '..', 'storage');
const storagePublicUrl = (filePath) => {
  if (!filePath) return null;
  const resolved = path.resolve(filePath);
  if (!resolved.startsWith(storageRoot)) return null;
  return `/storage/${path.relative(storageRoot, resolved).split(path.sep).join('/')}`;
};
const localStoragePathFromUrl = (url) => {
  if (!url || typeof url !== 'string') return null;
  const [pathname] = url.split('?');
  if (!pathname.startsWith('/storage/')) return null;
  const resolved = path.resolve(storageRoot, pathname.replace('/storage/', ''));
  return resolved.startsWith(storageRoot) ? resolved : null;
};
const hasManualEraserBackground = (item = {}) => Array.isArray(item.eraserHistory) && item.eraserHistory.length > 1;
const isSameComponentReEdit = (item = {}) => item.sourceVersionComponent && item.componentKey && String(item.sourceVersionComponent).toLowerCase() === String(item.componentKey).toLowerCase();

const withLocalRepinFiles = (item = {}) => {
  const useRepinBackground = Boolean(item.repinBackgroundPath || item.repinBackgroundUrl) || hasManualEraserBackground(item) || isSameComponentReEdit(item);
  return {
    ...item,
    editableLayerPath: item.editableLayerPath || localStoragePathFromUrl(item.editableLayerUrl),
    repinBackgroundPath: useRepinBackground ? (item.repinBackgroundPath || localStoragePathFromUrl(item.repinBackgroundUrl)) : null,
  };
};

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

const fileSha256 = async (filePath) => new Promise((resolve, reject) => {
  const hash = crypto.createHash('sha256');
  const stream = fs.createReadStream(filePath);

  stream.on('error', reject);
  stream.on('data', (chunk) => hash.update(chunk));
  stream.on('end', () => resolve(hash.digest('hex')));
});

const readJsonIfExists = async (filePath) => {
  if (!(await fileExists(filePath))) return {};
  try {
    return JSON.parse(await fsPromises.readFile(filePath, 'utf-8'));
  } catch {
    return {};
  }
};

const createWebPreview = async (inputPath, outputPath, maxSide = 1400) => {
  try {
    await execFileAsync('python3', [
      '-c',
      'from PIL import Image; import sys; im=Image.open(sys.argv[1]).convert("RGB"); im.thumbnail((int(sys.argv[3]), int(sys.argv[3])), Image.Resampling.LANCZOS); im.save(sys.argv[2], "JPEG", quality=86, optimize=True)',
      inputPath,
      outputPath,
      String(maxSide),
    ], { timeout: 30000 });
    return await fileExists(outputPath);
  } catch {
    return false;
  }
};

const isValidVideoFile = async (filePath) => {
  if (!(await fileExists(filePath))) return false;
  try {
    const { stdout } = await execFileAsync(
      'ffprobe',
      [
        '-v',
        'error',
        '-show_entries',
        'format=duration',
        '-of',
        'default=noprint_wrappers=1:nokey=1',
        filePath,
      ],
      { timeout: 30000 }
    );
    return Number(stdout.trim()) > 0;
  } catch {
    return false;
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
        bbox: [x1, y1, x2, y2],
        imageWidth: width,
        imageHeight: height,
        editableLayerUrl: storagePublicUrl(placement.editable_layer_path),
        repinBackgroundUrl: storagePublicUrl(placement.repin_background_path),
        repinBackgroundDisplayUrl: storagePublicUrl(placement.repin_background_web_path || placement.repin_background_path),
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
  const webPreviewCreated = await createWebPreview(path.join(outputDir, 'final_output.png'), path.join(outputDir, 'final_output_web.jpg'));
  const pins = await componentPinsFromPlacement(storageDir);
  return {
    storageDir,
    previewUrl: webPreviewCreated ? `/output/${imageId}/final_output_web.jpg` : `/output/${imageId}/final_output.png`,
    fullPreviewUrl: `/output/${imageId}/final_output.png`,
    pins,
  };
};


const normalizePreviewVersions = (offering, fallbackUrl) => {
  const existing = Array.isArray(offering.previewVersions) ? offering.previewVersions : [];
  if (existing.length) return existing.map((version) => typeof version.toObject === 'function' ? version.toObject() : version);
  return fallbackUrl ? [{ version: 1, url: fallbackUrl, createdAt: new Date() }] : [];
};

const mergeComponentPins = (existingPins = [], updatedPins = []) => {
  const byKey = new Map();
  existingPins.forEach((pin) => {
    const plain = typeof pin.toObject === 'function' ? pin.toObject() : pin;
    if (plain?.componentKey) byKey.set(String(plain.componentKey).toLowerCase(), plain);
  });
  updatedPins.forEach((pin) => {
    if (pin?.componentKey) byKey.set(String(pin.componentKey).toLowerCase(), pin);
  });
  return Array.from(byKey.values());
};

const runLogicRepin = async ({ imageId, userId, transform, transforms = [], componentAssets, environments, previewRequestKey }) => {
  const logicTransform = withLocalRepinFiles(transform);
  const logicTransforms = transforms.map((item) => withLocalRepinFiles(item));
  const repinComponents = Array.from(new Set((logicTransforms.length ? logicTransforms : [logicTransform])
    .map((item) => item?.componentKey)
    .filter(Boolean)));
  const storageDir = getLogicStorageDir(userId, imageId);
  const uploadsDir = path.join(storageDir, 'uploads');
  const previewDir = path.join(storageDir, 'preview');
  const pipelineDir = path.join(storageDir, 'pipeline');
  const outputDir = getOutputDir(imageId);
  await Promise.all([uploadsDir, previewDir, pipelineDir, outputDir].map((dir) => fsPromises.mkdir(dir, { recursive: true })));

  const fallbackInput = getUploadInputPath(imageId);
  const sourcePath = logicTransform.sourceBaseMode === 'original'
    ? fallbackInput
    : (logicTransform.sourceVersion > 1
        ? path.join(outputDir, `final_output_v${logicTransform.sourceVersion}.png`)
        : path.join(outputDir, 'final_output.png'));
  const sourceImage = (await fileExists(sourcePath)) ? sourcePath : ((await fileExists(path.join(outputDir, 'final_output.png'))) ? path.join(outputDir, 'final_output.png') : fallbackInput);
  await fsPromises.copyFile(sourceImage, path.join(uploadsDir, `repin_source_v${logicTransform.sourceVersion}.png`));

  const { data } = await axios.post(
    `${LOGIC_URL}/repin-components`,
    {
      session_id: `auth_${userId}`,
      project_id: imageId,
      project_name: imageId,
      storage_dir: storageDir,
      selected_components: repinComponents.length ? repinComponents : [transform.componentKey],
      component_assets: componentAssets,
      environments,
      preview_request_key: previewRequestKey,
      transform: logicTransform,
      transforms: logicTransforms,
    },
    { timeout: 0 }
  );

  if (!data?.ok) throw new Error(data?.error || 'Logic repin placement failed');

  const versionFile = `final_output_v${logicTransform.targetVersion}.png`;
  const webVersionFile = `final_output_v${logicTransform.targetVersion}_web.jpg`;
  await fsPromises.copyFile(path.join(previewDir, versionFile), path.join(outputDir, versionFile));
  await fsPromises.copyFile(path.join(previewDir, 'final_output.png'), path.join(outputDir, 'final_output.png'));
  const webVersionCreated = await createWebPreview(path.join(outputDir, versionFile), path.join(outputDir, webVersionFile));
  const webCurrentCreated = await createWebPreview(path.join(outputDir, 'final_output.png'), path.join(outputDir, 'final_output_web.jpg'));
  const publicLogicUrl = (value) => {
    if (!value || typeof value !== 'string') return value;
    if (value.startsWith('/storage/') || value.startsWith('/output/') || value.startsWith('http://') || value.startsWith('https://')) return value;
    return storagePublicUrl(path.join(storageDir, value));
  };
  const logicPreviewVersion = Array.isArray(data.preview_versions)
    ? data.preview_versions.find((version) => Number(version.version) === Number(logicTransform.targetVersion))
    : null;
  const logicTransformResult = logicPreviewVersion?.transform
    ? {
        ...logicPreviewVersion.transform,
        editableLayerUrl: publicLogicUrl(logicPreviewVersion.transform.editableLayerUrl),
        repinBackgroundUrl: publicLogicUrl(logicPreviewVersion.transform.repinBackgroundUrl),
        repinBackgroundDisplayUrl: publicLogicUrl(logicPreviewVersion.transform.repinBackgroundDisplayUrl),
      }
    : null;

  return {
    storageDir,
    previewUrl: webVersionCreated ? `/output/${imageId}/${webVersionFile}` : `/output/${imageId}/${versionFile}`,
    currentPreviewUrl: webCurrentCreated ? `/output/${imageId}/final_output_web.jpg` : `/output/${imageId}/final_output.png`,
    fullPreviewUrl: `/output/${imageId}/${versionFile}`,
    transform: logicTransformResult,
    pins: await componentPinsFromPlacement(storageDir),
  };
};

const startRepinRun = ({ offeringId, imageId, userId, transform, transforms = [], componentAssets, environments, previewRequestKey }) => {
  const runKey = `${offeringId}:${previewRequestKey || `repin-v${transform.targetVersion}`}`;
  if (repinRuns.has(runKey)) return;

  const run = (async () => {
    try {
      const offering = await getOwnedOffering(offeringId, userId);
      if (!offering) throw new Error('Invalid offeringId');
      if (Number(transform.targetVersion) > 5) throw new Error('Version limit reached. Choose the best saved version to continue.');
      const placement = await runLogicRepin({ imageId, userId, transform, transforms, componentAssets, environments, previewRequestKey });
      const versionUrl = `${placement.previewUrl}?v=${Date.now()}`;
      const versions = normalizePreviewVersions(offering, offering.previewImagePath || offering.outputImagePath || offering.outputImageUrl);
      const nextVersion = {
        version: Number(transform.targetVersion),
        url: versionUrl,
        sourceVersion: Number(transform.sourceVersion),
        transform: placement.transform || transform,
        feedbackOption: transform.feedbackOption || null,
        feedbackOptions: Array.isArray(transform.feedbackOptions) ? transform.feedbackOptions : (transform.feedbackOption ? [transform.feedbackOption] : []),
        createdAt: new Date(),
      };
      const withoutTarget = versions.filter((version) => Number(version.version) !== Number(transform.targetVersion));
      withoutTarget.push(nextVersion);
      withoutTarget.sort((a, b) => Number(a.version) - Number(b.version));
      await Offering.findByIdAndUpdate(offeringId, {
        componentPins: mergeComponentPins(offering.componentPins, placement.pins),
        outputImageUrl: versionUrl,
        outputImagePath: placement.fullPreviewUrl || placement.currentPreviewUrl,
        previewImagePath: placement.currentPreviewUrl,
        previewVersions: withoutTarget,
        repinPass: Number(transform.targetVersion),
        outputVideoUrl: null,
        outputVideoPath: null,
        downloadUrl: null,
        pipelineStatus: 'preview_ready',
        savedStep: 4,
        status: 'active',
        lastError: null,
        previewRequestKey,
      });
    } catch (error) {
      await Offering.findByIdAndUpdate(offeringId, {
        pipelineStatus: 'failed',
        lastError: error.message,
        previewRequestKey,
      });
    } finally {
      repinRuns.delete(runKey);
    }
  })();

  repinRuns.set(runKey, run);
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
        outputImagePath: placement.fullPreviewUrl || placement.previewUrl,
        previewImagePath: placement.fullPreviewUrl || placement.previewUrl,
        previewVersions: [{ version: 1, url: previewUrl, createdAt: new Date() }],
        repinPass: 1,
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

const VIDEO_PROMPTS = {
  'zoom-in':'A clearly visible continuous camera push forward toward the elevator for the entire 5-second clip. The camera begins at the exact viewpoint shown in the input image and steadily moves closer, ending noticeably closer than it started. The elevator doors and call panel become progressively larger in the frame from the first frame to the last frame, with realistic perspective change and gentle natural parallax. The forward camera movement must begin immediately in the first second, remain visible throughout the clip, and finish with a smooth slowdown. This is physical forward camera movement, not an abrupt digital zoom. Keep the elevator centered and preserve the original architectural layout, wall textures, call panel, buttons, floor, ceiling, signage, lighting, and reflections. No people and no new objects, panels, text, buttons, or signs. No sideways pan, orbit, backward movement, or vertical movement. Stable indoor lighting, smooth cinematic motion, photorealistic, temporally consistent, 5-second clip.',


  'pan': 'A clearly visible slow cinematic camera arc toward the existing elevator LCI call panel for the entire 5-second clip. First identify which side of the elevator contains the real LCI panel in the input image. If the LCI is on the right side, smoothly move and arc the camera toward the right. If the LCI is on the left side, smoothly move and arc the camera toward the left. The movement must begin during the first second and continue steadily throughout the clip, ending noticeably closer to the LCI side than it started. Follow a gentle shallow curved path with realistic lateral parallax while maintaining a comfortable distance from the wall. The LCI becomes slightly more prominent, but do not move so close that it becomes a close-up or causes the elevator to leave the frame. The camera gently turns toward the elevator and LCI while moving, then slows smoothly at the end. This is camera movement only. Preserve the exact elevator, LCI panel, buttons, walls, floor, ceiling, signage, lighting, reflections, textures, and architectural geometry from the input image.   No movement away from the LCI, no movement toward the opposite wall, no abrupt zoom, no vertical movement, no camera shake, and no door movement. Smooth realistic arc movement, natural perspective change, photorealistic, temporally consistent, 5-second clip.',

  'door-functionality': 'The elevator doors perform a single smooth realistic action. If the doors are closed in the input image they slide open from center to fully open revealing the elevator interior. If the doors are open in the input image they slide closed from sides to fully shut. Camera position is completely fixed and does not move at all. All existing components — call panel, buttons, walls, floor, ceiling, lighting — remain exactly in place and unchanged. No new objects, panels, text, logos, or signage are created. Realistic metal door sliding mechanics, natural consistent reflections on stainless steel, constant stable indoor lighting, no flickering, no exposure change, no texture shimmer on any surface, photorealistic, temporally consistent, 5 second clip.'
};

const VIDEO_NEGATIVE_PROMPT = [
  'cartoon',
  'animation',
  'CGI',
  '3d render',
  'fake render',
  'warped elevator',
  'distorted doors',
  'bending metal',
  'changing wall panels',
  'duplicated elevator doors',
  'extra panels',
  'flickering display',
  'unreadable display',
  'blurry',
  'low quality',
  'heavy camera shake',
  'fast pan',
  'jump cut',
  'sudden zoom',
  'sudden lighting change',
  'people',
  'watermark',
  'logo',
  'added text',
].join(', ');

const VIDEO_STATIC_DOOR_NEGATIVE_PROMPT = [
  VIDEO_NEGATIVE_PROMPT,
  'opening elevator doors',
  'closing elevator doors',
  'sliding elevator doors',
  'elevator door motion',
  'moving door panels',
  'cabin reveal',
  'changing elevator door state',
].join(', ');

const normalizeVideoMotion = (value) => {
  const normalized = String(value || '').trim().toLowerCase().replace(/_/g, '-');
  if (normalized === 'door-functionality') return 'door-functionality';
  if (['pan', 'pan-lr', 'pan-rl', 'pan-l-r', 'pan-r-l', 'pan-left-right', 'pan-right-left'].includes(normalized)) return 'pan';
  if (['zoom-in'].includes(normalized)) return normalized;
  return null;
};

const videoMotionForOptions = (videoOptions = {}) => {
  return normalizeVideoMotion(videoOptions.mode)
    || normalizeVideoMotion(videoOptions.motion)
    || normalizeVideoMotion(videoOptions.motionStyle)
    || 'zoom-in';
};

const videoPromptForOptions = (videoOptions = {}) => {
  const motion = videoMotionForOptions(videoOptions);
  return VIDEO_PROMPTS[motion] || VIDEO_PROMPTS['zoom-in'];
};

const videoNegativePromptForOptions = (videoOptions = {}) => {
  return videoMotionForOptions(videoOptions) === 'door-functionality'
    ? VIDEO_NEGATIVE_PROMPT
    : VIDEO_STATIC_DOOR_NEGATIVE_PROMPT;
};

const qualityDimensions = (quality) => {
  switch (quality) {
    case '360p':
      return { width: 360, height: 640 };
    case '480p':
      return { width: 480, height: 640 };
    case '720p':
      return { width: 640, height: 854 };
    case '1080p':
    default:
      return { width: 720, height: 960 };
  }
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const isComfyAlive = async () => {
  try {
    await axios.get(`${COMFY_URL}/system_stats`, { timeout: 2500 });
    return true;
  } catch (_) {
    return false;
  }
};

const ensureComfyRunning = async () => {
  if (await isComfyAlive()) return;
  if (comfyStartPromise) return comfyStartPromise;

  comfyStartPromise = (async () => {
    if (!(await fileExists(COMFY_START_SCRIPT))) {
      throw new Error(`ComfyUI start script not found at ${COMFY_START_SCRIPT}`);
    }

    const child = spawn('bash', [COMFY_START_SCRIPT], {
      cwd: COMFY_ROOT,
      detached: true,
      stdio: 'ignore',
    });
    child.unref();

    for (let attempt = 0; attempt < 90; attempt += 1) {
      await sleep(2000);
      if (await isComfyAlive()) return;
    }

    throw new Error('ComfyUI did not start on port 8188 within 3 minutes. Check /workspace/Kone/vdotest/logs.');
  })().finally(() => {
    comfyStartPromise = null;
  });

  return comfyStartPromise;
};

const generateComfyVideo = async ({ inputPath, outputDir, videoOptions }) => {
  await ensureComfyRunning();

  const pythonPath = (await fileExists(COMFY_PYTHON)) ? COMFY_PYTHON : '/usr/bin/python3';
  const outputVideoPath = path.join(outputDir, 'elevator_animation.mp4');
  const metadataPath = path.join(outputDir, 'elevator_animation.json');
  const { width, height } = qualityDimensions(videoOptions.quality);
  const prompt = videoPromptForOptions(videoOptions);
  const negativePrompt = videoNegativePromptForOptions(videoOptions);
  const motion = videoMotionForOptions(videoOptions);
  const quality = videoOptions.quality || '1080p';
  const workflow = 'wan_i2v';
  const seed = Math.floor(Date.now() % 1000000000);
  const inputSha256 = await fileSha256(inputPath);
  const existingMeta = await readJsonIfExists(metadataPath);

  if (
    (await isValidVideoFile(outputVideoPath)) &&
    existingMeta.engine === 'comfy_wan' &&
    existingMeta.motion === motion &&
    existingMeta.quality === quality &&
    existingMeta.workflow === workflow &&
    existingMeta.prompt === prompt &&
    existingMeta.input_sha256 === inputSha256
  ) {
    return;
  }

  try {
    await fsPromises.rm(outputVideoPath, { force: true });
    await execFileAsync(
      pythonPath,
      [
        COMFY_RUNNER,
        '--image',
        inputPath,
        '--prompt',
        prompt,
        '--negative',
        negativePrompt,
        '--comfy-url',
        COMFY_URL,
        '--width',
        String(width),
        '--height',
        String(height),
        '--length',
        String(81),
        '--fps',
        '16',
        '--seed',
        String(seed),
        '--motion',
        motion,
        '--wait',
        '--output',
        outputVideoPath,
      ],
      {
        cwd: COMFY_ROOT,
        timeout: 0,
        maxBuffer: 1024 * 1024 * 20,
      }
    );
  } catch (error) {
    const message = error.stderr || error.stdout || error.message || 'ComfyUI video generation failed';
    throw new Error(message);
  }

  if (!(await isValidVideoFile(outputVideoPath))) {
    throw new Error('ComfyUI completed but did not produce a valid elevator_animation.mp4');
  }

  await fsPromises.writeFile(
    metadataPath,
    JSON.stringify(
      {
        engine: 'comfy_wan',
        motion,
        quality,
        workflow,
        input_sha256: inputSha256,
        raw_video_options: videoOptions,
        selected_prompt_key: motion,
        prompt,
        negative_prompt: negativePrompt,
        comfy: {
          url: COMFY_URL,
          width,
          height,
          length: 81,
          fps: 16,
          seed,
        },
        generatedAt: new Date().toISOString(),
      },
      null,
      2
    )
  );
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
    const originalBlobPath = uploadedImageBlobPath({
      userId: req.user.id,
      projectId: offering.projectId,
      offeringId,
      fileName: 'original-image.jpg',
    });

    uploadAzureCopy(job.inputPath, originalBlobPath, 'image/jpeg', async (result) => {
      await Offering.findByIdAndUpdate(offeringId, {
        uploadedImageBlobPath: result.blobPath,
        'azureSyncStatus.uploadedImage': 'success',
      });
    });

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
      selectedComponentAssets: componentAssets,
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


const repinPreview = async (req, res) => {
  try {
    const {
      imageId,
      offeringId,
      components = [],
      environments = [],
      component_assets: componentAssets = {},
      preview_request_key: previewRequestKey = null,
      transform,
      transforms = [],
    } = req.body;

    if (!transform || !transform.componentKey) {
      return res.status(400).json({ success: false, message: 'Repin transform is required' });
    }
    const job = await getOrRecoverJob(imageId, req.user.id);
    if (!job) {
      return res.status(404).json({ success: false, message: 'Invalid imageId' });
    }
    if (job.userId !== req.user.id) {
      return res.status(403).json({ success: false, message: 'Forbidden' });
    }
    const offering = await getOwnedOffering(offeringId, req.user.id);
    if (!offering) {
      return res.status(404).json({ success: false, message: 'Invalid offeringId' });
    }
    if (Number(transform.targetVersion) > 5) {
      return res.status(400).json({ success: false, message: 'Version limit reached. Choose the best saved version to continue.' });
    }

    await Offering.findByIdAndUpdate(offeringId, {
      selectedComponents: components.length ? components : offering.selectedComponents,
      selectedComponentAssets: Object.keys(componentAssets || {}).length ? componentAssets : offering.selectedComponentAssets,
      environments: environments.length ? environments : offering.environments,
      outputVideoUrl: null,
      outputVideoPath: null,
      downloadUrl: null,
      pipelineStatus: 'processing',
      lastError: null,
      savedStep: 4,
      status: 'active',
      previewRequestKey,
    });

    startRepinRun({
      offeringId,
      imageId,
      userId: req.user.id,
      transform,
      transforms,
      componentAssets,
      environments: environments.length ? environments : offering.environments,
      previewRequestKey,
    });

    return res.status(200).json({ success: true, status: 'processing', preview_request_key: previewRequestKey });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
  }
};


const repinEraser = async (req, res) => {
  try {
    const {
      imageId,
      offeringId,
      sourceVersion,
      sourceBaseMode = 'version',
      maskDataUrl,
      transform,
    } = req.body;

    const job = await getOrRecoverJob(imageId, req.user.id);
    if (!job) return res.status(404).json({ success: false, message: 'Invalid imageId' });
    if (job.userId !== req.user.id) return res.status(403).json({ success: false, message: 'Forbidden' });
    const offering = await getOwnedOffering(offeringId, req.user.id);
    if (!offering) return res.status(404).json({ success: false, message: 'Invalid offeringId' });

    const storageDir = getLogicStorageDir(req.user.id, imageId);
    const uploadsDir = path.join(storageDir, 'uploads');
    const previewDir = path.join(storageDir, 'preview');
    const outputDir = getOutputDir(imageId);
    await Promise.all([uploadsDir, previewDir, outputDir].map((dir) => fsPromises.mkdir(dir, { recursive: true })));

    const fallbackInput = getUploadInputPath(imageId);
    const sourcePath = sourceBaseMode === 'original'
      ? fallbackInput
      : (Number(sourceVersion) > 1
          ? path.join(outputDir, `final_output_v${sourceVersion}.png`)
          : path.join(outputDir, 'final_output.png'));
    const sourceImage = (await fileExists(sourcePath)) ? sourcePath : ((await fileExists(path.join(outputDir, 'final_output.png'))) ? path.join(outputDir, 'final_output.png') : fallbackInput);
    await fsPromises.copyFile(sourceImage, path.join(uploadsDir, `repin_source_v${sourceVersion}.png`));

    const { data } = await axios.post(`${LOGIC_URL}/repin-erase`, {
      session_id: `auth_${req.user.id}`,
      project_id: imageId,
      project_name: imageId,
      storage_dir: storageDir,
      source_version: sourceVersion,
      source_base_mode: sourceBaseMode,
      mask_data_url: maskDataUrl,
      transform: withLocalRepinFiles(transform),
    }, { timeout: 0 });

    if (!data?.ok) throw new Error(data?.error || 'Magic Eraser failed');
    return res.status(200).json({
      success: true,
      repinBackgroundUrl: storagePublicUrl(path.join(storageDir, data.repin_background_url || data.preview_url)),
      repinBackgroundDisplayUrl: storagePublicUrl(path.join(storageDir, data.preview_url || data.repin_background_url)),
      maskUrl: storagePublicUrl(path.join(storageDir, data.mask_url || '')),
    });
  } catch (error) {
    return res.status(500).json({ success: false, message: error.message });
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

    let inputPath = requestedSourcePath && (await fileExists(requestedSourcePath))
      ? requestedSourcePath
      : job.inputPath;

    // The UI displays compressed *_web.jpg previews. Wan must receive
    // the full-resolution PNG for the exact version selected by the user.
    if (inputPath && /_web\.(jpg|jpeg)$/i.test(inputPath)) {
      const selectedVersionFullResolutionPath = inputPath.replace(
        /_web\.(jpg|jpeg)$/i,
        '.png'
      );

      if (await fileExists(selectedVersionFullResolutionPath)) {
        inputPath = selectedVersionFullResolutionPath;
      }
    }

    // Preserve 01_original.jpg, final_output.png and all version files.
    // Use a dedicated staging copy containing the selected full-resolution
    // version for this Wan generation.
    const videoInputPath = path.join(outputDir, 'video_input.png');

    if (path.resolve(inputPath) !== path.resolve(videoInputPath)) {
      await fsPromises.copyFile(inputPath, videoInputPath);
    }
    const offeringId = req.body.offeringId;

    if (offeringId) {
      const offering = await getOwnedOffering(offeringId, req.user.id);

      if (offering) {
        const selectedBlobPath = selectedImageBlobPath({
          userId: req.user.id,
          projectId: offering.projectId,
          offeringId,
          fileName: 'selected-for-video.png',
        });

        uploadAzureCopy(videoInputPath, selectedBlobPath, 'image/png', async (result) => {
          await Offering.findByIdAndUpdate(offeringId, {
            selectedImageBlobPath: result.blobPath,
            'azureSyncStatus.selectedImage': 'success',
          });
        });
      }
    }

    await generateComfyVideo({
      inputPath: videoInputPath,
      outputDir,
      videoOptions,
    });
    const finalVideoPath = path.join(outputDir, 'elevator_animation.mp4');

    if (offeringId && await fileExists(finalVideoPath)) {
      const offering = await getOwnedOffering(offeringId, req.user.id);

      if (offering) {
        const videoBlobPath = finalVideoBlobPath({
          userId: req.user.id,
          projectId: offering.projectId,
          offeringId,
          fileName: 'final-video.mp4',
        });

        const originalBlobPath = uploadedImageBlobPath({
          userId: req.user.id,
          projectId: offering.projectId,
          offeringId,
          fileName: 'original-image.jpg',
        });

        const selectedBlobPath = selectedImageBlobPath({
          userId: req.user.id,
          projectId: offering.projectId,
          offeringId,
          fileName: 'selected-for-video.png',
        });

        const originalInputPath = getUploadInputPath(imageId);
        if (await fileExists(originalInputPath)) {
          const originalUploadResult = await uploadFileToAzure(originalInputPath, originalBlobPath, 'image/jpeg');
          if (originalUploadResult.success) {
            await Offering.findByIdAndUpdate(offeringId, {
              uploadedImageBlobPath: originalUploadResult.blobPath,
              'azureSyncStatus.uploadedImage': 'success',
            });
          } else {
            console.warn('[Azure] Original image backup upload failed/skipped:', originalUploadResult);
          }
        } else {
          console.warn('[Azure] Original image backup upload skipped: local input missing', originalInputPath);
        }

        const project = await Project.findById(offering.projectId);
        const user = await User.findById(req.user.id);

        const videoMetadata = {
          userId: req.user.id,
          projectId: String(offering.projectId),
          offeringId,
          personName: user?.name || req.user.name || '',
          projectName: project?.name || '',
          beforeBlobPath: originalBlobPath,
          afterBlobPath: selectedBlobPath,
          videoBlobPath,
        };

        uploadFileToAzure(finalVideoPath, videoBlobPath, 'video/mp4', videoMetadata)
          .then(async (result) => {
            if (!result.success) {
              console.warn('[Azure] Final video copy failed/skipped:', result);
              return;
            }

            console.log('[Azure] Copied final video with metadata:', result.blobPath);

            await Offering.findByIdAndUpdate(offeringId, {
              finalVideoBlobPath: result.blobPath,
              'azureSyncStatus.finalVideo': 'success',
            });
          })
          .catch((error) => {
            console.error('[Azure] Final video copy crashed:', error.message);
          });
      }
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
  repinPreview,
  repinEraser,
  generateVideo,
};
