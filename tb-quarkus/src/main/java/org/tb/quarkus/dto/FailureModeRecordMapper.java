package org.tb.quarkus.dto;

import org.tb.quarkus.entity.pdm.*;
import org.tb.quarkus.model.FailureModeRecord;
import org.tb.quarkus.model.FailureModeRecordResponse;

import java.time.Instant;
import java.util.UUID;

public final class FailureModeRecordMapper {

    private FailureModeRecordMapper() {}

    public static Object toEntity(FailureModeRecord r) {
        UUID deviceId = UUID.fromString(r.getDeviceId());
        Instant ts = r.getDatetime().toInstant();
        return switch (r.getType()) {
            case "error" -> {
                var e = new DeviceErrorEntity();
                e.deviceId = deviceId;
                e.errorTime = ts;
                e.errorDescription = r.getDescription();
                e.errorCode = defaultString(r.getErrorCode(), "UNKNOWN");
                yield e;
            }
            case "maintenance" -> {
                var e = new DeviceMaintenanceEntity();
                e.deviceId = deviceId;
                e.maintenanceDate = ts;
                e.maintenanceType = "maintenance";
                e.description = r.getDescription();
                e.partsReplaced = defaultString(r.getPartsReplaced(), "");
                yield e;
            }
            case "failure" -> {
                var e = new DeviceFailureEntity();
                e.deviceId = deviceId;
                e.failureTime = ts;
                e.failureType = "failure";
                e.failureDescription = r.getDescription();
                e.rootCause = defaultString(r.getRootCause(), "UNKNOWN");
                yield e;
            }
            default -> throw new IllegalArgumentException("Unknown record type: " + r.getType());
        };
    }

    public static FailureModeRecordResponse toResponse(Object entity) {
        var resp = new FailureModeRecordResponse();
        if (entity instanceof DeviceErrorEntity e) {
            resp.setId(e.id.toString());
            resp.setDeviceId(e.deviceId.toString());
            resp.setDatetime(e.errorTime != null ? e.errorTime.toString() : null);
            resp.setDescription(e.errorDescription);
            resp.setErrorCode(e.errorCode);
        } else if (entity instanceof DeviceMaintenanceEntity e) {
            resp.setId(e.id.toString());
            resp.setDeviceId(e.deviceId.toString());
            resp.setDatetime(e.maintenanceDate != null ? e.maintenanceDate.toString() : null);
            resp.setDescription(e.description);
            resp.setPartsReplaced(e.partsReplaced);
        } else if (entity instanceof DeviceFailureEntity e) {
            resp.setId(e.id.toString());
            resp.setDeviceId(e.deviceId.toString());
            resp.setDatetime(e.failureTime != null ? e.failureTime.toString() : null);
            resp.setDescription(e.failureDescription);
            resp.setRootCause(e.rootCause);
        }
        return resp;
    }

    private static String defaultString(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value;
    }
}
