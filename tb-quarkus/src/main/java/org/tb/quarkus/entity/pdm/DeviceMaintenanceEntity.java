package org.tb.quarkus.entity.pdm;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
import java.time.Instant;

@Entity
@Table(name = "device_maintenance", schema = "tb_quarkus_pdm")
public class DeviceMaintenanceEntity extends FailureRecordBaseEntity {
    public String maintenanceType;
    public Instant maintenanceDate;
    public Double durationHours;
    public Double cost;
    public String technician;
    @Column(columnDefinition = "TEXT")
    public String description;
    public String partsReplaced;
    @JdbcTypeCode(SqlTypes.JSON)
    public JsonNode actionsPerformed;
    public Instant nextMaintenanceDate;
}