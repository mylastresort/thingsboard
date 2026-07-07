package org.tb.quarkus.entity.pdm;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
import java.time.Instant;

@Entity
@Table(name = "device_failures", schema = "tb_quarkus_pdm")
public class DeviceFailureEntity extends FailureRecordBaseEntity {
    public Instant failureTime;
    public Instant detectionTime;
    public Instant resolvedTime;
    public String failureType;
    public String failureSeverity;
    @Column(columnDefinition = "TEXT")
    public String failureDescription;
    public String rootCause;
    public Double downtimeHours;
    public Double repairCost;
    @JdbcTypeCode(SqlTypes.JSON)
    public JsonNode replacedParts;
    @JdbcTypeCode(SqlTypes.JSON)
    public JsonNode maintenanceActions;
    public Boolean wasPredicted;
    public Double predictionLeadTimeHours;
}