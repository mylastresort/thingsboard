package org.tb.quarkus.entity.core;

import com.fasterxml.jackson.databind.JsonNode;
import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.util.UUID;

@Entity
@Table(name = "claim", schema = "tb_quarkus")
public class ClaimEntity extends PanacheEntityBase {

    @Id
    @GeneratedValue
    public UUID id;

    @Column(name = "tenant_id")
    public UUID tenantId;

    @Column(name = "created_time")
    public Long createdTime;

    public String body;

    public boolean done;

    public String name;

    @Column(name = "assignee_id")
    public UUID assigneeId;

    @JdbcTypeCode(SqlTypes.JSON)
    public JsonNode tags;
}