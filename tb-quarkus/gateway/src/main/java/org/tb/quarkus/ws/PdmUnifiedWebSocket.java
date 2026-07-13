package org.tb.quarkus.ws;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.quarkus.runtime.StartupEvent;
import io.vertx.core.Vertx;
import io.vertx.core.http.ServerWebSocket;
import io.vertx.ext.web.Router;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.event.Observes;
import jakarta.inject.Inject;
import org.jboss.logging.Logger;
import org.tb.quarkus.event.model.StreamMessage;
import org.tb.quarkus.event.model.StreamMessageData;
import org.tb.quarkus.event.model.StreamMessageDataType;
import org.tb.quarkus.event.model.StreamMessageStatus;
import org.tb.quarkus.event.model.StreamMessageType;
import org.tb.quarkus.service.PdmCommandService;

import java.time.Instant;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@ApplicationScoped
public class PdmUnifiedWebSocket {

    private static final Logger LOG = Logger.getLogger(PdmUnifiedWebSocket.class);
    private static final String MODELINA_PACKAGE = "org.tb.quarkus.event.model.";

    @Inject Router router;
    @Inject Vertx vertx;
    @Inject ObjectMapper mapper;
    @Inject PdmCommandService pdmCommandService;

    void register(@Observes StartupEvent event) {
        router.route("/models/ws/unified").handler(ctx -> {
            String token = ctx.request().getParam("token");
            ctx.request().toWebSocket()
                    .onSuccess(ws -> {
                        if (token == null || token.isBlank()) {
                            ws.close((short) 4001, "Unauthorized - no token");
                            return;
                        }
                        WsState state = new WsState();
                        long timerId = vertx.setPeriodic(2_000, ignored -> pushSubscriptions(ws, state));
                        ws.closeHandler(ignored -> vertx.cancelTimer(timerId));
                        ws.exceptionHandler(error -> {
                            LOG.warn("PdM websocket connection error", error);
                            vertx.cancelTimer(timerId);
                        });
                        ws.textMessageHandler(message -> vertx.executeBlocking(() -> handle(message, state), false)
                                .onSuccess(response -> send(ws, response))
                                .onFailure(error -> {
                                    LOG.warn("Failed to handle PdM websocket message", error);
                                    send(ws, error(0, null, error.getMessage()));
                                }));
                        send(ws, response(0, null, StreamMessageType.RESPONSE, "connection", "Connected to unified model service", Map.of()));
                    })
                    .onFailure(ctx::fail);
        });
    }

    private Object handle(String rawMessage, WsState state) {
        try {
            JsonNode node = mapper.readTree(rawMessage);
            String type = text(node.get("type"));
            int commandId = node.path("commandId").asInt(node.path("cmdId").asInt(0));
            String forecastId = text(node.get("forecastId"));
            if (type == null || type.isBlank()) {
                return error(commandId, forecastId, "Missing command type");
            }
            if (!"ping".equals(type) && (forecastId == null || forecastId.isBlank())) {
                return error(commandId, forecastId, "Missing forecastId");
            }

            switch (type) {
                case "ping" -> {
                    return pong(commandId);
                }
                case "activate" -> {
                    readGeneratedCommand("ActivateCommand", node);
                    state.statusSubscriptions.put(forecastId, commandId);
                    state.logSubscriptions.put(forecastId, new LogSubscription(commandId, null, 100));
                    LOG.infof("PdM websocket activate auto-subscribed forecastId=%s commandId=%s", forecastId, commandId);
                    return response(commandId, forecastId, StreamMessageType.PROGRESS, "predictive_model", "Training command queued",
                            pdmCommandService.train(forecastId, commandData(node, commandId)));
                }
                case "job_status", "model_status" -> {
                    readGeneratedCommand(type.equals("job_status") ? "JobStatusCommand" : "ModelStatusCommand", node);
                    state.statusSubscriptions.put(forecastId, commandId);
                    return response(commandId, forecastId, type.equals("job_status") ? StreamMessageType.JOB_STATUS : StreamMessageType.MODEL_STATUS, "predictive_model", "Job status",
                            pdmCommandService.status(forecastId));
                }
                case "pause_job" -> {
                    readGeneratedCommand("PauseJobCommand", node);
                    String modelType = text(node.path("data").get("modelType"));
                    return response(commandId, forecastId, StreamMessageType.RESPONSE, "response", "Pause command queued",
                            pdmCommandService.pause(forecastId, modelType, Integer.toString(commandId)));
                }
                case "unpause_job" -> {
                    readGeneratedCommand("UnpauseJobCommand", node);
                    String modelType = text(node.path("data").get("modelType"));
                    return response(commandId, forecastId, StreamMessageType.RESPONSE, "response", "Unpause command queued",
                            pdmCommandService.unpause(forecastId, modelType, Integer.toString(commandId)));
                }
                case "subscribe_logs", "job_logs" -> {
                    readGeneratedCommand(type.equals("subscribe_logs") ? "SubscribeLogsCommand" : "JobStatusCommand", node);
                    String modelType = text(node.path("data").get("modelType"));
                    state.logSubscriptions.put(forecastId, new LogSubscription(
                            commandId,
                            modelType,
                            node.path("data").path("limit").asInt(100)));
                    return logsResponse(commandId, forecastId,
                            pdmCommandService.logs(forecastId, modelType, node.path("data").path("limit").asInt(100)));
                }
                case "unsubscribe_model_status" -> {
                    state.statusSubscriptions.remove(forecastId);
                    return response(commandId, forecastId, StreamMessageType.RESPONSE, "response", "Unsubscribed", Map.of("status", "ok"));
                }
                case "unsubscribe_logs" -> {
                    state.logSubscriptions.remove(forecastId);
                    return response(commandId, forecastId, StreamMessageType.RESPONSE, "response", "Unsubscribed", Map.of("status", "ok"));
                }
                case "unsubscribe_predictions" -> {
                    return response(commandId, forecastId, StreamMessageType.RESPONSE, "response", "Unsubscribed", Map.of("status", "ok"));
                }
                default -> {
                    return error(commandId, forecastId, "Unsupported command type: " + type);
                }
            }
        } catch (Exception e) {
            LOG.warn("Failed to handle PdM websocket message", e);
            return error(0, null, e.getMessage());
        }
    }

    private void pushSubscriptions(ServerWebSocket ws, WsState state) {
        if (state.isEmpty()) {
            return;
        }
        vertx.executeBlocking(() -> subscriptionSnapshot(state), false)
                .onSuccess(snapshot -> snapshot.forEach(message -> send(ws, message)))
                .onFailure(error -> LOG.warn("Failed to push PdM websocket subscription update", error));
    }

    private java.util.List<Object> subscriptionSnapshot(WsState state) {
        java.util.List<Object> messages = new java.util.ArrayList<>();
        state.statusSubscriptions.forEach((forecastId, commandId) -> {
            try {
                messages.add(response(commandId, forecastId, StreamMessageType.MODEL_STATUS, "predictive_model", "Job status",
                        pdmCommandService.status(forecastId)));
            } catch (Exception e) {
                LOG.warnf(e, "Failed to build PdM status update for forecastId=%s", forecastId);
                messages.add(error(commandId, forecastId, "Failed to build status update: " + e.getMessage()));
            }
        });
        state.logSubscriptions.forEach((forecastId, subscription) -> {
            try {
                messages.add(logsResponse(subscription.commandId(), forecastId,
                        pdmCommandService.logs(forecastId, subscription.modelType(), subscription.limit())));
            } catch (Exception e) {
                LOG.warnf(e, "Failed to build PdM logs update for forecastId=%s", forecastId);
            }
        });
        return messages;
    }

    private Object readGeneratedCommand(String simpleName, JsonNode node) throws Exception {
        Class<?> type = Class.forName(MODELINA_PACKAGE + simpleName);
        return mapper.treeToValue(node, type);
    }

    private Map<String, Object> commandData(JsonNode node, int commandId) {
        Map<String, Object> data = node.path("data").isObject()
                ? mapper.convertValue(node.path("data"), Map.class)
                : new LinkedHashMap<>();
        copyRootValue(node, data, "modelType");
        copyRootValue(node, data, "deviceId");
        data.putIfAbsent("commandId", Integer.toString(commandId));
        return data;
    }

    private void copyRootValue(JsonNode node, Map<String, Object> data, String field) {
        JsonNode value = node.get(field);
        if (value != null && !value.isNull() && !data.containsKey(field)) {
            data.put(field, value.asText());
        }
    }

    private StreamMessage pong(int commandId) {
        return response(commandId, null, StreamMessageType.RESPONSE, "response", "pong", Map.of("timestamp", Instant.now().toString()));
    }

    private StreamMessage response(int commandId, String forecastId, StreamMessageType type, String model, String message, Object payload) {
        StreamMessage stream = new StreamMessage();
        stream.setCmdId(commandId);
        stream.setType(type);
        stream.setModel(model);
        stream.setForecastId(forecastId);

        StreamMessageData data = new StreamMessageData();
        data.setType(StreamMessageDataType.CONNECTION);
        data.setForecastId(forecastId);
        data.setMessage(message);
        data.setData(payload);
        data.setStatus(StreamMessageStatus.RUNNING);
        data.setTimestamp(Instant.now().toString());
        stream.setData(data);
        return stream;
    }

    private Map<String, Object> logsResponse(int commandId, String forecastId, Map<String, Object> payload) {
        List<?> rawLogs = payload.get("logs") instanceof List<?> list ? list : List.of();
        List<Map<String, Object>> logEntries = rawLogs.stream()
                .map(this::normalizeLog)
                .toList();

        Map<String, Object> logs = new LinkedHashMap<>();
        logs.put("logs", logEntries);
        logs.put("count", payload.get("count") instanceof Number number ? number.intValue() : rawLogs.size());
        logs.put("modelType", payload.getOrDefault("modelType", "BOTH"));

        Map<String, Object> stream = new LinkedHashMap<>();
        stream.put("cmdId", commandId);
        stream.put("type", "logs");
        stream.put("forecastId", forecastId);
        stream.put("data", logs);
        stream.put("timestamp", Instant.now().toString());
        return stream;
    }

    private Map<String, Object> normalizeLog(Object rawLog) {
        Map<String, Object> log = new LinkedHashMap<>(mapper.convertValue(rawLog, Map.class));
        String source = textValue(log.get("source"));
        if ("AnomalyPredictor".equals(source)) {
            log.put("source", "AnomalyModel");
        } else if (!"ForecastModel".equals(source) && !"AnomalyModel".equals(source)) {
            log.remove("source");
        }
        if (!log.containsKey("type") || log.get("type") == null) {
            String normalizedSource = textValue(log.get("source"));
            log.put("type", "ForecastModel".equals(normalizedSource) ? "forecast" : "system");
        }
        return log;
    }

    private StreamMessage error(int commandId, String forecastId, String message) {
        StreamMessage stream = response(commandId, forecastId, StreamMessageType.ERROR, "error", message, Map.of());
        stream.setType(StreamMessageType.ERROR);
        stream.setErrorMsg(message);
        return stream;
    }

    private void send(ServerWebSocket ws, Object message) {
        try {
            ws.writeTextMessage(mapper.writeValueAsString(message));
        } catch (Exception e) {
            LOG.warn("Failed to write PdM websocket message", e);
        }
    }

    private String text(JsonNode node) {
        return node == null || node.isMissingNode() || node.isNull() ? null : node.asText();
    }

    private String textValue(Object value) {
        return value == null ? null : value.toString();
    }

    private record LogSubscription(int commandId, String modelType, int limit) {
    }

    private static class WsState {
        private final Map<String, Integer> statusSubscriptions = new ConcurrentHashMap<>();
        private final Map<String, LogSubscription> logSubscriptions = new ConcurrentHashMap<>();

        private boolean isEmpty() {
            return statusSubscriptions.isEmpty() && logSubscriptions.isEmpty();
        }
    }
}
