package org.tb.quarkus.entity.pdm;

import com.fasterxml.jackson.databind.JsonNode;
import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.util.UUID;

@Entity
@Table(name = "predictive_model_load_model_config", schema = "tb_quarkus_pdm")
public class PredictiveModelLoadModelConfigEntity extends PanacheEntityBase {

    @Id
    @GeneratedValue
    public UUID id;

    public String name;

    @JdbcTypeCode(SqlTypes.JSON)
    public JsonNode config;
}
