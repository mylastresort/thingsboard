const express = require('express');

function createRouter({ logger, tbPublisher, flexsimClient }) {
  const router = express.Router();

  router.get('/health', (_req, res) => {
    res.status(200).json({ status: 'ok' });
  });

  // Endpoint to receive telemetry/events from ThingsBoard Rule Engine webhook.
  router.post('/api/v1/thingsboard/telemetry', async (req, res) => {
    const payload = req.body || {};

    try {
      await flexsimClient.sendTelemetry({
        source: 'thingsboard',
        receivedAt: new Date().toISOString(),
        payload
      });

      logger.info({ payload }, 'Forwarded ThingsBoard telemetry to FlexSim');
      res.status(202).json({ status: 'accepted' });
    } catch (err) {
      logger.error({ err, payload }, 'Failed to forward telemetry to FlexSim');
      res.status(502).json({ error: 'flexsim_ingest_failed' });
    }
  });

  // Endpoint to receive telemetry from FlexSim and publish to ThingsBoard device.
  router.post('/api/v1/flexsim/telemetry', async (req, res) => {
    const body = req.body || {};
    const deviceName = body.deviceName || '';
    const deviceToken = body.deviceToken || '';
    const telemetry = body.telemetry || body;

    if (!telemetry || typeof telemetry !== 'object' || Array.isArray(telemetry)) {
      res.status(400).json({ error: 'telemetry must be a JSON object' });
      return;
    }

    try {
      await tbPublisher.publishTelemetry({
        deviceName,
        deviceToken,
        telemetry
      });

      logger.info({ deviceName, telemetry }, 'Published FlexSim telemetry to ThingsBoard');
      res.status(202).json({ status: 'accepted' });
    } catch (err) {
      logger.error({ err, body }, 'Failed to publish telemetry to ThingsBoard');
      res.status(502).json({ error: 'thingsboard_publish_failed', message: err.message });
    }
  });

  return router;
}

module.exports = createRouter;
