package org.tb.quarkus.entity.pdm;

import com.fasterxml.jackson.databind.JsonNode;
import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.util.UUID;

@Entity
@Table(name = "predictive_maintenance_config", schema = "tb_quarkus_pdm")
public class PredictiveMaintenanceConfigEntity extends PanacheEntityBase {

    @Id
    public UUID id;

    @Column(name = "tenant_id")
    public UUID tenantId;

    @Column(name = "device_id")
    public UUID deviceId;

    @Column(name = "created_time")
    public Long createdTime;

    public String name;

    @JdbcTypeCode(SqlTypes.JSON)
    public JsonNode attributes;

    public String forecastAlgorithm;
    public Long forecastStartDate;
    public Long forecastEndDate;
    public String anomalyAlgorithm;
    public Long anomalyStartDate;
    public Long anomalyEndDate;

    @JdbcTypeCode(SqlTypes.JSON)
    public JsonNode viewPreferences;

    @JdbcTypeCode(SqlTypes.JSON)
    public JsonNode additionalData;

    @PrePersist
    public void prePersist() {
        if (id == null) {
            id = UUID.randomUUID();
        }
        if (createdTime == null) {
            createdTime = System.currentTimeMillis();
        }
        if (forecastAlgorithm == null) {
            forecastAlgorithm = "ARIMA";
        }
        if (forecastStartDate == null) {
            forecastStartDate = 0L;
        }
        if (forecastEndDate == null) {
            forecastEndDate = 0L;
        }
        if (anomalyAlgorithm == null) {
            anomalyAlgorithm = "THRESHOLD";
        }
        if (anomalyStartDate == null) {
            anomalyStartDate = 0L;
        }
        if (anomalyEndDate == null) {
            anomalyEndDate = 0L;
        }
    }
}
