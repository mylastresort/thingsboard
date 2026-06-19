const dotenv = require('dotenv');

dotenv.config();

function toInt(value, fallback) {
  const parsed = Number(value);
  return Number.isInteger(parsed) ? parsed : fallback;
}

function parseTokenMap(raw) {
  if (!raw || !raw.trim()) {
    return {};
  }

  return raw
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean)
    .reduce((acc, entry) => {
      const [deviceName, token] = entry.split(':').map((item) => item.trim());
      if (deviceName && token) {
        acc[deviceName] = token;
      }
      return acc;
    }, {});
}

const config = {
  port: toInt(process.env.PORT, 8095),
  logLevel: process.env.LOG_LEVEL || 'info',
  thingsboard: {
    mqttUrl: process.env.TB_MQTT_URL || 'mqtt://localhost:1883',
    mqttClientId: process.env.TB_MQTT_CLIENT_ID || 'tb-flexsim-bridge',
    publishQos: toInt(process.env.TB_MQTT_PUBLISH_QOS, 1),
    defaultDeviceToken: process.env.TB_DEFAULT_DEVICE_TOKEN || '',
    deviceTokenMap: parseTokenMap(process.env.TB_DEVICE_TOKEN_MAP || '')
  },
  flexsim: {
    ingestUrl: process.env.FLEXSIM_INGEST_URL || 'http://localhost:8088/api/thingsboard/ingest',
    timeoutMs: toInt(process.env.FLEXSIM_API_TIMEOUT_MS, 5000),
    apiToken: process.env.FLEXSIM_API_TOKEN || ''
  }
};

module.exports = config;
