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

async function uploadFileToAzure(localFilePath, blobPath, contentType) {
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

module.exports = {
  uploadFileToAzure,
};