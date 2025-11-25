package org.thingsboard.server.service.ws;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.client.WebSocketClient;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.handler.TextWebSocketHandler;
import org.thingsboard.server.common.data.id.TenantId;
import org.thingsboard.server.common.data.id.ModelLogId;
import org.thingsboard.server.common.data.id.PredictiveModelId;
import org.thingsboard.server.common.data.model.ModelLog;
import org.thingsboard.server.common.data.page.PageData;
import org.thingsboard.server.common.data.page.PageLink;
import org.thingsboard.server.dao.model.ModelLogService;

import javax.annotation.PostConstruct;
import javax.annotation.PreDestroy;
import java.io.IOException;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * WebSocket client service that connects to Python ML service.
 * 
 * This service:
 * 1. Acts as WebSocket proxy between UI and Python service
 * 2. Stores logs and predictions in database
 * 3. Loads active jobs on startup
 * 4. Maintains state persistence
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class PythonWebSocketClientService {

    private final ModelLogService modelLogService;
    private final ObjectMapper objectMapper;

    @Value("${fastapi.ws.url:ws://localhost:8000/models/ws/unified}")
    private String pythonWebSocketUrl;

    // Python WebSocket connection
    private WebSocketSession pythonSession;

    // UI client sessions: {sessionId -> WebSocketSession}
    private final Map<String, WebSocketSession> uiSessions = new ConcurrentHashMap<>();

    // WebSocket session locks for thread-safe sending: {sessionId -> Object}
    private final Map<String, Object> sessionLocks = new ConcurrentHashMap<>();

    // Command ID tracking: {commandId -> uiSessionId}
    private final Map<Integer, String> commandToSession = new ConcurrentHashMap<>();

    // Forecast ID subscriptions: {forecastId -> {modelType -> Set<uiSessionId>}}
    private final Map<String, Map<String, Set<String>>> subscriptions = new ConcurrentHashMap<>();

    // Active job tracking: {forecastId -> JobInfo}
    private final Map<String, JobInfo> activeJobs = new ConcurrentHashMap<>();

    private final AtomicInteger commandIdCounter = new AtomicInteger(1);
    private volatile boolean connected = false;

    // Queue for outgoing messages when Python is not connected
    private final BlockingQueue<PendingPythonRequest> pendingRequests = new LinkedBlockingQueue<>();

    @PostConstruct
    public void init() {
        loadActiveJobsFromDatabase();
        connectToPythonService();
    }

    @PreDestroy
    public void destroy() {
        disconnectFromPythonService();
    }

    /**
     * Load active jobs from database and subscribe to them
     * 
     * TODO: Implement this method when PredictiveMaintenanceConfig is available
     * For now, this method is a placeholder that will be implemented later.
     */
    private void loadActiveJobsFromDatabase() {
        try {
            log.info("Loading active predictive maintenance configs from database");

            // TODO: Query database for active configs
            // For now, we'll rely on UI clients to trigger job monitoring
            // The database persistence for logs/predictions works independently

            log.info("Active jobs loading placeholder - will be implemented with config table");

        } catch (Exception e) {
            log.error("Error loading active jobs from database", e);
        }
    }

    /**
     * Request status for all active jobs from Python service
     */
    private void requestStatusForActiveJobs() {
        if (activeJobs.isEmpty()) {
            log.debug("No active jobs to request status for");
            return;
        }
        try {
            for (String forecastId : activeJobs.keySet()) {
                requestJobStatus(forecastId);
            }
        } catch (Exception e) {
            log.error("Error requesting status for active jobs", e);
        }
    }

    /**
     * Connect to Python WebSocket service
     */
    private void connectToPythonService() {
        try {
            if (pythonSession != null && pythonSession.isOpen()) {
                log.debug("Already connected to Python WebSocket service");
                return;
            }

            log.info("Connecting to Python WebSocket service at: {}", pythonWebSocketUrl);

            WebSocketClient webSocketClient = new StandardWebSocketClient();

            // Use the new execute method for Spring 6+
            pythonSession = webSocketClient.execute(
                    new PythonWebSocketHandler(),
                    pythonWebSocketUrl).get(); // Block until connection is established

            log.info("Connected to Python WebSocket service");
            connected = true;
            flushPendingRequests();

            // Request status for all loaded active jobs
            requestStatusForActiveJobs();

        } catch (Exception e) {
            log.error("Failed to connect to Python WebSocket service", e);
            pythonSession = null;
            connected = false;
        }
    }

    /**
     * Flush all pending requests in the queue when connection is established
     */
    private void flushPendingRequests() {
        log.info("Flushing pending requests to Python service: {} requests", pendingRequests.size());
        PendingPythonRequest req;
        while ((req = pendingRequests.poll()) != null) {
            try {
                pythonSession.sendMessage(new TextMessage(req.message));
                log.info("Sent queued request to Python: {}", req.message);
                if (req.onSuccess != null) req.onSuccess.run();
            } catch (Exception e) {
                log.error("Failed to send queued request to Python", e);
                if (req.onFailure != null) req.onFailure.run();
            }
        }
    }

    /**
     * Helper to send or queue a message to Python service
     */
    private void sendOrQueueToPython(String message, Runnable onSuccess, Runnable onFailure) {
        if (pythonSession != null && pythonSession.isOpen()) {
            try {
                pythonSession.sendMessage(new TextMessage(message));
                if (onSuccess != null) onSuccess.run();
            } catch (Exception e) {
                log.error("Error sending message to Python service", e);
                if (onFailure != null) onFailure.run();
            }
        } else {
            log.info("Python not connected, queuing request: {}", message);
            pendingRequests.offer(new PendingPythonRequest(message, onSuccess, onFailure));
        }
    }

    // Helper class for queued requests
    private static class PendingPythonRequest {
        final String message;
        final Runnable onSuccess;
        final Runnable onFailure;
        PendingPythonRequest(String message, Runnable onSuccess, Runnable onFailure) {
            this.message = message;
            this.onSuccess = onSuccess;
            this.onFailure = onFailure;
        }
    }

    /**
     * Request job status from Python service
     */
    private void requestJobStatus(String forecastId) throws IOException {
        if (pythonSession != null && pythonSession.isOpen()) {
            int commandId = commandIdCounter.getAndIncrement();

            ObjectNode message = objectMapper.createObjectNode();
            message.put("commandId", commandId);
            message.put("type", "job_status");
            message.put("forecastId", forecastId);

            pythonSession.sendMessage(new TextMessage(message.toString()));
            log.debug("Requested job status for forecast {}", forecastId);
        }
    }

    /**
     * Disconnect from Python WebSocket service
     */
    public void disconnectFromPythonService() {
        if (pythonSession != null && pythonSession.isOpen()) {
            try {
                pythonSession.close();
                connected = false;
                log.info("Disconnected from Python WebSocket service");
            } catch (IOException e) {
                log.error("Error closing Python WebSocket connection", e);
            }
        }
    }

    /**
     * Reconnect to Python service every 30 seconds if disconnected
     */
    @Scheduled(fixedDelay = 30000)
    public void checkConnection() {
        if (!connected || pythonSession == null || !pythonSession.isOpen()) {
            log.info("Python WebSocket disconnected, attempting reconnection...");
            connectToPythonService();
        }
    }

    /**
     * Register UI client session
     */
    public void registerUiSession(String sessionId, WebSocketSession session) {
        uiSessions.put(sessionId, session);
        sessionLocks.putIfAbsent(sessionId, new Object());
        log.info("Registered UI session: {}", sessionId);
    }

    /**
     * Unregister UI client session
     */
    public void unregisterUiSession(String sessionId) {
        uiSessions.remove(sessionId);
        sessionLocks.remove(sessionId);

        // Remove from command tracking
        commandToSession.entrySet().removeIf(entry -> entry.getValue().equals(sessionId));

        // Remove from subscriptions
        subscriptions.values()
                .forEach(modelTypeMap -> modelTypeMap.values().forEach(sessions -> sessions.remove(sessionId)));

        log.info("Unregistered UI session: {}", sessionId);
    }

    /**
     * Thread-safe method to send message to UI session
     */
    private void sendMessageToUi(String sessionId, String message) throws IOException {
        WebSocketSession session = uiSessions.get(sessionId);
        if (session == null || !session.isOpen()) {
            log.warn("Cannot send message to UI session {}: session is null or closed", sessionId);
            return;
        }

        Object lock = sessionLocks.get(sessionId);
        if (lock == null) {
            // Fallback if lock doesn't exist (shouldn't happen)
            lock = sessionId.intern();
        }

        synchronized (lock) {
            if (session.isOpen()) {
                session.sendMessage(new TextMessage(message));
            }
        }
    }

    /**
     * Send activate command to Python service via WebSocket (can be called from
     * REST API)
     */
    public void sendActivateCommand(PredictiveModelId predictiveModelId) throws IOException {
        log.info(
                "[ACTIVATE] PythonWebSocketClientService: Preparing to send activate command for predictive model ID: {}",
                predictiveModelId);

        if (pythonSession == null || !pythonSession.isOpen()) {
            log.error(
                    "[ACTIVATE] PythonWebSocketClientService: Python service not connected. Session is null or closed.");
            throw new IOException("Python service not connected");
        }

        int commandId = commandIdCounter.getAndIncrement();
        log.info("[ACTIVATE] PythonWebSocketClientService: Generated command ID: {} for predictive model: {}",
                commandId, predictiveModelId);

        ObjectNode pythonMessage = objectMapper.createObjectNode();
        pythonMessage.put("commandId", commandId);
        pythonMessage.put("type", "activate");
        // Keep "forecastId" as the wire protocol field name for backward compatibility
        pythonMessage.put("forecastId", predictiveModelId.getId().toString());

        log.info("[ACTIVATE] PythonWebSocketClientService: Sending activate message to Python: {}",
                pythonMessage.toString());
        pythonSession.sendMessage(new TextMessage(pythonMessage.toString()));
        log.info(
                "[ACTIVATE] PythonWebSocketClientService: Activate command sent successfully to Python for predictive model: {}",
                predictiveModelId);
    }

    /**
     * Handle message from UI client
     */
    public void handleUiMessage(String sessionId, String message) {
        try {
            JsonNode jsonMessage = objectMapper.readTree(message);
            String type = jsonMessage.get("type").asText();

            switch (type) {
                case "job_status":
                    handleJobQuery(sessionId, jsonMessage);
                    break;
                case "job_listen":
                    handleJobListen(sessionId, jsonMessage);
                    break;
                case "subscribe_logs":
                    handleSubscribeLogs(sessionId, jsonMessage);
                    break;
                case "activate":
                    handleActivate(sessionId, jsonMessage);
                    break;
                case "ping":
                    handlePing(sessionId, jsonMessage);
                    break;
                default:
                    log.warn("Unknown message type from UI: {}", type);
            }
        } catch (Exception e) {
            log.error("Error handling UI message from session {}", sessionId, e);
            sendErrorToUi(sessionId, "Error processing request: " + e.getMessage());
        }
    }

    /**
     * Handle job status/logs query
     */
    private void handleJobQuery(String sessionId, JsonNode message) throws IOException {
        int commandId = commandIdCounter.getAndIncrement();
        commandToSession.put(commandId, sessionId);

        // Create message for Python service
        ObjectNode pythonMessage = objectMapper.createObjectNode();
        pythonMessage.put("commandId", commandId);
        pythonMessage.put("type", message.get("type").asText());
        pythonMessage.put("forecastId", message.get("forecastId").asText());

        if (message.has("data")) {
            pythonMessage.set("data", message.get("data"));
        }

        // Send to Python service
        if (pythonSession != null && pythonSession.isOpen()) {
            pythonSession.sendMessage(new TextMessage(pythonMessage.toString()));
            log.debug("Sent {} request to Python for forecast {}",
                    message.get("type").asText(),
                    message.get("forecastId").asText());
        } else {
            sendErrorToUi(sessionId, "Python service not connected");
        }
    }

    /**
     * Handle job listen request
     */
    private void handleJobListen(String sessionId, JsonNode message) throws IOException {
        String forecastId = message.get("forecastId").asText();
        String modelType = message.get("modelType").asText();

        // Register subscription
        subscriptions
                .computeIfAbsent(forecastId, k -> new ConcurrentHashMap<>())
                .computeIfAbsent(modelType, k -> ConcurrentHashMap.newKeySet())
                .add(sessionId);

        int commandId = commandIdCounter.getAndIncrement();
        commandToSession.put(commandId, sessionId);

        // Create message for Python service
        ObjectNode pythonMessage = objectMapper.createObjectNode();
        pythonMessage.put("commandId", commandId);
        pythonMessage.put("type", "job_listen");
        pythonMessage.put("forecastId", forecastId);
        pythonMessage.put("modelType", modelType);

        // Send to Python service
        if (pythonSession != null && pythonSession.isOpen()) {
            pythonSession.sendMessage(new TextMessage(pythonMessage.toString()));
            log.info("Subscribed UI session {} to {} predictions for forecast {}",
                    sessionId, modelType, forecastId);
        } else {
            sendErrorToUi(sessionId, "Python service not connected");
        }
    }

    /**
     * Handle ping from UI
     */
    private void handlePing(String sessionId, JsonNode message) throws IOException {
        ObjectNode response = objectMapper.createObjectNode();
        response.put("type", "pong");
        response.put("timestamp", System.currentTimeMillis());

        sendMessageToUi(sessionId, response.toString());
    }

    /**
     * Handle job_logs request - retrieves 7 days of logs from database
     */
    private void handleJobLogsRequest(String sessionId, JsonNode message) throws IOException {
        String forecastId = message.get("forecastId").asText();
        int limit = message.has("data") && message.get("data").has("limit")
                ? message.get("data").get("limit").asInt()
                : 1000;

        try {
            // Calculate 7 days ago timestamp
            long sevenDaysAgo = System.currentTimeMillis() - (7L * 24 * 60 * 60 * 1000);
            long now = System.currentTimeMillis();

            // Retrieve logs from database for the past 7 days
            PageData<ModelLog> logsPage = modelLogService.findByModelIdAndTimeWindow(
                    forecastId,
                    sevenDaysAgo,
                    now,
                    null, // all log levels
                    null, // all sources
                    new PageLink(limit, 0, null, new org.thingsboard.server.common.data.page.SortOrder("createdTime",
                            org.thingsboard.server.common.data.page.SortOrder.Direction.DESC)));

            // Send logs in batches to avoid WebSocket buffer overflow
            int batchSize = 10; // Send 10 logs per message
            int totalLogs = logsPage.getData().size();
            int sentLogs = 0;

            for (int i = 0; i < totalLogs; i += batchSize) {
                int endIndex = Math.min(i + batchSize, totalLogs);

                // Format logs for UI
                ObjectNode response = objectMapper.createObjectNode();
                response.put("type", "logs");

                ObjectNode data = objectMapper.createObjectNode();
                ArrayNode logsArray = objectMapper.createArrayNode();

                for (int j = i; j < endIndex; j++) {
                    ModelLog modelLog = logsPage.getData().get(j);
                    ObjectNode logNode = objectMapper.createObjectNode();
                    logNode.put("timestamp", new java.util.Date(modelLog.getCreatedTime()).toInstant().toString());
                    logNode.put("level", modelLog.getLogLevel() != null ? modelLog.getLogLevel() : "INFO");
                    logNode.put("message", modelLog.getMessage() != null ? modelLog.getMessage() : "");

                    if (modelLog.getSource() != null) {
                        logNode.put("source", modelLog.getSource());
                    } else if (modelLog.getMetadata() != null && modelLog.getMetadata().has("source")) {
                        logNode.put("source", modelLog.getMetadata().get("source").asText());
                    }

                    logsArray.add(logNode);
                }

                data.set("logs", logsArray);
                data.put("count", logsArray.size());
                response.set("data", data);

                // Send to UI (thread-safe)
                sendMessageToUi(sessionId, response.toString());
                sentLogs += logsArray.size();

                log.debug("Sent batch of {} logs (total: {}/{}) for forecast {} to UI session {}",
                        logsArray.size(), sentLogs, totalLogs, forecastId, sessionId);
            }

            log.info("Sent {} logs from past 7 days for forecast {} to UI session {}",
                    sentLogs, forecastId, sessionId);
        } catch (Exception e) {
            log.error("Error retrieving logs from database for forecast {}", forecastId, e);
            sendErrorToUi(sessionId, "Error retrieving logs: " + e.getMessage());
        }
    }

    /**
     * Handle subscribe_logs - sends 7 days of historical logs + subscribes to
     * real-time updates
     */
    private void handleSubscribeLogs(String sessionId, JsonNode message) throws IOException {
        String forecastId = message.get("forecastId").asText();

        // First, send historical logs from database (7 days)
        // handleJobLogsRequest(sessionId, message);

        // Then subscribe to real-time log updates via Python
        int commandId = commandIdCounter.getAndIncrement();
        commandToSession.put(commandId, sessionId);

        ObjectNode pythonMessage = objectMapper.createObjectNode();
        pythonMessage.put("commandId", commandId);
        pythonMessage.put("type", "subscribe_logs");
        pythonMessage.put("forecastId", forecastId);

        sendOrQueueToPython(pythonMessage.toString(),
            () -> log.info("Subscribed UI session {} to real-time logs for forecast {}", sessionId, forecastId),
            () -> sendErrorToUi(sessionId, "Python service not connected")
        );
    }

    /**
     * Handle activate command from UI - sends to unified Python WebSocket
     */
    private void handleActivate(String sessionId, JsonNode message) throws IOException {
        String forecastId = message.get("forecastId").asText();

        int commandId = commandIdCounter.getAndIncrement();
        commandToSession.put(commandId, sessionId);

        log.info("[ACTIVATE] Created commandId {} mapping to sessionId {} for forecast {}",
                commandId, sessionId, forecastId);

        // Create activate message for Python unified endpoint
        ObjectNode pythonMessage = objectMapper.createObjectNode();
        pythonMessage.put("commandId", commandId);
        pythonMessage.put("type", "activate");
        pythonMessage.put("forecastId", forecastId);

        if (message.has("data")) {
            pythonMessage.set("data", message.get("data"));
        }

        log.info("[ACTIVATE] Sending to Python: {}", pythonMessage.toString());

        sendOrQueueToPython(pythonMessage.toString(),
            () -> log.info("[ACTIVATE] Successfully sent activate command to Python for forecast {}", forecastId),
            () -> sendErrorToUi(sessionId, "Python service not connected")
        );
    }

    /**
     * Handle response from Python service
     */
    private void handlePythonResponse(JsonNode message) {
        // log at debug level the received message - type, commandId, forecastId
        log.info("[handlePythonResponse] Received Python response: type={}, commandId={}, forecastId={}",
                message.has("type") ? message.get("type").asText() : "N/A",
                message.has("commandId") ? message.get("commandId").asText() : "N/A",
                message.has("forecastId") ? message.get("forecastId").asText() : "N/A");
        try {
            String type = message.get("type").asText();

            if ("prediction".equals(type)) {
                log.info(
                        "[handlePythonResponse] Received prediction response: commandId={}, forecastId={}",
                        message.has("commandId") ? message.get("commandId").asText() : "N/A",
                        message.has("forecastId") ? message.get("forecastId").asText() : "N/A");
                // Store prediction in database
                storePrediction(message);

                // Broadcast prediction to subscribed UI sessions
                broadcastPrediction(message);

            } else if ("progress".equals(type)) {
                // Forward training progress to UI - always route regardless of commandId
                routeToUiSession(message);

            } else if ("complete".equals(type)) {
                // Forward training completion to UI - always route regardless of commandId
                routeToUiSession(message);

            } else if ("logs".equals(type)) {
                log.info(
                        "[handlePythonResponse] Received logs message: commandId={}, forecastId={}",
                        message.has("commandId") ? message.get("commandId").asText() : "N/A",
                        message.has("forecastId") ? message.get("forecastId").asText() : "N/A");
                // Forward logs to UI - always route regardless of commandId
                routeToUiSession(message);

            } else if ("response".equals(type)) {
                String model = message.has("model") ? message.get("model").asText() : "";

                if ("job".equals(model)) {
                    // Handle job status/logs response
                    handleJobResponse(message);
                } else {
                    // Handle model-specific response
                    handleModelResponse(message);
                }

                // Route to UI session - always route regardless of commandId
                routeToUiSession(message);

            } else if ("connection".equals(type)) {
                log.info("Python service connection confirmed");

            } else if ("error".equals(type)) {
                handlePythonError(message);
            }
        } catch (Exception e) {
            log.error("Error handling Python response", e);
        }
    }

    /**
     * Handle job status/logs response
     */
    private void handleJobResponse(JsonNode message) {
        try {
            String forecastId = message.get("forecastId").asText();
            JsonNode data = message.get("data");

            if (data.has("status")) {
                String status = data.get("status").asText();

                // Update active jobs tracking
                if ("running".equals(status)) {
                    JobInfo jobInfo = activeJobs.computeIfAbsent(forecastId, k -> new JobInfo());
                    jobInfo.setForecastId(forecastId);
                    jobInfo.setStatus(status);

                    if (data.has("model_type")) {
                        jobInfo.setModelType(data.get("model_type").asText());
                    }
                    if (data.has("device_id")) {
                        jobInfo.setDeviceId(data.get("device_id").asText());
                    }
                    if (data.has("start_time")) {
                        jobInfo.setStartTime(data.get("start_time").asText());
                    }
                    if (data.has("iterations")) {
                        jobInfo.setIterations(data.get("iterations").asInt());
                    }

                    log.debug("Updated job status: {} - {}", forecastId, status);

                } else if ("stopped".equals(status) || "not_found".equals(status)) {
                    activeJobs.remove(forecastId);
                    log.debug("Removed job from tracking: {} - {}", forecastId, status);
                }
            }

            if (data.has("logs")) {
                // Store logs in database
                storeLogs(forecastId, data.get("logs"));
            }

        } catch (Exception e) {
            log.error("Error handling job response", e);
        }
    }

    /**
     * Handle model-specific response
     */
    private void handleModelResponse(JsonNode message) {
        try {
            if (message.has("data") && message.get("data").has("status")) {
                String status = message.get("data").get("status").asText();

                if ("listening".equals(status)) {
                    String forecastId = message.get("forecastId").asText();
                    String model = message.get("model").asText();

                    log.info("Successfully subscribed to {} predictions for forecast {}",
                            model, forecastId);
                }
            }
        } catch (Exception e) {
            log.error("Error handling model response", e);
        }
    }

    /**
     * Handle error from Python service
     */
    private void handlePythonError(JsonNode message) {
        try {
            String errorMsg = message.has("message") ? message.get("message").asText() : "Unknown error";

            if (message.has("commandId")) {
                // Route error to UI session
                routeToUiSession(message);
            }

            log.error("Error from Python service: {}", errorMsg);

        } catch (Exception e) {
            log.error("Error handling Python error message", e);
        }
    }

    /**
     * Route message to UI session based on commandId, or broadcast if no commandId
     */
    private void routeToUiSession(JsonNode message) throws IOException {
        String type = message.has("type") ? message.get("type").asText() : "unknown";

        // If message has commandId, route to specific session
        if (message.has("commandId")) {
            int commandId = message.get("commandId").asInt();

            // Only remove commandId mapping for final messages (complete, error)
            // Keep mapping for intermediate messages (progress) so they can be routed too
            boolean isFinalMessage = "complete".equals(type) || "error".equals(type);

            log.info("[ROUTE] Routing {} message with commandId {} - isFinal: {}, current mappings: {}",
                    type, commandId, isFinalMessage, commandToSession.keySet());

            String sessionId = isFinalMessage
                    ? commandToSession.remove(commandId)
                    : commandToSession.get(commandId);

            log.info("[ROUTE] SessionId for commandId {}: {}", commandId, sessionId);

            if (sessionId != null) {
                sendMessageToUi(sessionId, message.toString());
                log.info("[ROUTE] Successfully routed {} response for commandId {} to UI session {}",
                        type, commandId, sessionId);
            } else {
                // log.warn("No UI session mapping found for commandId {}, broadcasting to all sessions", commandId);
                // broadcastToAllSessions(message, type);
            }
        } else {
            // // No commandId - broadcast to all UI sessions
            // log.debug("Broadcasting {} message to all UI sessions (no commandId)", type);
            // broadcastToAllSessions(message, type);
        }
    }

    /**
     * Broadcast message to all connected UI sessions
     */
    private void broadcastToAllSessions(JsonNode message, String type) throws IOException {
        String messageStr = message.toString();
        int sentCount = 0;

        for (Map.Entry<String, WebSocketSession> entry : uiSessions.entrySet()) {
            WebSocketSession session = entry.getValue();
            if (session != null && session.isOpen()) {
                try {
                    session.sendMessage(new TextMessage(messageStr));
                    sentCount++;
                } catch (IOException e) {
                    log.error("Error broadcasting {} to UI session {}", type, entry.getKey(), e);
                }
            }
        }

        log.debug("Broadcasted {} message to {} UI sessions", type, sentCount);
    }

    /**
     * Store prediction in database
     */
    private void storePrediction(JsonNode message) {
        log.info(
                "[storePrediction] Received prediction message: forecastId={}, modelType={}",
                message.has("forecastId") ? message.get("forecastId").asText() : "N/A",
                message.has("model") ? message.get("model").asText() : "N/A");
        try {
            String forecastId = message.get("forecastId").asText();
            String modelType = message.get("model").asText();
            JsonNode data = message.get("data");

            // Create prediction log entry
            ModelLog logEntry = new ModelLog();
            logEntry.setId(new ModelLogId(UUID.randomUUID()));
            logEntry.setCreatedTime(System.currentTimeMillis());

            // Store as metadata since ModelLog uses JsonNode
            ObjectNode metadata = objectMapper.createObjectNode();
            metadata.put("forecastId", forecastId);
            metadata.put("modelType", modelType);
            metadata.put("logType", "PREDICTION");
            metadata.set("data", data);

            logEntry.setMetadata(metadata);
            logEntry.setLogLevel("INFO");

            if (data.has("iteration")) {
                logEntry.setMessage("Prediction iteration #" + data.get("iteration").asInt());
            } else {
                logEntry.setMessage("Prediction generated");
            }

            modelLogService.save(TenantId.SYS_TENANT_ID, logEntry);

            log.debug("Stored {} prediction for forecast {} in database", modelType, forecastId);

        } catch (Exception e) {
            log.error("Error storing prediction in database", e);
        }
    }

    /**
     * Store logs in database
     */
    private void storeLogs(String forecastId, JsonNode logsArray) {
        try {
            if (logsArray.isArray()) {
                for (JsonNode logNode : logsArray) {
                    ModelLog logEntry = new ModelLog();
                    logEntry.setId(new ModelLogId(UUID.randomUUID()));

                    String timestamp = logNode.get("timestamp").asText();
                    String level = logNode.get("level").asText();
                    String logMessage = logNode.get("message").asText();

                    // Parse timestamp
                    try {
                        long ts = java.time.Instant.parse(timestamp).toEpochMilli();
                        logEntry.setCreatedTime(ts);
                    } catch (Exception e) {
                        logEntry.setCreatedTime(System.currentTimeMillis());
                    }

                    logEntry.setLogLevel(level);
                    logEntry.setMessage(logMessage);

                    // Store metadata
                    ObjectNode metadata = objectMapper.createObjectNode();
                    metadata.put("forecastId", forecastId);
                    metadata.put("logType", "JOB_LOG");
                    logEntry.setMetadata(metadata);

                    modelLogService.save(TenantId.SYS_TENANT_ID, logEntry);
                }

                log.debug("Stored {} job logs for forecast {} in database",
                        logsArray.size(), forecastId);
            }
        } catch (Exception e) {
            log.error("Error storing logs in database", e);
        }
    }

    /**
     * Broadcast prediction to subscribed UI sessions
     */
    private void broadcastPrediction(JsonNode message) throws IOException {
        String forecastId = message.get("forecastId").asText();
        String modelType = message.get("model").asText();

        log.info(
                "[broadcastPrediction] Broadcasting {} prediction for forecastId={} to subscribed UI sessions",
                modelType, forecastId);

        // Get subscribed sessions
        Set<String> subscribedSessions = subscriptions
                .getOrDefault(forecastId, Collections.emptyMap())
                .getOrDefault(modelType, Collections.emptySet());

        // Broadcast to all subscribed UI sessions (thread-safe)
        String messageStr = message.toString();
        for (String sessionId : subscribedSessions) {
            try {
                sendMessageToUi(sessionId, messageStr);
                log.debug("Broadcasted {} prediction for {} to UI session {}",
                        modelType, forecastId, sessionId);
            } catch (IOException e) {
                log.error("Error broadcasting to session {}: {}", sessionId, e.getMessage());
            }
        }
    }

    /**
     * Send error to UI client
     */
    private void sendErrorToUi(String sessionId, String errorMessage) {
        try {
            ObjectNode error = objectMapper.createObjectNode();
            error.put("type", "error");
            error.put("message", errorMessage);
            error.put("timestamp", System.currentTimeMillis());

            sendMessageToUi(sessionId, error.toString());
        } catch (IOException e) {
            log.error("Error sending error message to UI session {}", sessionId, e);
        }
    }

    /**
     * WebSocket handler for Python service connection
     */
    private class PythonWebSocketHandler extends TextWebSocketHandler {

        @Override
        public void afterConnectionEstablished(WebSocketSession session) {
            log.info("Python WebSocket connection established");
            connected = true;

            // Send connection confirmation
            try {
                ObjectNode confirmMessage = objectMapper.createObjectNode();
                confirmMessage.put("type", "connection");
                confirmMessage.put("message", "ThingsBoard connected");
                session.sendMessage(new TextMessage(confirmMessage.toString()));
                log.info("Python service connection confirmed");
            } catch (IOException e) {
                log.error("Error sending connection confirmation", e);
            }
        }

        @Override
        protected void handleTextMessage(WebSocketSession session, TextMessage message) {
            try {
                JsonNode jsonMessage = objectMapper.readTree(message.getPayload());
                handlePythonResponse(jsonMessage);
            } catch (Exception e) {
                log.error("Error handling message from Python service", e);
            }
        }

        @Override
        public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
            log.warn("Python WebSocket connection closed: {}", status);
            pythonSession = null;
            connected = false;
            // Connection will be re-established by @Scheduled checkConnection method
        }

        @Override
        public void handleTransportError(WebSocketSession session, Throwable exception) {
            log.error("Python WebSocket transport error", exception);
        }
    }
}
