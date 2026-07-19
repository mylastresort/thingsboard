package org.tb.quarkus.scenario.model;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class Device {
    private String name;
    private String type;
    private String label;
    private String deviceProfileName;
    private final Map<String, Object> attributes = new LinkedHashMap<>();
    private Telemetry telemetry;
    private final List<Relation> relations = new ArrayList<>();

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    public String getLabel() {
        return label;
    }

    public void setLabel(String label) {
        this.label = label;
    }

    public String getDeviceProfileName() {
        return deviceProfileName;
    }

    public void setDeviceProfileName(String deviceProfileName) {
        this.deviceProfileName = deviceProfileName;
    }

    public Map<String, Object> getAttributes() {
        return attributes;
    }

    public Telemetry getTelemetry() {
        return telemetry;
    }

    public void setTelemetry(Telemetry telemetry) {
        this.telemetry = telemetry;
    }

    public List<Relation> getRelations() {
        return relations;
    }

    public void addRelation(Relation relation) {
        this.relations.add(relation);
    }

    public static class Relation {
        private String entityType;
        private String entityId;
        private String entityName;
        private String type;

        public Relation() {
        }

        public Relation(String entityType, String entityId, String entityName, String type) {
            this.entityType = entityType;
            this.entityId = entityId;
            this.entityName = entityName;
            this.type = type;
        }

        public String getEntityType() {
            return entityType;
        }

        public void setEntityType(String entityType) {
            this.entityType = entityType;
        }

        public String getEntityId() {
            return entityId;
        }

        public void setEntityId(String entityId) {
            this.entityId = entityId;
        }

        public String getEntityName() {
            return entityName;
        }

        public void setEntityName(String entityName) {
            this.entityName = entityName;
        }

        public String getType() {
            return type;
        }

        public void setType(String type) {
            this.type = type;
        }
    }
}
