const axios = require('axios');
const httpStatus = require('http-status');
const config = require('../config/config');
const ApiError = require('../utils/ApiError');

const createBrochureRedirect = async (payload, requestId) => {
  if (!config.brochureIntegration.apiKey) {
    throw new ApiError(httpStatus.INTERNAL_SERVER_ERROR, 'Brochure integration is not configured');
  }

  try {
    const { data } = await axios.post(config.brochureIntegration.url, payload, {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${config.brochureIntegration.apiKey}`,
        ...(requestId ? { 'X-Request-Id': requestId } : {}),
      },
      timeout: 30000,
    });

    if (!data || !data.redirectUrl) {
      throw new ApiError(httpStatus.BAD_GATEWAY, 'Brochure service did not return a redirect URL');
    }

    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;

    const statusCode = error.response?.status || httpStatus.BAD_GATEWAY;
    const upstreamMessage = error.response?.data?.error || error.message || 'Brochure service request failed';
    const correlationId = error.response?.data?.correlationId;
    const message = correlationId ? `${upstreamMessage} (correlationId: ${correlationId})` : upstreamMessage;

    throw new ApiError(statusCode >= 500 ? httpStatus.BAD_GATEWAY : statusCode, message);
  }
};

module.exports = {
  createBrochureRedirect,
};
