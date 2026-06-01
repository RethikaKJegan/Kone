const crypto = require('crypto');
const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const axios = require('axios');
const archiver = require('archiver');
const catchAsync = require('../utils/catchAsync');

const API_ROOT = path.join(__dirname, '..', '..');
const STORAGE_ROOT = path.join(API_ROOT, 'storage');
const LOGIC_URL = process.env.LOGIC_URL || 'http://localhost:8001';

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

async function readJsonIfExists(file) {
  if (!fs.existsSync(file)) return {};
  try {
    return JSON.parse(await fsp.readFile(file, 'utf-8'));
  } catch {
    return {};
  }
}

async function componentPinsFromPlacement(root) {
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
  } = req.body;
  const root = projectDir(sessionId, projectId);
  await writeStatus(root, { status: 'processing', preview_url: null, video_url: null, download_url: null, error: null });
  axios.post(`${LOGIC_URL}/run-components`, {
    session_id: sessionId,
    project_id: projectId,
    project_name: projectName,
    storage_dir: root,
    selected_components: selectedComponents,
    component_assets: componentAssets,
    environments,
  }).catch((error) => writeStatus(root, { status: 'failed', preview_url: null, video_url: null, download_url: null, error: error.message }));
  res.send({ ok: true, status: 'processing' });
});

const status = catchAsync(async (req, res) => {
  const { session_id: sessionId, project_id: projectId } = req.query;
  const root = projectDir(sessionId, projectId);
  const current = await readStatus(root);
  const componentPins = await componentPinsFromPlacement(root);
  res.send({
    ...current,
    preview_url: publicStorageUrl(sessionId, projectId, current.preview_url),
    video_url: publicStorageUrl(sessionId, projectId, current.video_url),
    component_pins: componentPins,
    download_url: current.status === 'ready_for_download'
      ? `/api/v1/guest/download?session_id=${encodeURIComponent(sessionId)}&project_id=${encodeURIComponent(projectId)}`
      : null,
  });
});

const generateVideo = catchAsync(async (req, res) => {
  const { session_id: sessionId, project_id: projectId, project_name: projectName, video_options: videoOptions } = req.body;
  const root = projectDir(sessionId, projectId);
  await writeStatus(root, { status: 'generating_video', preview_url: 'preview/final_output.png', video_url: null, download_url: null, error: null });
  console.log(`[guest/video] calling ${LOGIC_URL}/generate-video for ${projectId}`);
  axios.post(`${LOGIC_URL}/generate-video`, {
    session_id: sessionId,
    project_id: projectId,
    project_name: projectName,
    storage_dir: root,
    video_options: videoOptions,
  }, { timeout: 0 }).catch((error) => {
    console.error(`[guest/video] failed for ${projectId}: ${error.message}`);
    return writeStatus(root, { status: 'failed', preview_url: 'preview/final_output.png', video_url: null, download_url: null, error: error.message });
  });
  res.send({ ok: true, status: 'generating_video' });
});

const finalize = catchAsync(async (req, res) => {
  const { session_id: sessionId, project_id: projectId, project_name: projectName, video_options: videoOptions = {} } = req.body;
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
  if (!fs.existsSync(video) || currentVideoMeta.quality !== requestedQuality) {
    const generation = await axios.post(`${LOGIC_URL}/generate-video`, {
      session_id: sessionId,
      project_id: projectId,
      project_name: projectName,
      storage_dir: root,
      video_options: {
        ...videoOptions,
        quality: requestedQuality,
      },
    }, { timeout: 0 });
    if (!generation.data?.ok || !fs.existsSync(video)) {
      return res.status(400).send({ ok: false, message: generation.data?.error || 'Video file is not ready' });
    }
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

module.exports = { createSession, uploadImage, precheck, runComponents, status, generateVideo, finalize, download };
