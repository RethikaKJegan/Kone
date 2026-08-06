const { BlobServiceClient } = require("@azure/storage-blob");
const path = require("path");

const connectionString = process.env.AZURE_STORAGE_CONNECTION_STRING;
const containerName = process.env.AZURE_STORAGE_CONTAINER_NAME || "kone";
const azureEnabled = process.env.AZURE_UPLOAD_ENABLED === "true";

let containerClient = null;

function getContainerClient() {
  if (!azureEnabled) return null;
  if (!connectionString) return null;

  if (!containerClient) {
    const blobServiceClient = BlobServiceClient.fromConnectionString(connectionString);
    containerClient = blobServiceClient.getContainerClient(containerName);
  }

  return containerClient;
}

function normalizeBlobName(value) {
  return String(value || "")
    .replace(/\\/g, "/")
    .replace(/^\/+/, "")
    .replace(/\/+/g, "/");
}

function cleanMetadata(metadata = {}) {
  return Object.fromEntries(
    Object.entries(metadata)
      .filter(([, value]) => value !== undefined && value !== null)
      .map(([key, value]) => [key, String(value)])
  );
}

async function uploadFileToAzure(localFilePath, blobPath, contentType, metadata = {}) {
  try {
    const client = getContainerClient();

    if (!client) {
      return {
        success: false,
        skipped: true,
        reason: "Azure upload disabled or missing config",
      };
    }

    const cleanBlobPath = normalizeBlobName(blobPath);
    const blockBlobClient = client.getBlockBlobClient(cleanBlobPath);

    await blockBlobClient.uploadFile(localFilePath, {
      blobHTTPHeaders: contentType
        ? { blobContentType: contentType }
        : undefined,
      metadata: cleanMetadata(metadata),
    });

    return {
      success: true,
      blobPath: cleanBlobPath,
      url: blockBlobClient.url,
    };
  } catch (error) {
    console.error("[Azure Upload Failed]", {
      localFilePath,
      blobPath,
      error: error.message,
    });

    return {
      success: false,
      error: error.message,
    };
  }
}

function getBlobClient(blobPath) {
  const client = getContainerClient();

  if (!client) {
    throw new Error("Azure upload disabled or missing config");
  }

  return client.getBlobClient(normalizeBlobName(blobPath));
}

async function blobExists(blobPath) {
  return getBlobClient(blobPath).exists();
}

async function getBlobMetadata(blobPath) {
  const properties = await getBlobClient(blobPath).getProperties();
  return properties.metadata || {};
}

function getBlobUrl(blobPath) {
  return getBlobClient(blobPath).url;
}

module.exports = {
  uploadFileToAzure,
  blobExists,
  getBlobMetadata,
  getBlobUrl,
};