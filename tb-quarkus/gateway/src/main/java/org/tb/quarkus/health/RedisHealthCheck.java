package org.tb.quarkus.health;

import io.quarkus.redis.client.RedisClient;
import jakarta.inject.Inject;
import org.eclipse.microprofile.health.HealthCheck;
import org.eclipse.microprofile.health.HealthCheckResponse;
import org.eclipse.microprofile.health.Liveness;
import org.jboss.logging.Logger;

@Liveness
public class RedisHealthCheck implements HealthCheck {

    private static final Logger LOG = Logger.getLogger(RedisHealthCheck.class);

    @Inject
    RedisClient redisClient;

    @Override
    public HealthCheckResponse call() {
        try {
            var response = redisClient.ping(List.of());
            var payload = response.toString();
            return HealthCheckResponse.up("redis")
                    .withData("response", payload)
                    .build();
        } catch (Exception e) {
            LOG.warn("Redis health check failed: " + e.getMessage());
            return HealthCheckResponse.down("redis")
                    .withData("error", e.getMessage())
                    .build();
        }
    }
}
