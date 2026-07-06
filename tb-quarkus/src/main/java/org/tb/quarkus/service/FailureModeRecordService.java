package org.tb.quarkus.service;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import io.quarkus.panache.common.Sort;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.transaction.Transactional;
import org.tb.quarkus.entity.pdm.*;
import org.tb.quarkus.dto.FailureModeRecordMapper;
import org.tb.quarkus.model.*; 
import jakarta.ws.rs.NotFoundException;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

@ApplicationScoped
public class FailureModeRecordService {

    @Transactional
    public FailureModeRecordResponse create(FailureModeRecord record) {
        record.setType(normalizeRecordType(record.getType()));
        Object entity = FailureModeRecordMapper.toEntity(record);
        ((PanacheEntityBase) entity).persist();
        return FailureModeRecordMapper.toResponse(entity);
    }

    @Transactional
    public CreateFailureModeRecordsResponse createBatch(List<FailureModeRecord> records) {
        var responses = new ArrayList<FailureModeRecordResponse>();
        for (var r : records) responses.add(create(r));
        var resp = new CreateFailureModeRecordsResponse();
        resp.setRecords(responses);
        resp.setCreatedCount(responses.size());
        return resp;
    }

    @Transactional
    public ImportFailureModeRecordsResponse importCsv(InputStream body, String recordType) {
        var resp = new ImportFailureModeRecordsResponse();
        var errors = new ArrayList<ImportError>();
        int imported = 0;

        try (var reader = new BufferedReader(new InputStreamReader(body, StandardCharsets.UTF_8))) {
            String headerLine = reader.readLine();
            if (headerLine == null || headerLine.isBlank()) {
                resp.setImportedCount(0);
                resp.setErrors(List.of(new ImportError().row(1).message("CSV is empty")));
                return resp;
            }

            List<String> headers = parseCsvLine(headerLine);
            String line;
            int rowNumber = 1;
            while ((line = reader.readLine()) != null) {
                rowNumber++;
                if (line.isBlank()) {
                    continue;
                }
                try {
                    Map<String, String> row = toRow(headers, parseCsvLine(line));
                    var record = new FailureModeRecord();
                    record.setType(normalizeRecordType(firstNonBlank(row.get("type"), recordType)));
                    record.setDeviceId(firstNonBlank(row.get("device_id"), row.get("deviceId")));
                    record.setDatetime(parseDate(firstNonBlank(row.get("datetime"), row.get("date"), row.get("timestamp"))));
                    record.setDescription(row.get("description"));
                    record.setPartsReplaced(firstNonBlank(row.get("parts_replaced"), row.get("partsReplaced")));
                    record.setErrorCode(firstNonBlank(row.get("error_code"), row.get("errorCode")));
                    record.setRootCause(firstNonBlank(row.get("root_cause"), row.get("rootCause")));
                    create(record);
                    imported++;
                } catch (Exception e) {
                    errors.add(new ImportError().row(rowNumber).message(e.getMessage()));
                }
            }
        } catch (Exception e) {
            errors.add(new ImportError().row(1).message(e.getMessage()));
        }

        resp.setImportedCount(imported);
        resp.setErrors(errors);
        return resp;
    }

    @Transactional
    public FailureModeRecordResponse update(String recordType, UUID id, FailureModeRecord record) {
        record.setType(normalizeRecordType(firstNonBlank(record.getType(), recordType)));
        UUID deviceId = UUID.fromString(record.getDeviceId());
        Instant ts = record.getDatetime().toInstant();

        Object entity = switch (normalizeRecordType(recordType)) {
            case "error" -> {
                DeviceErrorEntity e = DeviceErrorEntity.findById(id);
                if (e == null) {
                    throw new NotFoundException("Failure mode error record not found");
                }
                e.deviceId = deviceId;
                e.errorTime = ts;
                e.errorDescription = record.getDescription();
                e.errorCode = defaultString(record.getErrorCode(), "UNKNOWN");
                yield e;
            }
            case "maintenance" -> {
                DeviceMaintenanceEntity e = DeviceMaintenanceEntity.findById(id);
                if (e == null) {
                    throw new NotFoundException("Failure mode maintenance record not found");
                }
                e.deviceId = deviceId;
                e.maintenanceDate = ts;
                e.maintenanceType = "maintenance";
                e.description = record.getDescription();
                e.partsReplaced = defaultString(record.getPartsReplaced(), "");
                yield e;
            }
            case "failure" -> {
                DeviceFailureEntity e = DeviceFailureEntity.findById(id);
                if (e == null) {
                    throw new NotFoundException("Failure mode failure record not found");
                }
                e.deviceId = deviceId;
                e.failureTime = ts;
                e.failureType = "failure";
                e.failureDescription = record.getDescription();
                e.rootCause = defaultString(record.getRootCause(), "UNKNOWN");
                yield e;
            }
            default -> throw new IllegalArgumentException("Unknown record type: " + recordType);
        };

        return FailureModeRecordMapper.toResponse(entity);
    }

    @Transactional
    public DeleteFailureModeRecordResponse delete(String recordType, UUID id) {
        boolean deleted = switch (normalizeRecordType(recordType)) {
            case "error" -> DeviceErrorEntity.deleteById(id);
            case "maintenance" -> DeviceMaintenanceEntity.deleteById(id);
            case "failure" -> DeviceFailureEntity.deleteById(id);
            default -> throw new IllegalArgumentException("Unknown record type: " + recordType);
        };
        var resp = new DeleteFailureModeRecordResponse();
        resp.setDeletedCount(deleted ? 1 : 0);
        return resp;
    }

    public FailureModeHistoryResponse getHistory(UUID deviceId, Long startTs, Long endTs, Integer limit) {
        var resp = new FailureModeHistoryResponse();
        resp.setDeviceId(deviceId != null ? deviceId.toString() : null);
        resp.setErrors(queryErrors(deviceId, startTs, endTs, limit).stream()
                .map(FailureModeRecordMapper::toResponse).toList());
        resp.setMaintenance(queryMaintenance(deviceId, startTs, endTs, limit).stream()
                .map(FailureModeRecordMapper::toResponse).toList());
        resp.setFailures(queryFailures(deviceId, startTs, endTs, limit).stream()
                .map(FailureModeRecordMapper::toResponse).toList());
        return resp;
    }

    public FailureModeHistoryResponse getHistoryForModel(String modelId, Long startTs, Long endTs) {
        var modelUuid = UUID.fromString(modelId);
        PredictiveMaintenanceConfigEntity config = PredictiveMaintenanceConfigEntity.findById(modelUuid);
        var deviceId = config != null ? config.deviceId : modelUuid;
        if (deviceId == null) {
            throw new NotFoundException("Forecast device not found");
        }

        var resp = getHistory(deviceId, startTs, endTs, null);
        resp.setModelId(modelId);
        return resp;
    }

    private static List<DeviceErrorEntity> queryErrors(UUID deviceId, Long startTs, Long endTs, Integer limit) {
        var query = buildTimeQuery("errorTime", deviceId, startTs, endTs);
        var sort = Sort.descending("errorTime");
        return limited(query.isEmpty()
                ? DeviceErrorEntity.<DeviceErrorEntity>findAll(sort)
                : DeviceErrorEntity.<DeviceErrorEntity>find(query.query(), sort, query.params()), limit);
    }

    private static List<DeviceMaintenanceEntity> queryMaintenance(UUID deviceId, Long startTs, Long endTs, Integer limit) {
        var query = buildTimeQuery("maintenanceDate", deviceId, startTs, endTs);
        var sort = Sort.descending("maintenanceDate");
        return limited(query.isEmpty()
                ? DeviceMaintenanceEntity.<DeviceMaintenanceEntity>findAll(sort)
                : DeviceMaintenanceEntity.<DeviceMaintenanceEntity>find(query.query(), sort, query.params()), limit);
    }

    private static List<DeviceFailureEntity> queryFailures(UUID deviceId, Long startTs, Long endTs, Integer limit) {
        var query = buildTimeQuery("failureTime", deviceId, startTs, endTs);
        var sort = Sort.descending("failureTime");
        return limited(query.isEmpty()
                ? DeviceFailureEntity.<DeviceFailureEntity>findAll(sort)
                : DeviceFailureEntity.<DeviceFailureEntity>find(query.query(), sort, query.params()), limit);
    }

    private static QueryParts buildTimeQuery(String timeField, UUID deviceId, Long startTs, Long endTs) {
        var clauses = new ArrayList<String>();
        var params = new ArrayList<Object>();
        if (deviceId != null) {
            params.add(deviceId);
            clauses.add("deviceId = ?" + params.size());
        }
        if (startTs != null) {
            params.add(Instant.ofEpochMilli(startTs));
            clauses.add(timeField + " >= ?" + params.size());
        }
        if (endTs != null) {
            params.add(Instant.ofEpochMilli(endTs));
            clauses.add(timeField + " <= ?" + params.size());
        }
        return new QueryParts(clauses.isEmpty() ? "" : String.join(" and ", clauses), params.toArray());
    }

    private static <T> List<T> limited(io.quarkus.hibernate.orm.panache.PanacheQuery<T> query, Integer limit) {
        if (limit != null && limit > 0) {
            query.range(0, limit - 1);
        }
        return query.list();
    }

    private record QueryParts(String query, Object[] params) {
        boolean isEmpty() {
            return query.isEmpty();
        }
    }

    private static Map<String, String> toRow(List<String> headers, List<String> values) {
        var row = new LinkedHashMap<String, String>();
        for (int i = 0; i < headers.size(); i++) {
            row.put(headers.get(i), i < values.size() ? values.get(i) : null);
        }
        return row;
    }

    private static List<String> parseCsvLine(String line) {
        var values = new ArrayList<String>();
        var current = new StringBuilder();
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
                values.add(current.toString().trim());
                current.setLength(0);
            } else {
                current.append(ch);
            }
        }
        values.add(current.toString().trim());
        return values;
    }

    private static String normalizeRecordType(String type) {
        if (type == null || type.isBlank()) {
            throw new IllegalArgumentException("record type is required");
        }
        return switch (type.toLowerCase(Locale.ROOT)) {
            case "errors", "error" -> "error";
            case "maintenance" -> "maintenance";
            case "failures", "failure" -> "failure";
            default -> throw new IllegalArgumentException("Unknown record type: " + type);
        };
    }

    private static String defaultString(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value;
    }

    private static Date parseDate(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("datetime is required");
        }
        try {
            return Date.from(Instant.parse(value));
        } catch (DateTimeParseException e) {
            return new Date(Long.parseLong(value));
        }
    }

    private static String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return null;
    }
}
