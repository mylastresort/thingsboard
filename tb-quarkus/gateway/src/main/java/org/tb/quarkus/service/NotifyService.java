package org.tb.quarkus.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.persistence.EntityManager;
import jakarta.ws.rs.InternalServerErrorException;
import jakarta.ws.rs.NotFoundException;
import jakarta.ws.rs.core.MediaType;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.eclipse.microprofile.faulttolerance.Retry;
import org.jboss.logging.Logger;
import org.tb.quarkus.model.NotifyAlarmAssigneeRequest;
import org.tb.quarkus.model.NotifyAlarmBody;
import org.tb.quarkus.model.NotifyClaimAssigneeRequest;
import org.tb.quarkus.model.NotifySentResponse;
import org.tb.quarkus.model.NotifyStatusResponse;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@ApplicationScoped
public class NotifyService {

    private static final Logger LOG = Logger.getLogger(NotifyService.class);
    private static final DateTimeFormatter START_AT_FORMATTER =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final String TENANT_ADMIN_EMAIL = "tenant@thingsboard.org";
    private static final String SYSADMIN_EMAIL = "sysadmin@thingsboard.org";

    @Inject EntityManager em;
    @Inject ObjectMapper mapper;

    @ConfigProperty(name = "WB_TOKEN")
    Optional<String> whatsappToken;

    @ConfigProperty(name = "WB_VERSION", defaultValue = "v20.0")
    String whatsappVersion;

    @ConfigProperty(name = "PhoneNumberID")
    Optional<String> phoneNumberId;

    private final HttpClient httpClient = HttpClient.newHttpClient();

    public NotifySentResponse notifyNewAlarm(NotifyAlarmBody body) {
        List<?> phones = em.createNativeQuery(
                "SELECT phone FROM public.tb_user WHERE phone IS NOT NULL")
                .getResultList();

        int sent = 0;
        for (Object phone : phones) {
            sendNotification(string(phone), body.getSeverity(), body.getType(), body.getStartTs());
            sent++;
        }
        NotifySentResponse response = new NotifySentResponse();
        response.setSent(sent);
        return response;
    }

    public NotifyStatusResponse notifyClaimAssignee(NotifyClaimAssigneeRequest body) {
        List<?> rows = em.createNativeQuery(
                "SELECT phone FROM public.tb_user WHERE email = :email")
                .setParameter("email", body.getEmail())
                .getResultList();
        if (rows.isEmpty() || rows.get(0) == null) {
            throw new NotFoundException("User phone was not found");
        }

        NotifyAlarmBody alarmBody = body.getBody();
        sendNotification(
                string(rows.get(0)),
                alarmBody.getSeverity(),
                alarmBody.getType(),
                alarmBody.getStartTs());
        return status("sent");
    }

    public NotifyStatusResponse notifyAlarmAssignee(NotifyAlarmAssigneeRequest body) {
        List<?> rows = em.createNativeQuery(
                "SELECT phone, email FROM public.tb_user WHERE id = :assignee")
                .setParameter("assignee", body.getAssigneeId())
                .getResultList();
        if (rows.isEmpty()) {
            throw new NotFoundException("User was not found");
        }

        Object[] row = (Object[]) rows.get(0);
        String phone = string(row[0]);
        String email = string(row[1]);
        if (TENANT_ADMIN_EMAIL.equals(email) || SYSADMIN_EMAIL.equals(email)) {
            return status("skipped");
        }
        if (phone == null || phone.isBlank()) {
            throw new NotFoundException("User phone was not found");
        }

        sendNotification(phone, body.getSeverity(), body.getType(), body.getStartTs());
        return status("sent");
    }

    @Retry(maxRetries = 3, delay = 2000, maxDelay = 10000, retryOn = {IOException.class, InterruptedException.class})
    private void sendNotification(String phone, String severity, String type, Long startTs) {
        String token = whatsappToken.filter(value -> !value.isBlank())
                .orElseThrow(() -> new InternalServerErrorException("WhatsApp provider is not configured"));
        String providerPhoneNumberId = phoneNumberId.filter(value -> !value.isBlank())
                .orElseThrow(() -> new InternalServerErrorException("WhatsApp provider is not configured"));

        Map<String, Object> payload = Map.of(
                "messaging_product", "whatsapp",
                "recipient_type", "individual",
                "to", phone,
                "type", "template",
                "template", Map.of(
                        "name", "alarms",
                        "language", Map.of("code", "en"),
                        "components", List.of(Map.of(
                                "type", "BODY",
                                "parameters", List.of(
                                        templateText("severity", severity),
                                        templateText("type", type),
                                        templateText("start_at", startAt(startTs)))))));

        String endpoint = "https://graph.facebook.com/"
                + whatsappVersion + "/" + providerPhoneNumberId + "/messages";
        try {
            HttpRequest request = HttpRequest.newBuilder(URI.create(endpoint))
                    .header("Authorization", "Bearer " + token)
                    .header("Content-Type", MediaType.APPLICATION_JSON)
                    .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(payload)))
                    .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new InternalServerErrorException(
                        "Could not reach sms provider. Status: " + response.statusCode());
            }
            LOG.infof("WhatsApp notification sent to %s: %d", phone, response.statusCode());
        } catch (IOException e) {
            LOG.error("Could not reach sms provider", e);
            throw new InternalServerErrorException("Could not reach sms provider. " + e.getMessage(), e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new InternalServerErrorException("Could not reach sms provider. Request interrupted", e);
        }
    }

    private Map<String, String> templateText(String name, String value) {
        return Map.of(
                "parameter_name", name,
                "type", "text",
                "text", value);
    }

    private String startAt(Long startTs) {
        return LocalDateTime.ofInstant(Instant.ofEpochMilli(startTs), ZoneId.systemDefault())
                .format(START_AT_FORMATTER);
    }

    private NotifyStatusResponse status(String status) {
        NotifyStatusResponse response = new NotifyStatusResponse();
        response.setStatus(status);
        return response;
    }

    private String string(Object value) {
        return value == null ? null : value.toString();
    }
}
