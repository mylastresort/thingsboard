const express = require('express');
const config = require('./config');
const logger = require('./logger');
const createRouter = require('./routes');
const ThingsBoardPublisher = require('./thingsboardPublisher');
const FlexSimClient = require('./flexsimClient');

const tbPublisher = new ThingsBoardPublisher(config.thingsboard, logger);
const flexsimClient = new FlexSimClient(config.flexsim, logger);

const app = express();
app.use(express.json({ limit: '1mb' }));
app.use(createRouter({ logger, tbPublisher, flexsimClient }));

const server = app.listen(config.port, () => {
  logger.info({ port: config.port }, 'TB-FlexSim bridge started');
});

tbPublisher.connect();

async function shutdown(signal) {
  logger.info({ signal }, 'Shutting down TB-FlexSim bridge');

  server.close(async (err) => {
    if (err) {
      logger.error({ err }, 'Error while stopping HTTP server');
      process.exit(1);
      return;
    }

    try {
      await tbPublisher.close();
    } catch (closeError) {
      logger.error({ closeError }, 'Error while closing ThingsBoard MQTT client');
    }

    process.exit(0);
  });
}

['SIGINT', 'SIGTERM'].forEach((signal) => {
  process.on(signal, () => {
    shutdown(signal);
  });
});
