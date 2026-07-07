package org.tb.quarkus.entity.pdm;

import com.fasterxml.jackson.databind.JsonNode;
import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.Column;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.PrePersist;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.UUID;

@MappedSuperclass
public abstract class FailureRecordBaseEntity extends PanacheEntityBase {
    @Id @GeneratedValue
    public UUID id;

    @Column(name = "device_id")
    public UUID deviceId;

    @JdbcTypeCode(SqlTypes.JSON)
    public JsonNode metadata;

    @Column(name = "created_time")
    public Long createdTime;

    @Column(name = "created_at")
    public Instant createdAt;

    @PrePersist
    public void prePersist() {
        if (createdTime == null) {
            createdTime = System.currentTimeMillis();
        }
        if (createdAt == null) {
            createdAt = Instant.now();
        }
    }
}
