package org.tb.quarkus.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.quarkus.logging.Log;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.tb.quarkus.model.FailureModeRecord;
import org.tb.quarkus.model.PdmSeedMachineDefaults;
import org.tb.quarkus.model.PdmSeedMachineOption;
import org.tb.quarkus.model.PdmSeedMachineOptions;
import org.tb.quarkus.model.PdmSeedMachineRequest;
import org.tb.quarkus.model.PdmSeedMachineResult;
import org.tb.quarkus.model.PdmSeedMachineSelection;

import java.io.BufferedReader;
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

@ApplicationScoped
public class PdmSeedService {

    private static final String DEFAULT_TB_URL = "http://thingsboard:8080";
    private static final String DEFAULT_DATA_PATH = "/data";
    private static final int DEFAULT_MAX_MACHINES = 100;
    private static final int DEFAULT_WORKERS = 8;
    private static final int DEFAULT_BATCH_SIZE = 1000;
    private static final String MODE_MAX_MACHINES = "maxMachines";
    private static final String MODE_SELECTED_MACHINES = "selectedMachines";
    private static final String DEFAULT_MACHINE_PREFIX = "PdM-Machine";
    private static final long DAY_MILLIS = Duration.ofDays(1).toMillis();
    private static final DateTimeFormatter CSV_DATE_FORMAT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    @Inject
    ObjectMapper mapper;

    @Inject
    FailureModeRecordService failureModeRecordService;

    @ConfigProperty(name = "agents.tb.url", defaultValue = DEFAULT_TB_URL)
    String configuredTbUrl;

    @ConfigProperty(name = "agents.tb.username", defaultValue = "tenant@thingsboard.org")
    String configuredTbUser;

    @ConfigProperty(name = "agents.tb.password", defaultValue = "tenant")
    String configuredTbPass;

    @ConfigProperty(name = "pdm.seed.data", defaultValue = DEFAULT_DATA_PATH)
    String configuredDataPath;

    public PdmSeedMachineOptions getOptions() {
        PdmSeedMachineDefaults defaults = new PdmSeedMachineDefaults()
                .machinePrefix(DEFAULT_MACHINE_PREFIX)
                .machines(List.of())
                .maxMachines(DEFAULT_MAX_MACHINES)
                .shiftToNow(true)
                .workers(DEFAULT_WORKERS);

        List<PdmSeedMachineOption> machines;
        try {
            machines = readMachineOptions(Path.of(configuredDataPath));
        } catch (Exception e) {
            Log.warnf(e, "Unable to read PdM machine options from %s", configuredDataPath);
            machines = List.of();
        }

        return new PdmSeedMachineOptions()
                .defaults(defaults)
                .machines(machines)
                .fields(List.of(
                        "mode",
                        "machinePrefix",
                        "machines",
                        "maxMachines",
                        "shiftToNow",
                        "workers"
                ));
    }

    private List<PdmSeedMachineOption> readMachineOptions(Path dataPath) throws IOException {
        List<List<String>> rows = readCsvRows(dataPath.resolve("PdM_machines.csv"));
        List<PdmSeedMachineOption> machines = new ArrayList<>();
        for (int r = 1; r < rows.size(); r++) {
            List<String> row = rows.get(r);
            int machineId = parseInt(valueAt(row, 0, ""), -1);
            if (machineId < 0) {
                continue;
            }
            String model = valueAt(row, 1, "");
            machines.add(new PdmSeedMachineOption()
                    .machineId(machineId)
                    .model(model)
                    .age(valueAt(row, 2, ""))
                    .label("Machine " + machineId + " - " + firstNonBlank(model, "unknown")));
        }
        return machines;
    }

    public PdmSeedMachineResult seed(PdmSeedMachineRequest cfg) throws Exception {
        if (cfg == null) {
            throw new IllegalArgumentException("request body is required");
        }
        String tbUrl = firstNonBlank(configuredTbUrl, DEFAULT_TB_URL);
        String tbUser = firstNonBlank(configuredTbUser, System.getenv("TB_USERNAME"));
        String tbPass = firstNonBlank(configuredTbPass, System.getenv("TB_PASSWORD"));
        String dataPath = firstNonBlank(configuredDataPath, DEFAULT_DATA_PATH);
        String mode = cfg.getMode() == null ? MODE_MAX_MACHINES : cfg.getMode().toString();
        int maxMachines = cfg.getMaxMachines() == null ? DEFAULT_MAX_MACHINES : cfg.getMaxMachines();
        int workers = cfg.getWorkers() == null ? DEFAULT_WORKERS : Math.max(1, cfg.getWorkers());
        boolean shiftToNow = Boolean.TRUE.equals(cfg.getShiftToNow());

        if (isBlank(tbUser) || isBlank(tbPass)) {
            throw new IllegalArgumentException("ThingsBoard credentials are not configured");
        }
        if (!MODE_MAX_MACHINES.equals(mode) && !MODE_SELECTED_MACHINES.equals(mode)) {
            throw new IllegalArgumentException("Unknown seed mode: " + mode);
        }

        Map<Integer, String> selectedMachineNames = selectedMachineNames(cfg.getMachines());
        if (MODE_SELECTED_MACHINES.equals(mode) && selectedMachineNames.isEmpty()) {
            throw new IllegalArgumentException("At least one named machine is required");
        }
        TbClient client = new TbClient(tbUrl, tbUser, tbPass, mapper);
        client.login();

        LoadMachinesResult machines = loadMachines(Path.of(dataPath), client, mode, selectedMachineNames, maxMachines,
                firstNonBlank(cfg.getMachinePrefix(), DEFAULT_MACHINE_PREFIX));
        Log.infof("PdM seed: %d devices ready", machines.machineToDevice().size());

        Map<String, List<TsPoint>> deviceTelemetry = new LinkedHashMap<>();
        Map<Integer, Long> machineMaxTs = new HashMap<>();
        TsTracker tracker = (machineId, deviceId, ts, values) -> {
            machineMaxTs.merge(machineId, ts, Math::max);
            deviceTelemetry.computeIfAbsent(deviceId, ignored -> new ArrayList<>()).add(new TsPoint(ts, values));
        };

        Path seedDataPath = Path.of(dataPath);
        loadTelemetry(seedDataPath, machines.machineToDevice(), tracker);
        List<EventRecord> eventRecords = new ArrayList<>();
        eventRecords.addAll(loadFailureModeRecords(seedDataPath, "PdM_errors.csv", "error", machines.machineToDevice(), machineMaxTs));
        eventRecords.addAll(loadFailureModeRecords(seedDataPath, "PdM_failures.csv", "failure", machines.machineToDevice(), machineMaxTs));
        eventRecords.addAll(loadFailureModeRecords(seedDataPath, "PdM_maint.csv", "maintenance", machines.machineToDevice(), machineMaxTs));

        int totalPoints = deviceTelemetry.values().stream().mapToInt(List::size).sum();
        int shifted = 0;
        if (shiftToNow) {
            Map<Integer, Long> machineTimeDiff = machineTimeDiffToNow(machines.machineToDevice(), machineMaxTs, System.currentTimeMillis());
            shiftMachineTelemetry(deviceTelemetry, machines.machineToDevice(), machineTimeDiff);
            shiftFailureModeRecords(eventRecords, machineTimeDiff);
            shifted = machineTimeDiff.size();
        }

        int failedDevices = pushAll(client, deviceTelemetry, workers);
        if (!eventRecords.isEmpty()) {
            failureModeRecordService.createBatch(eventRecords.stream().map(EventRecord::record).toList());
        }

        return new PdmSeedMachineResult()
                .loadedMachines(machines.loaded())
                .devicesReady(machines.machineToDevice().size())
                .telemetryPoints(totalPoints)
                .failureModeRecords(eventRecords.size())
                .shiftedMachines(shifted)
                .failedDevices(failedDevices)
                .machineToDevice(stringKeyMap(machines.machineToDevice()));
    }

    private LoadMachinesResult loadMachines(Path dataPath, TbClient client, String mode, Map<Integer, String> selectedMachineNames,
                                            int max, String machinePrefix)
            throws Exception {
        List<List<String>> rows = readCsvRows(dataPath.resolve("PdM_machines.csv"));
        Map<Integer, String> machineToDevice = new LinkedHashMap<>();
        int loaded = 0;
        for (int r = 1; r < rows.size(); r++) {
            List<String> row = rows.get(r);
            if (row.isEmpty()) {
                continue;
            }
            int machineId = parseInt(row.get(0), -1);
            if (machineId < 0 || !shouldLoad(machineId, loaded, mode, selectedMachineNames, max)) {
                continue;
            }

            String model = valueAt(row, 1, "unknown");
            String age = valueAt(row, 2, "");
            String name = MODE_SELECTED_MACHINES.equals(mode)
                    ? selectedMachineNames.get(machineId)
                    : machinePrefix.trim() + "-" + machineId;
            String deviceId;
            if (client == null) {
                deviceId = "dryrun-" + machineId;
            } else {
                JsonNode existing = client.findDeviceByName(name);
                if (existing != null) {
                    deviceId = existing.path("id").path("id").asText();
                } else {
                    deviceId = client.createDevice(name, "PdM-" + model, "Predictive Maintenance Machine " + machineId);
                    client.saveAttributes(deviceId, Map.of(
                            "model", model,
                            "age", age,
                            "machineId", machineId
                    ));
                }
            }
            machineToDevice.put(machineId, deviceId);
            loaded++;
        }
        return new LoadMachinesResult(machineToDevice, loaded);
    }

    private void loadTelemetry(Path dataPath, Map<Integer, String> machineToDevice, TsTracker tracker) throws IOException {
        List<List<String>> rows = readCsvRows(dataPath.resolve("PdM_telemetry.csv"));
        List<String> header = rows.get(0);
        int skipped = 0;
        for (int r = 1; r < rows.size(); r++) {
            List<String> row = rows.get(r);
            Long ts = parseTs(valueAt(row, 0, null));
            int machineId = parseInt(valueAt(row, 1, ""), -1);
            String deviceId = machineToDevice.get(machineId);
            if (ts == null || deviceId == null) {
                skipped++;
                continue;
            }
            Map<String, String> values = new LinkedHashMap<>();
            for (int c = 2; c < row.size() && c < header.size(); c++) {
                values.put(header.get(c), row.get(c));
            }
            tracker.track(machineId, deviceId, ts, values);
        }
        Log.infof("PdM telemetry: %d loaded, %d skipped", rows.size() - 1 - skipped, skipped);
    }

    private List<EventRecord> loadFailureModeRecords(Path dataPath, String file, String type, Map<Integer, String> machineToDevice,
                                                     Map<Integer, Long> machineMaxTs) throws IOException {
        List<List<String>> rows = readCsvRows(dataPath.resolve(file));
        List<EventRecord> records = new ArrayList<>();
        int skipped = 0;
        for (int r = 1; r < rows.size(); r++) {
            List<String> row = rows.get(r);
            Long ts = parseTs(valueAt(row, 0, null));
            int machineId = parseInt(valueAt(row, 1, ""), -1);
            String eventValue = valueAt(row, 2, "");
            String deviceId = machineToDevice.get(machineId);
            if (ts == null || deviceId == null || eventValue.isBlank()) {
                skipped++;
                continue;
            }
            machineMaxTs.merge(machineId, ts, Math::max);
            records.add(new EventRecord(machineId, new FailureModeRecord()
                    .type(type)
                    .deviceId(deviceId)
                    .datetime(new Date(ts))
                    .description(eventDescription(type, eventValue))
                    .errorCode("error".equals(type) ? eventValue : null)
                    .rootCause("failure".equals(type) ? eventValue : null)
                    .partsReplaced("maintenance".equals(type) ? eventValue : null)));
        }
        Log.infof("PdM %s: %d loaded, %d skipped", file, rows.size() - 1 - skipped, skipped);
        return records;
    }

    private Map<Integer, Long> machineTimeDiffToNow(Map<Integer, String> machineToDevice, Map<Integer, Long> machineMaxTs,
                                                    long currentTimeMs) {
        Map<Integer, Long> machineTimeDiff = new HashMap<>();
        for (Map.Entry<Integer, String> entry : machineToDevice.entrySet()) {
            Long maxTs = machineMaxTs.get(entry.getKey());
            if (maxTs == null || maxTs == 0) {
                continue;
            }
            long timeDiff = currentTimeMs - maxTs;
            timeDiff -= timeDiff % DAY_MILLIS;
            machineTimeDiff.put(entry.getKey(), timeDiff);
        }
        return machineTimeDiff;
    }

    private void shiftMachineTelemetry(Map<String, List<TsPoint>> deviceTelemetry, Map<Integer, String> machineToDevice,
                                       Map<Integer, Long> machineTimeDiff) {
        for (Map.Entry<Integer, Long> entry : machineTimeDiff.entrySet()) {
            String deviceId = machineToDevice.get(entry.getKey());
            if (deviceId == null) {
                continue;
            }
            for (TsPoint point : deviceTelemetry.getOrDefault(deviceId, List.of())) {
                point.ts += entry.getValue();
            }
        }
    }

    private void shiftFailureModeRecords(List<EventRecord> records, Map<Integer, Long> machineTimeDiff) {
        for (EventRecord eventRecord : records) {
            Long timeDiff = machineTimeDiff.get(eventRecord.machineId());
            if (timeDiff == null) {
                continue;
            }
            Date datetime = eventRecord.record().getDatetime();
            if (datetime != null) {
                eventRecord.record().setDatetime(new Date(datetime.getTime() + timeDiff));
            }
        }
    }

    private String eventDescription(String type, String value) {
        return switch (type) {
            case "error" -> "PdM error " + value;
            case "failure" -> "PdM failure " + value;
            case "maintenance" -> "PdM maintenance " + value;
            default -> value;
        };
    }

    private int pushAll(TbClient client, Map<String, List<TsPoint>> deviceTelemetry, int workers) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(workers);
        AtomicInteger failed = new AtomicInteger();
        for (Map.Entry<String, List<TsPoint>> entry : deviceTelemetry.entrySet()) {
            executor.submit(() -> {
                try {
                    List<TsPoint> points = entry.getValue();
                    for (int start = 0; start < points.size(); start += DEFAULT_BATCH_SIZE) {
                        int end = Math.min(start + DEFAULT_BATCH_SIZE, points.size());
                        client.saveTimeseries(entry.getKey(), points.subList(start, end));
                    }
                } catch (Exception e) {
                    failed.incrementAndGet();
                    Log.warnf(e, "PdM push failed for device %s", entry.getKey());
                }
            });
        }
        executor.shutdown();
        executor.awaitTermination(1, TimeUnit.HOURS);
        return failed.get();
    }

    private List<List<String>> readCsvRows(Path path) throws IOException {
        List<List<String>> rows = new ArrayList<>();
        try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                rows.add(parseCsvLine(line));
            }
        }
        if (rows.isEmpty()) {
            throw new IOException(path + ": empty");
        }
        return rows;
    }

    private List<String> parseCsvLine(String line) {
        List<String> values = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        boolean quoted = false;
        for (int i = 0; i < line.length(); i++) {
            char ch = line.charAt(i);
            if (ch == '"') {
                if (quoted && i + 1 < line.length() && line.charAt(i + 1) == '"') {
                    current.append('"');
                    i++;
                } else {
                    quoted = !quoted;
                }
            } else if (ch == ',' && !quoted) {
                values.add(current.toString());
                current.setLength(0);
            } else {
                current.append(ch);
            }
        }
        values.add(current.toString());
        return values;
    }

    private Map<Integer, String> selectedMachineNames(List<PdmSeedMachineSelection> selections) {
        Map<Integer, String> names = new LinkedHashMap<>();
        if (selections == null) {
            return names;
        }
        for (PdmSeedMachineSelection selection : selections) {
            if (selection == null || selection.getMachineId() == null || isBlank(selection.getMachineName())) {
                throw new IllegalArgumentException("Each selected machine requires a machineId and machineName");
            }
            names.put(selection.getMachineId(), selection.getMachineName().trim());
        }
        return names;
    }

    private boolean shouldLoad(int machineId, int loadedCount, String mode, Map<Integer, String> selectedMachineNames, int max) {
        return MODE_SELECTED_MACHINES.equals(mode) ? selectedMachineNames.containsKey(machineId) : loadedCount < max;
    }

    private Long parseTs(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return LocalDateTime.parse(value, CSV_DATE_FORMAT).atZone(ZoneId.systemDefault()).toInstant().toEpochMilli();
    }

    private int parseInt(String value, int fallback) {
        try {
            return Integer.parseInt(value.trim());
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private String valueAt(List<String> row, int index, String fallback) {
        return index >= 0 && index < row.size() ? row.get(index) : fallback;
    }

    private String firstNonBlank(String... values) {
        for (String value : values) {
            if (!isBlank(value)) {
                return value;
            }
        }
        return null;
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private Map<String, String> stringKeyMap(Map<Integer, String> values) {
        Map<String, String> result = new LinkedHashMap<>();
        for (Map.Entry<Integer, String> entry : values.entrySet()) {
            result.put(String.valueOf(entry.getKey()), entry.getValue());
        }
        return result;
    }

    private record LoadMachinesResult(Map<Integer, String> machineToDevice, int loaded) {
    }

    private record EventRecord(int machineId, FailureModeRecord record) {
    }

    private interface TsTracker {
        void track(int machineId, String deviceId, long ts, Map<String, String> values);
    }

    private static class TsPoint {
        public long ts;
        public Map<String, String> values;

        TsPoint(long ts, Map<String, String> values) {
            this.ts = ts;
            this.values = values;
        }
    }

    private static class TbClient {
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

        JsonNode findDeviceByName(String name) throws IOException, InterruptedException {
            HttpResponse<String> resp = get("/api/tenant/devices?deviceName=" + encode(name));
            if (resp.statusCode() == 404) {
                return null;
            }
            if (resp.statusCode() != 200) {
                throw ioError("find device " + name, resp);
            }
            JsonNode node = mapper.readTree(resp.body());
            return node.isMissingNode() || node.isNull() ? null : node;
        }

        String createDevice(String name, String type, String label) throws IOException, InterruptedException {
            ObjectNode body = mapper.createObjectNode();
            body.put("name", name);
            body.put("type", type);
            body.put("label", label);
            HttpResponse<String> resp = post("/api/device", body, true);
            if (resp.statusCode() != 200) {
                throw ioError("create device " + name, resp);
            }
            return mapper.readTree(resp.body()).path("id").path("id").asText();
        }

        void saveAttributes(String deviceId, Map<String, Object> attributes) throws IOException, InterruptedException {
            HttpResponse<String> resp = post("/api/plugins/telemetry/DEVICE/" + deviceId + "/attributes/SERVER_SCOPE",
                    mapper.valueToTree(attributes), true);
            if (resp.statusCode() != 200) {
                throw ioError("save attributes for " + deviceId, resp);
            }
        }

        void saveTimeseries(String deviceId, List<TsPoint> points) throws IOException, InterruptedException {
            ArrayNode body = mapper.valueToTree(points);
            HttpResponse<String> resp = post("/api/plugins/telemetry/DEVICE/" + deviceId + "/timeseries/ANY", body, true);
            if (resp.statusCode() != 200) {
                throw ioError("save timeseries for " + deviceId, resp);
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
