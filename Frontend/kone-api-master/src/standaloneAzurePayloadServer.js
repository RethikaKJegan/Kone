require('dotenv').config();

const express = require('express');
const {
  blobExists,
  getBlobMetadata,
  getBlobUrl,
} = require('./services/azureBlob.service');
const { finalVideoBlobPath } = require('./utils/azureBlobPaths');

const app = express();
const port = process.env.AZURE_PAYLOAD_SERVER_PORT || 5050;

app.use(express.json());

app.post('/payload', async (req, res) => {
  try {
    const { userId, projectId, offeringId } = req.body;

    if (!userId || !projectId || !offeringId) {
      return res.status(400).json({
        success: false,
        message: 'userId, projectId, and offeringId are required',
      });
    }

    const videoBlobPath = finalVideoBlobPath({
      userId,
      projectId,
      offeringId,
      fileName: 'final-video.mp4',
    });

    const exists = await blobExists(videoBlobPath);

    if (!exists) {
      return res.status(404).json({
        success: false,
        message: 'Final video blob not found',
        videoBlobPath,
      });
    }

    const metadata = await getBlobMetadata(videoBlobPath);

    const beforeBlobPath = metadata.beforeblobpath || metadata.beforeBlobPath;
    const afterBlobPath = metadata.afterblobpath || metadata.afterBlobPath;
    const actualVideoBlobPath = metadata.videoblobpath || metadata.videoBlobPath || videoBlobPath;

    const payload = {
      userId: metadata.userid || metadata.userId || userId,
      projectId: metadata.projectid || metadata.projectId || projectId,
      offeringId: metadata.offeringid || metadata.offeringId || offeringId,
      personName: metadata.personname || metadata.personName || '',
      projectName: metadata.projectname || metadata.projectName || '',
      beforePhotoUrl: getBlobUrl(beforeBlobPath),
      afterPhotoUrl: getBlobUrl(afterBlobPath),
      videoUrl: getBlobUrl(actualVideoBlobPath),
    };

    console.log('[Azure Payload]', payload);

    return res.status(200).json(payload);
  } catch (error) {
    console.error('[Azure Payload Error]', error);
    return res.status(500).json({
      success: false,
      message: error.message,
    });
  }
});

app.listen(port, () => {
  console.log(`Azure payload server listening on port ${port}`);
});