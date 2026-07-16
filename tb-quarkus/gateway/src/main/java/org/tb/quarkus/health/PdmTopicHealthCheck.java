package org.tb.quarkus.health;

import jakarta.inject.Inject;
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.eclipse.microprofile.health.HealthCheck;
import org.eclipse.microprofile.health.HealthCheckResponse;
import org.eclipse.microprofile.health.Readiness;
import org.jboss.logging.Logger;

import java.util.List;
import java.util.Map;
import java.util.Set;

@Readiness
public class PdmTopicHealthCheck implements HealthCheck {

    private static final Logger LOG = Logger.getLogger(PdmTopicHealthCheck.class);

    @ConfigProperty(name = "kafka.bootstrap.servers", defaultValue = "kafka:9092")
    String bootstrapServers;

    @Override
    public HealthCheckResponse call() {
        try (var admin = AdminClient.create(Map.of(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers))) {
            var topics = admin.listTopics().names().get();
            var required = Set.of("pdm-commands", "pdm-events", "pdm-job-state");
            var missing = required.stream().filter(t -> !topics.contains(t)).toList();
            if (missing.isEmpty()) {
                return HealthCheckResponse.up("pdm-topics")
                        .withData("topics", String.join(",", required))
                        .build();
            }
            return HealthCheckResponse.down("pdm-topics")
                    .withData("missing", String.join(",", missing))
                    .build();
        } catch (Exception e) {
            LOG.warn("PdM topic health check failed: " + e.getMessage());
            return HealthCheckResponse.down("pdm-topics")
                    .withData("error", e.getMessage())
                    .build();
        }
    }
}
