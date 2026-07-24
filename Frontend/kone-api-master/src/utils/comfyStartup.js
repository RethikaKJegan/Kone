const axios = require('axios');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const logger = require('../config/logger');

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let comfyChild = null;

const fileExists = async (file) => {
  try {
    await fs.promises.access(file);
    return true;
  } catch (_) {
    return false;
  }
};

const isComfyAlive = async (comfyUrl) => {
  try {
    await axios.get(`${comfyUrl.replace(/\/$/, '')}/system_stats`, { timeout: 2500 });
    return true;
  } catch (_) {
    return false;
  }
};

const startComfyOnApiStartup = async () => {
  if (String(process.env.COMFY_AUTOSTART || 'true').toLowerCase() === 'false') {
    logger.info('ComfyUI autostart disabled');
    return;
  }

  const comfyRoot = process.env.COMFY_ROOT || '/root/Kone/vdotest';
  const comfyUrl = process.env.COMFY_URL || 'http://127.0.0.1:8188';
  const startScript = process.env.COMFY_START_SCRIPT || path.join(comfyRoot, 'scripts', 'start_comfy_logged.sh');

  if (await isComfyAlive(comfyUrl)) {
    logger.info(`ComfyUI already running at ${comfyUrl}`);
    return;
  }

  if (comfyChild && !comfyChild.killed) {
    logger.info('ComfyUI startup already in progress');
    return;
  }

  if (!(await fileExists(startScript))) {
    logger.error(`ComfyUI start script not found at ${startScript}`);
    return;
  }

  logger.info(`Starting ComfyUI using ${startScript}`);
  comfyChild = spawn('bash', [startScript], {
    cwd: comfyRoot,
    detached: false,
    stdio: 'inherit',
  });

  comfyChild.on('exit', (code, signal) => {
    logger.error(`ComfyUI process exited before/after startup: code=${code} signal=${signal}`);
    comfyChild = null;
  });

  for (let attempt = 0; attempt < 150; attempt += 1) {
    await sleep(2000);
    if (await isComfyAlive(comfyUrl)) {
      logger.info(`ComfyUI is ready at ${comfyUrl}`);
      return;
    }
  }

  logger.error(`ComfyUI did not become ready at ${comfyUrl} within 5 minutes`);
};

module.exports = {
  startComfyOnApiStartup,
};
