package org.tb.quarkus.entity.pdm;

import com.fasterxml.jackson.databind.JsonNode;
import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "predictions", schema = "tb_quarkus_pdm")
public class PredictionEntity extends PanacheEntityBase {

    @Id
    @GeneratedValue
    public UUID id;

    public UUID modelId;
    public Long createdTime;
    public Instant createdAt;
    public Instant predictionTime;
    public String predictionType;

    @JdbcTypeCode(SqlTypes.JSON)
    public JsonNode predictionValue;

    @PrePersist
    public void prePersist() {
        if (createdAt == null) {
            createdAt = Instant.now();
        }
        if (predictionTime == null) {
            predictionTime = Instant.now();
        }
    }
}
