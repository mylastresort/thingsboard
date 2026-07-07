package org.tb.quarkus.tb;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.quarkus.logging.Log;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import org.eclipse.microprofile.config.inject.ConfigProperty;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;

/**
 * Thin wrapper around ThingsBoard CE's public REST API. Kept dependency-free
 * (plain java.net.http + Jackson, both already pulled in by Quarkus) so the
 * loader doesn't need the unpublished thingsboard-java-client to build.
 *
 * Covers exactly what the loader needs: login, find-or-create Asset/Device,
 * CONTAINS relation, and SERVER_SCOPE attribute save (used both for sensor
 * metadata and for the scenario JSON blobs).
 */
@ApplicationScoped
public class TbGateway {

    @ConfigProperty(name = "agents.tb.url")
    String baseUrl;

    @ConfigProperty(name = "agents.tb.username")
    String username;

    @ConfigProperty(name = "agents.tb.password")
    String password;

    @Inject
    ObjectMapper mapper;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(15))
            .build();

    private volatile String jwt;

    public synchronized void login() throws IOException, InterruptedException {
        ObjectNode body = mapper.createObjectNode();
        body.put("username", username);
        body.put("password", password);

        HttpResponse<String> resp = post("/api/auth/login", body, false);
        if (resp.statusCode() != 200) {
            throw new IOException("TB login failed (HTTP " + resp.statusCode() + "): " + resp.body());
        }
        this.jwt = mapper.readTree(resp.body()).path("token").asText();
        Log.info("Authenticated against ThingsBoard as " + username);
    }

    public AuthCheck testConnection() throws IOException, InterruptedException {
        login();
        if (jwt == null || jwt.isBlank()) {
            throw new IOException("TB login response did not include a token");
        }

        HttpResponse<String> resp = get("/api/auth/user");
        if (resp.statusCode() != 200) {
            throw ioError("read authenticated user", resp);
        }

        JsonNode user = mapper.readTree(resp.body());
        return new AuthCheck(baseUrl, username, user.path("authority").asText(""));
    }

    /** Looks up an Asset by exact name (tenant scope); returns null if not found. */
    public JsonNode findAssetByName(String type, String name) throws IOException, InterruptedException {
        HttpResponse<String> resp = get("/api/tenant/assets?assetName=" + urlEncode(name));
        if (resp.statusCode() == 404) return null;
        if (resp.statusCode() != 200) throw ioError("find asset " + name, resp);
        JsonNode node = mapper.readTree(resp.body());
        return node.isMissingNode() || node.isNull() ? null : node;
    }

    /** Wraps a saved entity together with whether this call is what actually created it. */
    public record EntityResult(JsonNode json, boolean created) {
        public String id() {
            return json.path("id").path("id").asText();
        }
    }

    public EntityResult createOrUpdateAsset(String name, String type, String label) throws IOException, InterruptedException {
        JsonNode existing = findAssetByName(type, name);
        if (existing != null) {
            return new EntityResult(existing, false);
        }
        ObjectNode body = mapper.createObjectNode();
        body.put("name", name);
        body.put("type", type);
        body.put("label", label);

        HttpResponse<String> resp = post("/api/asset", body, true);
        if (resp.statusCode() != 200) throw ioError("create asset " + name, resp);
        Log.infof("Created Asset '%s' (type=%s)", name, type);
        return new EntityResult(mapper.readTree(resp.body()), true);
    }

    public void deleteAsset(String id) throws IOException, InterruptedException {
        HttpResponse<String> resp = delete("/api/asset/" + id);
        if (resp.statusCode() != 200) throw ioError("delete asset " + id, resp);
        Log.infof("Deleted Asset %s (rollback)", id);
    }

    public JsonNode findDeviceByName(String name) throws IOException, InterruptedException {
        HttpResponse<String> resp = get("/api/tenant/devices?deviceName=" + urlEncode(name));
        if (resp.statusCode() == 404) return null;
        if (resp.statusCode() != 200) throw ioError("find device " + name, resp);
        JsonNode node = mapper.readTree(resp.body());
        return node.isMissingNode() || node.isNull() ? null : node;
    }

    public EntityResult createOrUpdateDevice(String name, String type, String label) throws IOException, InterruptedException {
        JsonNode existing = findDeviceByName(name);
        if (existing != null) {
            return new EntityResult(existing, false);
        }
        ObjectNode body = mapper.createObjectNode();
        body.put("name", name);
        body.put("type", type);
        body.put("label", label);

        HttpResponse<String> resp = post("/api/device", body, true);
        if (resp.statusCode() != 200) throw ioError("create device " + name, resp);
        Log.infof("Created Device '%s' (type=%s)", name, type);
        return new EntityResult(mapper.readTree(resp.body()), true);
    }

    public void deleteDevice(String id) throws IOException, InterruptedException {
        HttpResponse<String> resp = delete("/api/device/" + id);
        if (resp.statusCode() != 200) throw ioError("delete device " + id, resp);
        Log.infof("Deleted Device %s (rollback)", id);
    }

    /** Idempotent-ish: ThingsBoard dedupes identical (from,to,type,typeGroup) relations on save. */
    public void saveContainsRelation(JsonNode fromId, JsonNode toId) throws IOException, InterruptedException {
        ObjectNode body = mapper.createObjectNode();
        body.set("from", fromId);
        body.set("to", toId);
        body.put("type", "Contains");
        body.put("typeGroup", "COMMON");

        HttpResponse<String> resp = post("/api/relation", body, true);
        if (resp.statusCode() != 200) throw ioError("save Contains relation", resp);
    }

    public void deleteContainsRelation(JsonNode fromId, JsonNode toId) throws IOException, InterruptedException {
        String path = "/api/relation"
                + "?fromId=" + urlEncode(fromId.path("id").asText())
                + "&fromType=" + urlEncode(fromId.path("entityType").asText())
                + "&relationType=Contains"
                + "&relationTypeGroup=COMMON"
                + "&toId=" + urlEncode(toId.path("id").asText())
                + "&toType=" + urlEncode(toId.path("entityType").asText());
        HttpResponse<String> resp = delete(path);
        if (resp.statusCode() != 200) throw ioError("delete Contains relation", resp);
        Log.info("Deleted Contains relation (rollback)");
    }

    public void saveServerAttributes(String entityType, String entityId, Map<String, Object> attributes)
            throws IOException, InterruptedException {
        ObjectNode body = mapper.valueToTree(attributes);
        String path = "/api/plugins/telemetry/" + entityType + "/" + entityId + "/attributes/SERVER_SCOPE";
        HttpResponse<String> resp = post(path, body, true);
        if (resp.statusCode() != 200) throw ioError("save attributes on " + entityType + "/" + entityId, resp);
    }

    /** Returns only the keys that currently exist (missing keys are simply absent from the result). */
    public Map<String, JsonNode> getServerAttributes(String entityType, String entityId, java.util.Collection<String> keys)
            throws IOException, InterruptedException {
        if (keys.isEmpty()) return Map.of();
        String keysCsv = String.join(",", keys);
        String path = "/api/plugins/telemetry/" + entityType + "/" + entityId
                + "/values/attributes/SERVER_SCOPE?keys=" + urlEncode(keysCsv);
        HttpResponse<String> resp = get(path);
        if (resp.statusCode() == 404) return Map.of();
        if (resp.statusCode() != 200) throw ioError("read attributes on " + entityType + "/" + entityId, resp);

        Map<String, JsonNode> out = new java.util.HashMap<>();
        for (JsonNode entry : mapper.readTree(resp.body())) {
            out.put(entry.path("key").asText(), entry.path("value"));
        }
        return out;
    }

    public void deleteServerAttributes(String entityType, String entityId, java.util.Collection<String> keys)
            throws IOException, InterruptedException {
        if (keys.isEmpty()) return;
        String keysCsv = String.join(",", keys);
        String path = "/api/plugins/telemetry/" + entityType + "/" + entityId
                + "/SERVER_SCOPE?keys=" + urlEncode(keysCsv);
        HttpResponse<String> resp = delete(path);
        if (resp.statusCode() != 200) throw ioError("delete attributes on " + entityType + "/" + entityId, resp);
        Log.infof("Deleted attribute keys %s on %s/%s (rollback)", keysCsv, entityType, entityId);
    }

    // --- low-level HTTP helpers ---

    private HttpResponse<String> get(String path) throws IOException, InterruptedException {
        HttpRequest.Builder req = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + path))
                .timeout(Duration.ofSeconds(20))
                .GET();
        authHeader(req);
        return http.send(req.build(), HttpResponse.BodyHandlers.ofString());
    }

    private HttpResponse<String> delete(String path) throws IOException, InterruptedException {
        HttpRequest.Builder req = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + path))
                .timeout(Duration.ofSeconds(20))
                .DELETE();
        authHeader(req);
        return http.send(req.build(), HttpResponse.BodyHandlers.ofString());
    }

    private HttpResponse<String> post(String path, JsonNode body, boolean withAuth) throws IOException, InterruptedException {
        HttpRequest.Builder req = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + path))
                .timeout(Duration.ofSeconds(20))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(body)));
        if (withAuth) authHeader(req);
        return http.send(req.build(), HttpResponse.BodyHandlers.ofString());
    }

    private void authHeader(HttpRequest.Builder req) {
        if (jwt != null) {
            req.header("X-Authorization", "Bearer " + jwt);
        }
    }

    private IOException ioError(String action, HttpResponse<String> resp) {
        return new IOException("Failed to " + action + " (HTTP " + resp.statusCode() + "): " + resp.body());
    }

    private static String urlEncode(String s) {
        return java.net.URLEncoder.encode(s, java.nio.charset.StandardCharsets.UTF_8);
    }

    public record AuthCheck(String baseUrl, String username, String authority) {
    }
}
