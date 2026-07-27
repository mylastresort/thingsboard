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
import org.tb.quarkus.scenario.model.Scenario;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@ApplicationScoped
public class ScenarioDiscoveryService {

    private static final String DEFAULT_TB_URL = "http://thingsboard:8080";
    private static final int PAGE_SIZE = 100;

    @Inject
    ObjectMapper mapper;

    @ConfigProperty(name = "agents.tb.url", defaultValue = DEFAULT_TB_URL)
    String tbUrl;

    @ConfigProperty(name = "agents.tb.username", defaultValue = "tenant@thingsboard.org")
    String tbUser;

    @ConfigProperty(name = "agents.tb.password", defaultValue = "tenant")
    String tbPass;

    public Scenario discover() throws IOException, InterruptedException {
        TbClient client = new TbClient(tbUrl, tbUser, tbPass, mapper);
        client.login();

        List<Device> devices = new ArrayList<>();
        int page = 0;

        while (true) {
            JsonNode pageNode = client.listDevices(page, PAGE_SIZE);
            JsonNode dataArray = pageNode.path("data");
            if (!dataArray.isArray() || dataArray.isEmpty()) {
                break;
            }

            for (JsonNode deviceNode : dataArray) {
                Device device = new Device();
                device.setName(deviceNode.path("name").asText());
                device.setType(deviceNode.path("type").asText());
                device.setLabel(deviceNode.path("label").asText());
                device.setDeviceProfileName(deviceNode.path("deviceProfileName").asText());

                String deviceId = deviceNode.path("id").path("id").asText();

                // Fetch relations
                try {
                    JsonNode relations = client.getRelations(deviceId, "DEVICE");
                    if (relations.isArray()) {
                        for (JsonNode rel : relations) {
                            JsonNode to = rel.path("to");
                            String toType = to.path("entityType").asText();
                            String toId = to.path("id").asText();
                            String relType = rel.path("type").asText();

                            String entityName = resolveEntityName(client, toId, toType);
                            device.addRelation(new Device.Relation(toType, toId, entityName, relType));
                        }
                    }
                } catch (Exception e) {
                    Log.warnf(e, "Failed to fetch relations for device '%s'", device.getName());
                }

                devices.add(device);
            }

            boolean hasNext = pageNode.path("hasNext").asBoolean(false);
            if (!hasNext) {
                break;
            }
            page++;
        }

        Log.infof("Discovered %d devices from ThingsBoard", devices.size());

        List<Asset> assets = discoverAssets(client);

        Scenario scenario = new Scenario();
        scenario.setName("discovered");
        scenario.setDescription("Auto-discovered from ThingsBoard (" + devices.size() + " devices, " + assets.size() + " assets)");
        scenario.setVersion(1);
        scenario.getDevices().addAll(devices);
        scenario.getAssets().addAll(assets);

        Log.infof("Discovered %d devices, %d assets from ThingsBoard", devices.size(), assets.size());
        return scenario;
    }

    private List<Asset> discoverAssets(TbClient client) throws IOException, InterruptedException {
        List<Asset> assets = new ArrayList<>();
        int page = 0;

        while (true) {
            JsonNode pageNode = client.listAssets(page, PAGE_SIZE);
            JsonNode dataArray = pageNode.path("data");
            if (!dataArray.isArray() || dataArray.isEmpty()) {
                break;
            }

            for (JsonNode assetNode : dataArray) {
                Asset asset = new Asset();
                asset.setName(assetNode.path("name").asText());
                asset.setType(assetNode.path("type").asText());
                asset.setLabel(assetNode.path("label").asText());

                String assetId = assetNode.path("id").path("id").asText();

                // Fetch relations for this asset
                try {
                    JsonNode relations = client.getRelations(assetId, "ASSET");
                    if (relations.isArray()) {
                        for (JsonNode rel : relations) {
                            JsonNode to = rel.path("to");
                            String toType = to.path("entityType").asText();
                            String toId = to.path("id").asText();
                            String relType = rel.path("type").asText();

                            String entityName = resolveEntityName(client, toId, toType);
                            asset.addRelation(new Device.Relation(toType, toId, entityName, relType));
                        }
                    }
                } catch (Exception e) {
                    Log.warnf(e, "Failed to fetch relations for asset '%s'", asset.getName());
                }

                assets.add(asset);
            }

            boolean hasNext = pageNode.path("hasNext").asBoolean(false);
            if (!hasNext) {
                break;
            }
            page++;
        }

        Log.infof("Discovered %d assets from ThingsBoard", assets.size());
        return assets;
    }

    private String resolveEntityName(TbClient client, String entityId, String entityType) {
        try {
            return client.getEntityName(entityId, entityType);
        } catch (Exception e) {
            return entityType + ":" + entityId.substring(0, Math.min(8, entityId.length()));
        }
    }

    static class TbClient {
        private final String baseUrl;
        private final String username;
        private final String password;
        private final ObjectMapper mapper;
        private final HttpClient http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(15))
                .build();
        private String token;

        TbClient(String baseUrl, String username, String password, ObjectMapper mapper) {
            this.baseUrl = baseUrl;
            this.username = username;
            this.password = password;
            this.mapper = mapper;
        }

        void login() throws IOException, InterruptedException {
            ObjectNode body = mapper.createObjectNode();
            body.put("username", username);
            body.put("password", password);
            HttpResponse<String> resp = post("/api/auth/login", body, false);
            if (resp.statusCode() != 200) {
                throw new IOException("TB login failed (HTTP " + resp.statusCode() + "): " + resp.body());
            }
            token = mapper.readTree(resp.body()).path("token").asText();
        }

        JsonNode listDevices(int page, int pageSize) throws IOException, InterruptedException {
            HttpResponse<String> resp = get("/api/tenant/deviceInfos?page=" + page + "&pageSize=" + pageSize);
            if (resp.statusCode() != 200) {
                throw ioError("list devices", resp);
            }
            return mapper.readTree(resp.body());
        }

        JsonNode listAssets(int page, int pageSize) throws IOException, InterruptedException {
            HttpResponse<String> resp = get("/api/tenant/assetInfos?page=" + page + "&pageSize=" + pageSize);
            if (resp.statusCode() != 200) {
                throw ioError("list assets", resp);
            }
            return mapper.readTree(resp.body());
        }

        JsonNode getRelations(String entityId, String entityType) throws IOException, InterruptedException {
            HttpResponse<String> resp = get("/api/relations?fromId=" + entityId + "&fromType=" + entityType);
            if (resp.statusCode() != 200) {
                throw ioError("get relations for " + entityId, resp);
            }
            return mapper.readTree(resp.body());
        }

        String getEntityName(String entityId, String entityType) throws IOException, InterruptedException {
            String path = "ASSET".equals(entityType)
                    ? "/api/asset/" + entityId
                    : "/api/device/" + entityId;
            HttpResponse<String> resp = get(path);
            if (resp.statusCode() != 200) {
                return "";
            }
            return mapper.readTree(resp.body()).path("name").asText("");
        }

        String findDeviceByName(String name) throws IOException, InterruptedException {
            HttpResponse<String> resp = get("/api/tenant/devices?deviceName=" + encode(name));
            if (resp.statusCode() == 404) {
                return null;
            }
            if (resp.statusCode() != 200) {
                throw ioError("find device " + name, resp);
            }
            JsonNode node = mapper.readTree(resp.body());
            return node.isMissingNode() || node.isNull() ? null : node.path("id").path("id").asText();
        }

        String getDeviceCredentials(String deviceId) throws IOException, InterruptedException {
            HttpResponse<String> resp = get("/api/device/" + deviceId + "/credentials");
            if (resp.statusCode() != 200) {
                throw ioError("get credentials for " + deviceId, resp);
            }
            return mapper.readTree(resp.body()).path("credentialsId").asText();
        }

        void saveAttributes(String deviceId, Map<String, Object> attributes) throws IOException, InterruptedException {
            HttpResponse<String> resp = post(
                    "/api/plugins/telemetry/DEVICE/" + deviceId + "/attributes/SERVER_SCOPE",
                    mapper.valueToTree(attributes), true);
            if (resp.statusCode() != 200) {
                throw ioError("save attributes for " + deviceId, resp);
            }
        }

        private HttpResponse<String> get(String path) throws IOException, InterruptedException {
            HttpRequest.Builder req = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + path))
                    .timeout(Duration.ofSeconds(30))
                    .GET();
            authHeader(req);
            return http.send(req.build(), HttpResponse.BodyHandlers.ofString());
        }

        private HttpResponse<String> post(String path, JsonNode body, boolean withAuth) throws IOException, InterruptedException {
            HttpRequest.Builder req = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + path))
                    .timeout(Duration.ofSeconds(30))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(body)));
            if (withAuth) {
                authHeader(req);
            }
            return http.send(req.build(), HttpResponse.BodyHandlers.ofString());
        }

        private void authHeader(HttpRequest.Builder req) {
            if (token != null) {
                req.header("X-Authorization", "Bearer " + token);
            }
        }

        private IOException ioError(String action, HttpResponse<String> resp) {
            return new IOException("Failed to " + action + " (HTTP " + resp.statusCode() + "): " + resp.body());
        }

        private String encode(String value) {
            return URLEncoder.encode(value, StandardCharsets.UTF_8);
        }
    }
}
