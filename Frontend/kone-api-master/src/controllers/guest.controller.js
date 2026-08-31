const crypto = require('crypto');
const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const axios = require('axios');
const archiver = require('archiver');
const { execFile, spawn } = require('child_process');
const { promisify } = require('util');
const catchAsync = require('../utils/catchAsync');

const API_ROOT = path.join(__dirname, '..', '..');
const STORAGE_ROOT = path.join(API_ROOT, 'storage');
const LOGIC_URL = process.env.LOGIC_URL || 'http://localhost:8001';
const execFileAsync = promisify(execFile);
const COMFY_ROOT = process.env.COMFY_ROOT || '/workspace/Kone/vdotest';
const COMFY_URL = process.env.COMFY_URL || 'http://127.0.0.1:8188';
const COMFY_RUNNER = process.env.COMFY_RUNNER || path.join(COMFY_ROOT, 'run_i2v_api.py');
const COMFY_START_SCRIPT = process.env.COMFY_START_SCRIPT || path.join(COMFY_ROOT, 'scripts', 'start_comfy_logged.sh');
const COMFY_PYTHON = process.env.COMFY_PYTHON || '/usr/bin/python3';
const componentRunQueues = new Map();
const latestComponentRunKeys = new Map();
let comfyStartPromise = null;

const VIDEO_PROMPTS = {
  'zoom-in': 'Photorealistic premium commercial video of the exact same elevator scene. Camera motion only: a slow smooth push-in toward the elevator entrance and selected components. The elevator doors stay fully closed and fixed for the entire clip. Preserve exact architecture, wall panels, lighting, reflections, proportions, product placement, and door state. Stable geometry, natural indoor light, realistic commercial camera movement, no people, no added text.',
  'pan': 'Photorealistic premium commercial video of the exact same elevator scene. Camera motion only: a slow controlled cinematic pan across the elevator entrance. The elevator doors stay fully closed and fixed for the entire clip; no opening, no closing, no sliding door motion, no cabin reveal. Preserve exact geometry, materials, reflections, lighting, wall panels, and product placement. Smooth lateral camera movement, no people, no added text.',
  'door-functionality': 'Photorealistic premium commercial product demo of the exact same elevator scene showing elevator door functionality. The camera stays locked off and stable while the elevator doors gently open and close once with realistic metal reflections. The surrounding lobby, panels, lighting, and installed components remain stable and unchanged. No people, no added text.',
};

const VIDEO_NEGATIVE_PROMPT = 'cartoon, animation, CGI, 3d render, fake render, warped elevator, distorted doors, bending metal, changing wall panels, duplicated elevator doors, extra panels, flickering display, unreadable display, blurry, low quality, heavy camera shake, fast pan, jump cut, sudden zoom, sudden lighting change, people, watermark, logo, added text';
const VIDEO_STATIC_DOOR_NEGATIVE_PROMPT = `${VIDEO_NEGATIVE_PROMPT}, opening elevator doors, closing elevator doors, sliding elevator doors, elevator door motion, moving door panels, cabin reveal, changing elevator door state`;

function safeName(value) {
  return String(value || '').replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 80);
}

function projectDir(sessionId, projectId) {
  return path.join(STORAGE_ROOT, 'guest', safeName(sessionId), safeName(projectId));
}

async function ensureProjectDirs(root) {
  await Promise.all(['uploads', 'pipeline', 'preview', 'video', 'downloads'].map((d) => fsp.mkdir(path.join(root, d), { recursive: true })));
}

async function readStatus(root) {
  const file = path.join(root, 'status.json');
  if (!fs.existsSync(file)) return { status: 'idle', preview_url: null, video_url: null, download_url: null, error: null };
  try {
    return JSON.parse(await fsp.readFile(file, 'utf-8'));
  } catch {
    return { status: 'processing', preview_url: null, video_url: null, download_url: null, error: null };
  }
}

async function writeStatus(root, status) {
  await fsp.mkdir(root, { recursive: true });
  const file = path.join(root, 'status.json');
  const tmp = path.join(root, `status.${process.pid}.${Date.now()}.${Math.random().toString(36).slice(2)}.tmp.json`);
  await fsp.writeFile(tmp, JSON.stringify(status, null, 2));
  await fsp.rename(tmp, file);
}

function publicStorageUrl(sessionId, projectId, filePath) {
  return filePath ? `/storage/guest/${safeName(sessionId)}/${safeName(projectId)}/${filePath}` : null;
}

function localStoragePathFromUrl(url) {
  if (!url || typeof url !== 'string') return null;
  const [pathname] = url.split('?');
  if (!pathname.startsWith('/storage/')) return null;
  const resolved = path.resolve(STORAGE_ROOT, pathname.replace('/storage/', ''));
  return resolved.startsWith(STORAGE_ROOT) ? resolved : null;
}

function hasManualEraserBackground(item = {}) {
  return (
    (Array.isArray(item.eraserHistory) && item.eraserHistory.length > 1) ||
    (item.magicEraserApplied && item.repinBackgroundUrl)
  );
}

function isSameComponentReEdit(item = {}) {
  return item.sourceVersionComponent && item.componentKey && (item.sourceVersionComponentId ? String(item.sourceVersionComponentId).toLowerCase() === String(item.componentId).toLowerCase() : String(item.sourceVersionComponent).toLowerCase() === String(item.componentKey).toLowerCase());
}

function withLocalRepinFiles(item = {}) {
  const useRepinBackground = hasManualEraserBackground(item) || isSameComponentReEdit(item);
  const currentUrlPath = localStoragePathFromUrl(item.repinBackgroundUrl);
  return {
    ...item,
    editableLayerPath: item.editableLayerPath || localStoragePathFromUrl(item.editableLayerUrl),
    repinBackgroundPath: useRepinBackground ? currentUrlPath : null,
  };
}

function stableRepinBackgroundPath(root, sourceVersion) {
  const versionKey = String(Number(sourceVersion) || 1);
  return path.join(root, 'repin', 'backgrounds', 'shared_background_v' + versionKey + '.png');
}

function stableRepinHistoryPath(root, sourceVersion) {
  const versionKey = String(Number(sourceVersion) || 1);
  return path.join(root, 'repin', 'backgrounds', 'history', 'repin_erased_v' + versionKey + '_' + crypto.randomUUID() + '.png');
}

async function persistRepinBackgroundSnapshot(root, sourceVersion, sourcePath) {
  if (!sourcePath || !(await fileExists(sourcePath))) return null;
  const historyPath = stableRepinHistoryPath(root, sourceVersion);
  const canonicalPath = stableRepinBackgroundPath(root, sourceVersion);
  await Promise.all([
    fsp.mkdir(path.dirname(historyPath), { recursive: true }),
    fsp.mkdir(path.dirname(canonicalPath), { recursive: true }),
  ]);
  await fsp.copyFile(sourcePath, historyPath);
  await fsp.copyFile(sourcePath, canonicalPath);
  return { historyPath, canonicalPath };
}

async function withStableRepinFiles(item = {}, root) {
  const localized = withLocalRepinFiles(item);
  if (!hasManualEraserBackground(item)) return localized;
  const sourceVersion = item.parentVersionId || item.sourceVersion || 1;
  const currentUrlPath = localStoragePathFromUrl(item.repinBackgroundUrl);
  if (item.repinBackgroundUrl) {
    if (currentUrlPath && (await fileExists(currentUrlPath))) {
      return { ...localized, repinBackgroundPath: currentUrlPath, magicEraserApplied: true };
    }
    throw new Error('Current Magic Eraser background snapshot is missing');
  }
  const canonicalPath = stableRepinBackgroundPath(root, sourceVersion);
  if (!(await fileExists(canonicalPath))) {
    throw new Error('Current Magic Eraser background snapshot is missing');
  }
  return {
    ...localized,
    repinBackgroundPath: canonicalPath,
    magicEraserApplied: true,
  };
}

async function readJsonIfExists(file) {
  if (!fs.existsSync(file)) return {};
  try {
    return JSON.parse(await fsp.readFile(file, 'utf-8'));
  } catch {
    return {};
  }
}

function validPlacementGeometry(preprocessing) {
  const geometry = preprocessing?.geometry;
  const originalWidth = Number(geometry?.original_size?.width);
  const originalHeight = Number(geometry?.original_size?.height);
  const matrix = geometry?.working_to_original;
  if (
    !Number.isFinite(originalWidth) ||
    originalWidth <= 0 ||
    !Number.isFinite(originalHeight) ||
    originalHeight <= 0 ||
    !Array.isArray(matrix) ||
    matrix.length !== 3
  ) {
    return null;
  }
  const normalizedMatrix = matrix.map((row) => (Array.isArray(row) ? row.map(Number) : []));
  if (normalizedMatrix.some((row) => row.length !== 3 || row.some((value) => !Number.isFinite(value)))) {
    return null;
  }
  return { originalWidth, originalHeight, workingToOriginal: normalizedMatrix };
}

function transformPlacementPoint(matrix, x, y) {
  const q0 = matrix[0][0] * x + matrix[0][1] * y + matrix[0][2];
  const q1 = matrix[1][0] * x + matrix[1][1] * y + matrix[1][2];
  const q2 = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2];
  if (!Number.isFinite(q0) || !Number.isFinite(q1) || !Number.isFinite(q2) || Math.abs(q2) < 1e-12) return null;
  return [q0 / q2, q1 / q2];
}

function clampPlacementCoordinate(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function placementBboxToOriginal(bbox, geometry) {
  if (!geometry) return null;
  const [x1, y1, x2, y2] = bbox;
  const points = [
    transformPlacementPoint(geometry.workingToOriginal, x1, y1),
    transformPlacementPoint(geometry.workingToOriginal, x2, y1),
    transformPlacementPoint(geometry.workingToOriginal, x2, y2),
    transformPlacementPoint(geometry.workingToOriginal, x1, y2),
  ];
  if (points.some((point) => !point)) return null;
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  const ox1 = clampPlacementCoordinate(Math.min(...xs), 0, geometry.originalWidth);
  const oy1 = clampPlacementCoordinate(Math.min(...ys), 0, geometry.originalHeight);
  const ox2 = clampPlacementCoordinate(Math.max(...xs), 0, geometry.originalWidth);
  const oy2 = clampPlacementCoordinate(Math.max(...ys), 0, geometry.originalHeight);
  if (ox2 <= ox1 || oy2 <= oy1) return null;
  return [ox1, oy1, ox2, oy2];
}

async function fileExists(file) {
  try {
    await fsp.access(file);
    return true;
  } catch {
    return false;
  }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function normalizeVideoMotion(value) {
  const normalized = String(value || '').trim().toLowerCase().replace(/_/g, '-');
  if (normalized === 'door-functionality') return 'door-functionality';
  if (['pan', 'pan-lr', 'pan-rl', 'pan-l-r', 'pan-r-l', 'pan-left-right', 'pan-right-left'].includes(normalized)) return 'pan';
  if (['zoom-in'].includes(normalized)) return normalized;
  return null;
}

function videoMotionForOptions(videoOptions = {}) {
  return normalizeVideoMotion(videoOptions.mode)
    || normalizeVideoMotion(videoOptions.motion)
    || normalizeVideoMotion(videoOptions.motionStyle)
    || 'zoom-in';
}

function videoPromptForOptions(videoOptions = {}) {
  const motion = videoMotionForOptions(videoOptions);
  return VIDEO_PROMPTS[motion] || VIDEO_PROMPTS['zoom-in'];
}

function videoNegativePromptForOptions(videoOptions = {}) {
  return videoMotionForOptions(videoOptions) === 'door-functionality'
    ? VIDEO_NEGATIVE_PROMPT
    : VIDEO_STATIC_DOOR_NEGATIVE_PROMPT;
}

function qualityDimensions(quality) {
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
}

async function isComfyAlive() {
  try {
    await axios.get(`${COMFY_URL}/system_stats`, { timeout: 2500 });
    return true;
  } catch (_) {
    return false;
  }
}

async function ensureComfyRunning() {
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
}

async function generateComfyVideo({ inputPath, outputVideoPath, metadataPath, videoOptions }) {
  await ensureComfyRunning();

  const pythonPath = (await fileExists(COMFY_PYTHON)) ? COMFY_PYTHON : '/usr/bin/python3';
  const { width, height } = qualityDimensions(videoOptions.quality);
  const prompt = videoPromptForOptions(videoOptions);
  const negativePrompt = videoNegativePromptForOptions(videoOptions);
  const motion = videoMotionForOptions(videoOptions);
  const quality = videoOptions.quality || '1080p';
  const workflow = 'wan_i2v';
  const seed = Math.floor(Date.now() % 1000000000);
  const existingMeta = await readJsonIfExists(metadataPath);

  if (
    (await fileExists(outputVideoPath)) &&
    existingMeta.engine === 'comfy_wan' &&
    existingMeta.motion === motion &&
    existingMeta.quality === quality &&
    existingMeta.workflow === workflow &&
    existingMeta.prompt === prompt
  ) {
    return;
  }

  try {
    await fsp.rm(outputVideoPath, { force: true });
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

  if (!(await fileExists(outputVideoPath))) {
    throw new Error('ComfyUI completed but did not produce elevator_animation.mp4');
  }

  await fsp.writeFile(
    metadataPath,
    JSON.stringify(
      {
        engine: 'comfy_wan',
        motion,
        quality,
        workflow,
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
}

function isWanEngine(value) {
  return ['wan', 'wan2.2', 'wan22'].includes(String(value || '').trim().toLowerCase());
}

function isComfyEngine(value) {
  return ['comfy', 'comfy_wan', 'comfy_i2v', 'comfy_flf2v', 'wan_comfy'].includes(String(value || '').trim().toLowerCase());
}

function shouldRegenerateVideo(videoExists, currentVideoMeta, videoOptions, requestedQuality) {
  if (!videoExists) return true;

  const currentIsPremium = isWanEngine(currentVideoMeta.engine) || isComfyEngine(currentVideoMeta.engine);
  const requestedIsPremium = isWanEngine(videoOptions.engine) || isComfyEngine(videoOptions.engine) || Boolean(videoOptions.force_wan || videoOptions.use_wan);
  if (currentIsPremium) {
    return Boolean(videoOptions.engine) && !requestedIsPremium;
  }

  return requestedIsPremium || currentVideoMeta.quality !== requestedQuality;
}

async function componentPinsFromPlacement(root, urlFor = null) {
  const placements = await readJsonIfExists(path.join(root, 'pipeline', 'component_placements.json'));
  if (!Array.isArray(placements)) return [];
  const detections = await readJsonIfExists(path.join(root, 'pipeline', 'elevator_detections.json'));
  const preprocessing = await readJsonIfExists(path.join(root, 'pipeline', 'preprocessing.json'));
  const geometry = validPlacementGeometry(preprocessing);
  const legacyWidth = Number(detections?.metadata?.image_width) || 0;
  const legacyHeight = Number(detections?.metadata?.image_height) || 0;
  if ((!legacyWidth || !legacyHeight) && !geometry) return [];

  const supported = new Set(['kds', 'kds_2', 'kds_3', 'dcs1020', 'lci', 'cop', 'door', 'ceiling']);
  return placements
    .map((placement) => {
      const componentKey = String(placement.id || '').toLowerCase();
      if (!supported.has(componentKey)) return null;
      const bbox = placement.final_insertion_bbox || placement.final_component_placement?.bbox || placement.inpaint_bbox;
      if (!Array.isArray(bbox) || bbox.length !== 4) return null;
      const [x1, y1, x2, y2] = bbox.map(Number);
      if (![x1, y1, x2, y2].every(Number.isFinite)) return null;
      const rawBbox = [x1, y1, x2, y2];
      const transformedBbox = placementBboxToOriginal(rawBbox, geometry);
      const pinBbox = transformedBbox || rawBbox;
      const pinWidth = transformedBbox ? geometry.originalWidth : legacyWidth;
      const pinHeight = transformedBbox ? geometry.originalHeight : legacyHeight;
      if (!pinWidth || !pinHeight) return null;
      return {
        componentKey,
        x: Math.round(((pinBbox[0] + pinBbox[2]) / 2 / pinWidth) * 100),
        y: Math.round(((pinBbox[1] + pinBbox[3]) / 2 / pinHeight) * 100),
        aiPlaced: true,
        bbox: pinBbox,
        imageWidth: pinWidth,
        imageHeight: pinHeight,
        editableLayerUrl: urlFor && placement.editable_layer_path ? urlFor(path.relative(root, placement.editable_layer_path)) : null,
        repinBackgroundUrl: urlFor && placement.repin_background_path ? urlFor(path.relative(root, placement.repin_background_path)) : null,
        repinBackgroundDisplayUrl: urlFor && (placement.repin_background_web_path || placement.repin_background_path) ? urlFor(path.relative(root, placement.repin_background_web_path || placement.repin_background_path)) : null,
      };
    })
    .filter(Boolean);
}



const createSession = (req, res) => {
  res.send({ session_id: `guest_${crypto.randomUUID()}` });
};

const uploadImage = catchAsync(async (req, res) => {
  const { session_id: sessionId, project_id: projectId } = req.body;
  if (!req.file || !sessionId || !projectId) {
    return res.status(400).send({ success: false, message: 'Missing image, session_id, or project_id' });
  }

  const root = projectDir(sessionId, projectId);
  await ensureProjectDirs(root);
  await Promise.all(['pipeline', 'preview', 'video', 'downloads', 'repin'].map((d) => fsp.rm(path.join(root, d), { recursive: true, force: true })));
  await ensureProjectDirs(root);
  await fsp.copyFile(req.file.path, path.join(root, 'uploads', 'input.jpg'));
  await fsp.rm(req.file.path, { force: true });
  await writeStatus(root, { status: 'uploaded', preview_url: null, video_url: null, download_url: null, error: null });
  res.send({ success: true, image_url: `${publicStorageUrl(sessionId, projectId, 'uploads/input.jpg')}?v=${Date.now()}` });
});

const precheck = catchAsync(async (req, res) => {
  const { session_id: sessionId, project_id: projectId, project_name: projectName } = req.body;
  const root = projectDir(sessionId, projectId);
  try {
    const { data } = await axios.post(`${LOGIC_URL}/precheck`, {
      session_id: sessionId,
      project_id: projectId,
      project_name: projectName,
      storage_dir: root,
    }, { timeout: 15000 });
    res.send(data);
  } catch (error) {
    const message = error.code === 'ECONNABORTED'
      ? 'Image validation timed out. Please upload a clear elevator image and try again.'
      : 'Could not validate this image. Please upload a valid elevator image.';
    await writeStatus(root, { status: 'precheck_failed', preview_url: null, video_url: null, download_url: null, error: message });
    res.send({ ok: false, next_action: 'reupload', reason: message, message });
  }
});

const runComponents = catchAsync(async (req, res) => {
  const {
    session_id: sessionId,
    project_id: projectId,
    project_name: projectName,
    selected_components: selectedComponents,
    component_assets: componentAssets,
    component_instances: componentInstances,
    environments,
    preview_request_key: previewRequestKey,
  } = req.body;
  const root = projectDir(sessionId, projectId);
  const queueKey = root;
  const latestKey = previewRequestKey || null;
  latestComponentRunKeys.set(queueKey, latestKey);
  const requestStatus = { status: 'processing', preview_url: null, video_url: null, download_url: null, error: null, preview_request_key: previewRequestKey || null };
  await writeStatus(root, requestStatus);
  const previousRun = componentRunQueues.get(queueKey) || Promise.resolve();
  const queuedRun = previousRun
    .catch(() => {})
    .then(async () => {
      if (latestComponentRunKeys.get(queueKey) !== latestKey) return;
      try {
        await axios.post(`${LOGIC_URL}/run-components`, {
          session_id: sessionId,
          project_id: projectId,
          project_name: projectName,
          storage_dir: root,
          selected_components: selectedComponents,
          component_assets: componentAssets,
          component_instances: componentInstances,
          environments,
          preview_request_key: previewRequestKey,
        });
        const current = await readStatus(root);
        if (latestComponentRunKeys.get(queueKey) === latestKey) {
          await writeStatus(root, { ...current, preview_request_key: latestKey });
        } else {
          await writeStatus(root, { status: 'processing', preview_url: null, video_url: null, download_url: null, error: null, preview_request_key: latestComponentRunKeys.get(queueKey) || null });
        }
      } catch (error) {
        if (latestComponentRunKeys.get(queueKey) === latestKey) {
          await writeStatus(root, { status: 'failed', preview_url: null, video_url: null, download_url: null, error: error.message, preview_request_key: latestKey });
        }
      }
    })
    .finally(() => {
      if (componentRunQueues.get(queueKey) === queuedRun) {
        componentRunQueues.delete(queueKey);
        latestComponentRunKeys.delete(queueKey);
      }
    });
  componentRunQueues.set(queueKey, queuedRun);
  res.send({ ok: true, status: 'processing' });
});



const runRepinEraser = catchAsync(async (req, res) => {
  const {
    session_id: sessionId,
    project_id: projectId,
    project_name: projectName,
    source_version: sourceVersion,
    source_base_mode: sourceBaseMode = 'version',
    mask_data_url: maskDataUrl,
    transform,
  } = req.body;
  const root = projectDir(sessionId, projectId);
  await ensureProjectDirs(root);
  const { data } = await axios.post(`${LOGIC_URL}/repin-erase`, {
    session_id: sessionId,
    project_id: projectId,
    project_name: projectName,
    storage_dir: root,
    source_version: sourceVersion,
    source_base_mode: sourceBaseMode,
    mask_data_url: maskDataUrl,
    transform: withLocalRepinFiles(transform),
  }, { timeout: 0 });
  if (!data?.ok) throw new Error(data?.error || 'Magic Eraser failed');
  const stableSourceVersion = Number(sourceVersion || transform?.parentVersionId || transform?.sourceVersion || 1);
  const erasedRelativePath = data.repin_background_url || data.preview_url;
  const erasedPath = erasedRelativePath ? path.join(root, erasedRelativePath) : null;
  const persistedBackground = await persistRepinBackgroundSnapshot(root, stableSourceVersion, erasedPath);
  if (!persistedBackground) throw new Error('Stable Magic Eraser background was not created');
  const historyRelativePath = path.relative(root, persistedBackground.historyPath);
  res.send({
    ok: true,
    repinBackgroundUrl: publicStorageUrl(sessionId, projectId, historyRelativePath),
    repinBackgroundDisplayUrl: publicStorageUrl(sessionId, projectId, historyRelativePath),
    maskUrl: publicStorageUrl(sessionId, projectId, data.mask_url),
  });
});

const runRepin = catchAsync(async (req, res) => {
  const {
    session_id: sessionId,
    project_id: projectId,
    project_name: projectName,
    selected_components: selectedComponents,
    component_assets: componentAssets,
    environments,
    preview_request_key: previewRequestKey,
    transform,
    transforms = [],
  } = req.body;
  const root = projectDir(sessionId, projectId);
  const logicTransform = await withStableRepinFiles(transform, root);
  const logicTransforms = await Promise.all(transforms.map((item) => withStableRepinFiles(item, root)));
  const repinComponents = Array.from(new Set((logicTransforms.length ? logicTransforms : [logicTransform])
    .map((item) => item?.componentKey)
    .filter(Boolean)));
  const queueKey = root;
  const latestKey = previewRequestKey || null;
  const previousStatus = await readStatus(root);
  const previousPreviewVersions = Array.isArray(previousStatus.preview_versions) ? previousStatus.preview_versions : [];
  latestComponentRunKeys.set(queueKey, latestKey);
  await writeStatus(root, { status: 'processing', preview_url: null, video_url: null, download_url: null, error: null, preview_request_key: latestKey });
  const previousRun = componentRunQueues.get(queueKey) || Promise.resolve();
  const queuedRun = previousRun
    .catch(() => {})
    .then(async () => {
      if (latestComponentRunKeys.get(queueKey) !== latestKey) return;
      try {
        const { data } = await axios.post(`${LOGIC_URL}/repin-components`, {
          session_id: sessionId,
          project_id: projectId,
          project_name: projectName,
          storage_dir: root,
          selected_components: repinComponents.length ? repinComponents : selectedComponents,
          component_assets: componentAssets,
          environments,
          preview_request_key: previewRequestKey,
          transform: logicTransform,
          transforms: logicTransforms,
        }, { timeout: 0 });
        if (!data?.ok) throw new Error(data?.error || 'Repin preview failed');
        const current = await readStatus(root);
        if (latestComponentRunKeys.get(queueKey) === latestKey) {
          const repinVersions = Array.isArray(current.preview_versions) ? current.preview_versions : [];
          const versionsByNumber = new Map(previousPreviewVersions.map((version) => [Number(version.version), version]));
          repinVersions.forEach((version) => versionsByNumber.set(Number(version.version), version));
          const mergedVersions = Array.from(versionsByNumber.values()).sort((a, b) => Number(a.version) - Number(b.version));
          await writeStatus(root, { ...current, preview_request_key: latestKey, preview_versions: mergedVersions });
        }
      } catch (error) {
        if (latestComponentRunKeys.get(queueKey) === latestKey) {
          await writeStatus(root, { status: 'failed', preview_url: null, video_url: null, download_url: null, error: error.message, preview_request_key: latestKey });
        }
      }
    })
    .finally(() => {
      if (componentRunQueues.get(queueKey) === queuedRun) {
        componentRunQueues.delete(queueKey);
        latestComponentRunKeys.delete(queueKey);
      }
    });
  componentRunQueues.set(queueKey, queuedRun);
  res.send({ ok: true, status: 'processing' });
});

const status = catchAsync(async (req, res) => {
  const { session_id: sessionId, project_id: projectId } = req.query;
  const root = projectDir(sessionId, projectId);
  const current = await readStatus(root);
  const componentPins = await componentPinsFromPlacement(root, (filePath) => publicStorageUrl(sessionId, projectId, filePath));
  const publicVersionUrl = (value) => {
    if (!value || typeof value !== 'string') return value;
    if (value.startsWith('/storage/') || value.startsWith('/output/') || value.startsWith('http://') || value.startsWith('https://')) return value;
    return publicStorageUrl(sessionId, projectId, value);
  };
  const publicVersionTransform = (item) => item ? ({
    ...item,
    editableLayerPath: null,
    editableLayerUrl: publicVersionUrl(item.editableLayerUrl),
    repinBackgroundPath: null,
    repinBackgroundUrl: publicVersionUrl(item.repinBackgroundUrl),
    repinBackgroundDisplayUrl: publicVersionUrl(item.repinBackgroundDisplayUrl),
  }) : item;
  const previewVersions = Array.isArray(current.preview_versions)
    ? current.preview_versions.map((version) => ({
        ...version,
        url: publicVersionUrl(version.url),
        transform: publicVersionTransform(version.transform),
        transforms: Array.isArray(version.transforms) ? version.transforms.map(publicVersionTransform) : version.transforms,
      }))
    : undefined;
  res.send({
    ...current,
    preview_url: publicStorageUrl(sessionId, projectId, current.preview_url),
    video_url: publicStorageUrl(sessionId, projectId, current.video_url),
    component_pins: componentPins,
    preview_versions: previewVersions,
    download_url: current.status === 'ready_for_download'
      ? `/api/v1/guest/download?session_id=${encodeURIComponent(sessionId)}&project_id=${encodeURIComponent(projectId)}`
      : null,
  });
});

const generateVideo = catchAsync(async (req, res) => {
  const { session_id: sessionId, project_id: projectId, video_options: videoOptions } = req.body;
  const root = projectDir(sessionId, projectId);
  await writeStatus(root, { status: 'generating_video', preview_url: 'preview/final_output.png', video_url: null, download_url: null, error: null });
  console.log(`[guest/video] calling ComfyUI for ${projectId}`);
  generateComfyVideo({
    inputPath: path.join(root, 'preview', 'final_output.png'),
    outputVideoPath: path.join(root, 'video', 'elevator_animation.mp4'),
    metadataPath: path.join(root, 'video', 'elevator_animation.json'),
    videoOptions,
  }).then(() => writeStatus(root, {
    status: 'video_ready',
    preview_url: 'preview/final_output.png',
    video_url: 'video/elevator_animation.mp4',
    download_url: null,
    error: null,
  })).catch((error) => {
    console.error(`[guest/video] failed for ${projectId}: ${error.message}`);
    return writeStatus(root, { status: 'failed', preview_url: 'preview/final_output.png', video_url: null, download_url: null, error: error.message });
  });
  res.send({ ok: true, status: 'generating_video' });
});

const finalize = catchAsync(async (req, res) => {
  const { session_id: sessionId, project_id: projectId, video_options: videoOptions = {} } = req.body;
  const root = projectDir(sessionId, projectId);
  const downloads = path.join(root, 'downloads');
  await fsp.mkdir(downloads, { recursive: true });
  await fsp.rm(path.join(downloads, 'metadata.json'), { force: true });

  const preview = path.join(root, 'preview', 'final_output.png');
  const video = path.join(root, 'video', 'elevator_animation.mp4');
  const videoMeta = path.join(root, 'video', 'elevator_animation.json');
  const requestedQuality = ['360p', '480p', '720p', '1080p'].includes(videoOptions.quality) ? videoOptions.quality : '1080p';
  if (!fs.existsSync(preview)) return res.status(400).send({ ok: false, message: 'Preview file is not ready' });

  const currentVideoMeta = await readJsonIfExists(videoMeta);
  if (shouldRegenerateVideo(fs.existsSync(video), currentVideoMeta, videoOptions, requestedQuality)) {
    await generateComfyVideo({
      inputPath: preview,
      outputVideoPath: video,
      metadataPath: videoMeta,
      videoOptions: {
        ...videoOptions,
        quality: requestedQuality,
      },
    });
  }

  await fsp.copyFile(preview, path.join(downloads, 'final_output.png'));
  if (fs.existsSync(video)) {
    await fsp.copyFile(video, path.join(downloads, 'elevator_animation.mp4'));
  }
  await writeStatus(root, {
    status: 'ready_for_download',
    preview_url: 'preview/final_output.png',
    video_url: fs.existsSync(video) ? 'video/elevator_animation.mp4' : null,
    download_url: 'downloads',
    error: null,
  });
  res.send({ ok: true, status: 'ready_for_download' });
});

const download = catchAsync(async (req, res) => {
  const { session_id: sessionId, project_id: projectId, type } = req.query;
  const downloads = path.join(projectDir(sessionId, projectId), 'downloads');
  await fsp.rm(path.join(downloads, 'metadata.json'), { force: true });
  const selectedType = String(type || 'all');
  const singleFiles = {
    image: { path: path.join(downloads, 'final_output.png'), name: 'final_output.png' },
    video: { path: path.join(downloads, 'elevator_animation.mp4'), name: 'elevator_animation.mp4' },
  };
  if (Object.prototype.hasOwnProperty.call(singleFiles, selectedType)) {
    const file = singleFiles[selectedType];
    if (!fs.existsSync(file.path)) {
      return res.status(404).send({ ok: false, message: 'Requested output file is not ready' });
    }
    return res.download(file.path, file.name);
  }

  res.setHeader('Content-Type', 'application/zip');
  res.setHeader('Content-Disposition', 'attachment; filename="kone-output.zip"');
  const archive = archiver('zip');
  archive.pipe(res);
  archive.directory(downloads, false);
  archive.finalize();
});

module.exports = { createSession, uploadImage, precheck, runComponents, runRepin, runRepinEraser, status, generateVideo, finalize, download };
