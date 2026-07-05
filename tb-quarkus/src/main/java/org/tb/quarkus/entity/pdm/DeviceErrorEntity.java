package org.tb.quarkus.entity.pdm;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "device_errors", schema = "tb_quarkus_pdm")
public class DeviceErrorEntity extends FailureRecordBaseEntity {
    public Instant errorTime;
    public String errorCode;
    public String errorType;
    public String errorSeverity;
    @Column(columnDefinition = "TEXT")
    public String errorDescription;
    public String component;
    public Instant recoveryTime;
    public Boolean wasAutoRecovered;
    public Boolean ledToFailure;
}