const axios = require('axios');

class FlexSimClient {
  constructor(config, logger) {
    this.logger = logger;
    this.http = axios.create({
      baseURL: config.ingestUrl,
      timeout: config.timeoutMs
    });
    this.apiToken = config.apiToken;
  }

  async sendTelemetry(payload) {
    const headers = {};
    if (this.apiToken) {
      headers.Authorization = `Bearer ${this.apiToken}`;
    }

    await this.http.post('', payload, { headers });
  }
}

module.exports = FlexSimClient;
