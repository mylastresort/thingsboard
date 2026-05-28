const mqtt = require('mqtt');

class ThingsBoardPublisher {
  constructor(config, logger) {
    this.logger = logger;
    this.config = config;
    this.clientsByToken = new Map();
  }

  connect() {
    this.logger.info('ThingsBoard publisher initialized');
  }

  resolveToken(deviceName, explicitToken) {
    if (explicitToken) {
      return explicitToken;
    }
    if (deviceName && this.config.deviceTokenMap[deviceName]) {
      return this.config.deviceTokenMap[deviceName];
    }
    return this.config.defaultDeviceToken;
  }

  async publishTelemetry({ deviceName, deviceToken, telemetry }) {
    const token = this.resolveToken(deviceName, deviceToken);
    if (!token) {
      throw new Error('No ThingsBoard device token provided or configured');
    }

    const client = this.getOrCreateClient(token);
    await this.waitForConnected(client, 3000);

    const topic = 'v1/devices/me/telemetry';
    const payload = JSON.stringify(telemetry || {});

    await new Promise((resolve, reject) => {
      client.publish(topic, payload, { qos: this.config.publishQos }, (err) => {
        if (err) {
          reject(err);
          return;
        }
        resolve();
      });
    });
  }

  waitForConnected(client, timeoutMs) {
    if (client.connected) {
      return Promise.resolve();
    }

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        cleanup();
        reject(new Error('Timed out waiting for ThingsBoard MQTT connection'));
      }, timeoutMs);

      const onConnect = () => {
        cleanup();
        resolve();
      };

      const onError = (err) => {
        cleanup();
        reject(err);
      };

      const cleanup = () => {
        clearTimeout(timeout);
        client.off('connect', onConnect);
        client.off('error', onError);
      };

      client.on('connect', onConnect);
      client.on('error', onError);
    });
  }

  getOrCreateClient(token) {
    if (this.clientsByToken.has(token)) {
      return this.clientsByToken.get(token);
    }

    const client = mqtt.connect(this.config.mqttUrl, {
      clientId: `${this.config.mqttClientId}-${token.slice(0, 8)}-${Date.now()}`,
      username: token,
      reconnectPeriod: 2000
    });

    client.on('connect', () => {
      this.logger.info({ tokenPrefix: token.slice(0, 6) }, 'Connected ThingsBoard MQTT client for token');
    });

    client.on('reconnect', () => {
      this.logger.warn({ tokenPrefix: token.slice(0, 6) }, 'Reconnecting token MQTT client...');
    });

    client.on('error', (err) => {
      this.logger.error({ err, tokenPrefix: token.slice(0, 6) }, 'ThingsBoard token MQTT error');
    });

    this.clientsByToken.set(token, client);
    return client;
  }

  async close() {
    const closePromises = [];
    for (const client of this.clientsByToken.values()) {
      closePromises.push(
        new Promise((resolve) => {
          client.end(false, {}, resolve);
        })
      );
    }

    await Promise.all(closePromises);
    this.clientsByToken.clear();
  }
}

module.exports = ThingsBoardPublisher;
