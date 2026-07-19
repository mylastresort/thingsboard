package org.tb.quarkus.scenario;

import io.quarkus.logging.Log;
import jakarta.enterprise.context.ApplicationScoped;
import org.eclipse.paho.client.mqttv3.MqttClient;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;
import org.tb.quarkus.scenario.model.Device;
import org.tb.quarkus.scenario.model.Telemetry;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

@ApplicationScoped
public class MqttTelemetryService {

    private static final String DEFAULT_MQTT_HOST = "thingsboard";
    private static final int DEFAULT_MQTT_PORT = 1883;
    private static final String TELEMETRY_TOPIC = "v1/devices/me/telemetry";

    private final ExecutorService executor = Executors.newCachedThreadPool();
    private final Map<String, MqttClient> activeClients = new ConcurrentHashMap<>();
    private final Random random = new Random();

    public void startStreaming(Device device, ScenarioContextService.DeviceContext ctx) {
        Telemetry tel = device.getTelemetry();
        if (tel == null || !"stream".equals(tel.getMode())) {
            return;
        }

        String clientId = "scenario-" + device.getName() + "-" + System.currentTimeMillis();
        executor.submit(() -> {
            try {
                MqttClient client = connect(clientId, ctx.mqttToken());
                activeClients.put(device.getName(), client);

                if ("csv".equals(tel.getSource()) && tel.getFile() != null) {
                    streamCsv(client, device, tel);
                } else if ("random".equals(tel.getSource())) {
                    streamRandom(client, device, tel);
                }
            } catch (Exception e) {
                Log.errorf(e, "MQTT streaming failed for device '%s'", device.getName());
            }
        });
        Log.infof("Started MQTT streaming for device '%s'", device.getName());
    }

    public void stopAll() {
        for (Map.Entry<String, MqttClient> entry : activeClients.entrySet()) {
            try {
                if (entry.getValue().isConnected()) {
                    entry.getValue().disconnect();
                }
                entry.getValue().close();
            } catch (MqttException e) {
                Log.warnf(e, "Error disconnecting MQTT client for '%s'", entry.getKey());
            }
        }
        activeClients.clear();
        executor.shutdown();
        try {
            executor.awaitTermination(10, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private MqttClient connect(String clientId, String token) throws MqttException {
        String host = System.getenv().getOrDefault("MQTT_HOST", DEFAULT_MQTT_HOST);
        int port = Integer.parseInt(System.getenv().getOrDefault("MQTT_PORT", String.valueOf(DEFAULT_MQTT_PORT)));

        MqttClient client = new MqttClient("tcp://" + host + ":" + port, clientId, new MemoryPersistence());

        MqttConnectOptions opts = new MqttConnectOptions();
        opts.setUserName(token);
        opts.setPassword("".toCharArray());
        opts.setCleanSession(true);
        opts.setAutomaticReconnect(true);
        opts.setKeepAliveInterval(60);

        client.connect(opts);
        return client;
    }

    private void streamCsv(MqttClient client, Device device, Telemetry tel) throws IOException, InterruptedException {
        List<String[]> rows = readCsv(tel.getFile());
        if (rows.isEmpty()) {
            Log.warnf("CSV file empty for device '%s': %s", device.getName(), tel.getFile());
            return;
        }

        List<String> metrics = tel.getMetrics();
        int intervalMs = tel.getIntervalMs();
        boolean loop = tel.isLoop();

        do {
            for (String[] row : rows) {
                if (row.length < 6) {
                    continue;
                }
                String payload = buildCsvPayload(metrics, row);
                publish(client, payload);

                if (intervalMs > 0) {
                    Thread.sleep(intervalMs);
                }
                if (!client.isConnected()) {
                    Log.warnf("MQTT client disconnected for device '%s', stopping", device.getName());
                    return;
                }
            }
        } while (loop && client.isConnected());
    }

    private void streamRandom(MqttClient client, Device device, Telemetry tel) throws InterruptedException {
        Map<String, Telemetry.MetricRange> ranges = tel.getMetricRanges();
        int intervalMs = tel.getIntervalMs();

        while (client.isConnected()) {
            StringBuilder sb = new StringBuilder("{");
            boolean first = true;
            for (String metric : tel.getMetrics()) {
                Telemetry.MetricRange range = ranges.get(metric);
                double min = range != null ? range.getMin() : 0;
                double max = range != null ? range.getMax() : 100;
                double value = min + random.nextDouble() * (max - min);
                if (!first) {
                    sb.append(",");
                }
                sb.append("\"").append(metric).append("\":").append(String.format("%.4f", value));
                first = false;
            }
            sb.append("}");
            publish(client, sb.toString());

            if (intervalMs > 0) {
                Thread.sleep(intervalMs);
            }
        }
    }

    private String buildCsvPayload(List<String> metrics, String[] row) {
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (int i = 0; i < metrics.size(); i++) {
            String metric = metrics.get(i);
            String value = (i + 2) < row.length ? row[i + 2] : "0";
            if (!first) {
                sb.append(",");
            }
            sb.append("\"").append(metric).append("\":").append(value);
            first = false;
        }
        sb.append("}");
        return sb.toString();
    }

    private void publish(MqttClient client, String payload) {
        try {
            MqttMessage msg = new MqttMessage(payload.getBytes(StandardCharsets.UTF_8));
            msg.setQos(1);
            client.publish(TELEMETRY_TOPIC, msg);
        } catch (MqttException e) {
            Log.warnf(e, "MQTT publish failed");
        }
    }

    private List<String[]> readCsv(String resourceName) throws IOException {
        List<String[]> rows = new ArrayList<>();
        InputStream is = getClass().getResourceAsStream("/" + resourceName);
        if (is == null) {
            is = Thread.currentThread().getContextClassLoader().getResourceAsStream(resourceName);
        }
        if (is == null) {
            throw new IOException("CSV resource not found: " + resourceName);
        }
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                rows.add(line.split(","));
            }
        }
        return rows;
    }
}
