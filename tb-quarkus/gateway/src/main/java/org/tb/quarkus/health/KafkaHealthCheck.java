package org.tb.quarkus.health;

import jakarta.inject.Inject;
import org.eclipse.microprofile.health.HealthCheck;
import org.eclipse.microprofile.health.HealthCheckResponse;
import org.eclipse.microprofile.health.Liveness;
import org.jboss.logging.Logger;

@Liveness
public class KafkaHealthCheck implements HealthCheck {

    private static final Logger LOG = Logger.getLogger(KafkaHealthCheck.class);

    @Inject
    io.vertx.mutiny.core.Vertx vertx;

    @Override
    public HealthCheckResponse call() {
        try {
            var kafkaClients = vertx
                    .eventBus()
                    .localServices()
                    .stream()
                    .toList();
            return HealthCheckResponse.up("kafka-vertx-ready");
        } catch (Exception e) {
            LOG.warn("Kafka health check failed: " + e.getMessage());
            return HealthCheckResponse.down("kafka-vertx-ready").withData("error", e.getMessage()).build();
        }
    }
}
