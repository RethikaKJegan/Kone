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
  return Array.isArray(item.eraserHistory) && item.eraserHistory.length > 1;
}

function isSameComponentReEdit(item = {}) {
  return item.sourceVersionComponent && item.componentKey && String(item.sourceVersionComponent).toLowerCase() === String(item.componentKey).toLowerCase();
}

function withLocalRepinFiles(item = {}) {
  const useRepinBackground = Boolean(item.repinBackgroundPath || item.repinBackgroundUrl) || hasManualEraserBackground(item) || isSameComponentReEdit(item);
  return {
    ...item,
    editableLayerPath: item.editableLayerPath || localStoragePathFromUrl(item.editableLayerUrl),
    repinBackgroundPath: useRepinBackground ? (item.repinBackgroundPath || localStoragePathFromUrl(item.repinBackgroundUrl)) : null,
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
  await Promise.all(['pipeline', 'preview', 'video', 'downloads'].map((d) => fsp.rm(path.join(root, d), { recursive: true, force: true })));
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
  res.send({
    ok: true,
    repinBackgroundUrl: publicStorageUrl(sessionId, projectId, data.repin_background_url || data.preview_url),
    repinBackgroundDisplayUrl: publicStorageUrl(sessionId, projectId, data.preview_url || data.repin_background_url),
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
  const logicTransform = withLocalRepinFiles(transform);
  const logicTransforms = transforms.map((item) => withLocalRepinFiles(item));
  const repinComponents = Array.from(new Set((logicTransforms.length ? logicTransforms : [logicTransform])
    .map((item) => item?.componentKey)
    .filter(Boolean)));
  const queueKey = root;
  const latestKey = previewRequestKey || null;
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
          const existingVersions = Array.isArray(current.preview_versions) ? current.preview_versions : [];
          await writeStatus(root, { ...current, preview_request_key: latestKey, preview_versions: existingVersions });
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
  const previewVersions = Array.isArray(current.preview_versions)
    ? current.preview_versions.map((version) => ({
        ...version,
        url: publicVersionUrl(version.url),
        transform: version.transform ? {
          ...version.transform,
          editableLayerUrl: publicVersionUrl(version.transform.editableLayerUrl),
          repinBackgroundUrl: publicVersionUrl(version.transform.repinBackgroundUrl),
          repinBackgroundDisplayUrl: publicVersionUrl(version.transform.repinBackgroundDisplayUrl),
        } : version.transform,
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
