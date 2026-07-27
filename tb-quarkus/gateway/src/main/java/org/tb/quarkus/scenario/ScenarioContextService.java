package org.tb.quarkus.scenario;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.quarkus.logging.Log;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.tb.quarkus.scenario.model.Asset;
import org.tb.quarkus.scenario.model.Device;



import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

@ApplicationScoped
public class ScenarioContextService {

    private static final String DEFAULT_TB_URL = "http://thingsboard:8080";

    @Inject
    ObjectMapper mapper;

    @ConfigProperty(name = "agents.tb.url", defaultValue = DEFAULT_TB_URL)
    String tbUrl;

    @ConfigProperty(name = "agents.tb.username", defaultValue = "tenant@thingsboard.org")
    String tbUser;

    @ConfigProperty(name = "agents.tb.password", defaultValue = "tenant")
    String tbPass;

    public void ensureTenant() {
        TbClient tenantClient = new TbClient(tbUrl, tbUser, tbPass, mapper);
        if (tenantClient.token != null) {
            Log.infof("Tenant user '%s' authenticated successfully", tbUser);
        } else {
            Log.warnf("Tenant user '%s' cannot authenticate — run 'make install-demo' to seed the tenant", tbUser);
        }
    }

    public DeviceContext createDeviceContext(Device device) throws IOException, InterruptedException {
        TbClient client = new TbClient(tbUrl, tbUser, tbPass, mapper);

        String deviceId = client.findDeviceByName(device.getName());
        boolean created = false;
        if (deviceId == null) {
            Log.infof("Device '%s' not found, creating...", device.getName());
            deviceId = client.createDevice(device.getName(), device.getType());
            created = true;
            Log.infof("Device '%s' created (id=%s)", device.getName(), deviceId);
        } else {
            Log.infof("Device '%s' found (id=%s)", device.getName(), deviceId);
        }

        String mqttToken = client.getDeviceCredentials(deviceId);
        Log.infof("Device '%s' MQTT token resolved", device.getName());

        return new DeviceContext(deviceId, mqttToken, created);
    }

    public record DeviceContext(String deviceId, String mqttToken, boolean created) {
    }

    public AssetContext createAssetContext(Asset asset) throws IOException, InterruptedException {
        TbClient client = new TbClient(tbUrl, tbUser, tbPass, mapper);

        String assetId = client.findAssetByName(asset.getName());
        boolean created = false;
        if (assetId == null) {
            Log.infof("Asset '%s' not found, creating...", asset.getName());
            assetId = client.createAsset(asset.getName(), asset.getType());
            created = true;
            Log.infof("Asset '%s' created (id=%s)", asset.getName(), assetId);
        } else {
            Log.infof("Asset '%s' found (id=%s)", asset.getName(), assetId);
        }

        return new AssetContext(assetId, created);
    }

    public record AssetContext(String assetId, boolean created) {
    }

    static class TbClient {
        private final String baseUrl;
        private final ObjectMapper mapper;
        private final HttpClient http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(15))
                .build();
        private String token;

        TbClient(String baseUrl, String username, String password, ObjectMapper mapper) {
            this.baseUrl = baseUrl;
            this.mapper = mapper;
            try {
                ObjectNode body = mapper.createObjectNode();
                body.put("username", username);
                body.put("password", password);
                HttpResponse<String> resp = post("/api/auth/login", body, false);
                if (resp.statusCode() == 200) {
                    token = mapper.readTree(resp.body()).path("token").asText();
                }
            } catch (Exception e) {
                Log.errorf(e, "TB login failed");
            }
        }

        String createDevice(String name, String type) throws IOException, InterruptedException {
            ObjectNode body = mapper.createObjectNode();
            body.put("name", name);
            body.put("type", type);
            HttpResponse<String> resp = post("/api/device", body, true);
            if (resp.statusCode() != 200) {
                throw new IOException("Failed to create device (HTTP " + resp.statusCode() + "): " + resp.body());
            }
            return mapper.readTree(resp.body()).path("id").path("id").asText();
        }

        String createAsset(String name, String type) throws IOException, InterruptedException {
            ObjectNode body = mapper.createObjectNode();
            body.put("name", name);
            body.put("type", type);
            HttpResponse<String> resp = post("/api/asset", body, true);
            if (resp.statusCode() != 200) {
                throw new IOException("Failed to create asset (HTTP " + resp.statusCode() + "): " + resp.body());
            }
            return mapper.readTree(resp.body()).path("id").path("id").asText();
        }

        String findDeviceByName(String name) throws IOException, InterruptedException {
            HttpResponse<String> resp = get("/api/tenant/devices?deviceName=" + java.net.URLEncoder.encode(name, java.nio.charset.StandardCharsets.UTF_8));
            if (resp.statusCode() == 404) {
                return null;
            }
            if (resp.statusCode() != 200) {
                return null;
            }
            JsonNode node = mapper.readTree(resp.body());
            return node.isMissingNode() || node.isNull() ? null : node.path("id").path("id").asText();
        }

        String findAssetByName(String name) throws IOException, InterruptedException {
            HttpResponse<String> resp = get("/api/tenant/assets?assetName=" + java.net.URLEncoder.encode(name, java.nio.charset.StandardCharsets.UTF_8));
            if (resp.statusCode() == 404) {
                return null;
            }
            if (resp.statusCode() != 200) {
                return null;
            }
            JsonNode node = mapper.readTree(resp.body());
            return node.isMissingNode() || node.isNull() ? null : node.path("id").path("id").asText();
        }

        String getDeviceCredentials(String deviceId) throws IOException, InterruptedException {
            HttpResponse<String> resp = get("/api/device/" + deviceId + "/credentials");
            if (resp.statusCode() != 200) {
                throw new IOException("Failed to get credentials (HTTP " + resp.statusCode() + "): " + resp.body());
            }
            return mapper.readTree(resp.body()).path("credentialsId").asText();
        }

        JsonNode httpGet(String path) throws IOException, InterruptedException {
            HttpResponse<String> resp = get(path);
            if (resp.statusCode() != 200) {
                throw new IOException("HTTP GET " + path + " failed (" + resp.statusCode() + "): " + resp.body());
            }
            return mapper.readTree(resp.body());
        }

        JsonNode httpPost(String path, JsonNode body) throws IOException, InterruptedException {
            HttpResponse<String> resp = post(path, body, true);
            if (resp.statusCode() != 200) {
                throw new IOException("HTTP POST " + path + " failed (" + resp.statusCode() + "): " + resp.body());
            }
            return mapper.readTree(resp.body());
        }

        private HttpResponse<String> get(String path) throws IOException, InterruptedException {
            HttpRequest.Builder req = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + path))
                    .timeout(Duration.ofSeconds(30))
                    .GET();
            if (token != null) {
                req.header("X-Authorization", "Bearer " + token);
            }
            return http.send(req.build(), HttpResponse.BodyHandlers.ofString());
        }

        private HttpResponse<String> post(String path, JsonNode body, boolean withAuth) throws IOException, InterruptedException {
            HttpRequest.Builder req = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + path))
                    .timeout(Duration.ofSeconds(30))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(body)));
            if (withAuth && token != null) {
                req.header("X-Authorization", "Bearer " + token);
            }
            return http.send(req.build(), HttpResponse.BodyHandlers.ofString());
        }
    }
}
