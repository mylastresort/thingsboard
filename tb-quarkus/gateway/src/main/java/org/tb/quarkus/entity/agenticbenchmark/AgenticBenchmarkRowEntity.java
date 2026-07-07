package org.tb.quarkus.entity.agenticbenchmark;

import com.fasterxml.jackson.databind.JsonNode;
import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.util.UUID;

@Entity
@Table(name = "agentic_benchmark_rows", schema = "tb_quarkus_agentic_benchmark")
public class AgenticBenchmarkRowEntity extends PanacheEntityBase {
    @Id
    @GeneratedValue
    public UUID id;

    public String subsetName;

    @Column(columnDefinition = "TEXT")
    public String sourceFile;

    public Long datasetRecordId;

    @Column(columnDefinition = "TEXT")
    public String subject;

    @Column(columnDefinition = "TEXT")
    public String question;

    @JdbcTypeCode(SqlTypes.JSON)
    public JsonNode options;

    @JdbcTypeCode(SqlTypes.JSON)
    public JsonNode optionIds;

    @JdbcTypeCode(SqlTypes.JSON)
    public JsonNode correct;

    public String textType;

    @Column(columnDefinition = "TEXT")
    public String assetName;

    @Column(columnDefinition = "TEXT")
    public String relevancy;

    @Column(columnDefinition = "TEXT")
    public String questionType;

    @Column(columnDefinition = "TEXT")
    public String triggerStatement;

    @Column(columnDefinition = "TEXT")
    public String context;

    @JdbcTypeCode(SqlTypes.JSON)
    public JsonNode rawPayload;

    public Long createdTime;
    public Long updatedTime;

    @PrePersist
    public void prePersist() {
        var now = System.currentTimeMillis();
        if (createdTime == null) {
            createdTime = now;
        }
        if (updatedTime == null) {
            updatedTime = now;
        }
    }

    @PreUpdate
    public void preUpdate() {
        updatedTime = System.currentTimeMillis();
    }
}
