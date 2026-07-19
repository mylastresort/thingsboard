package org.tb.quarkus.scenario.model;

import java.util.ArrayList;
import java.util.List;

public class Asset {
    private String name;
    private String type;
    private String label;
    private final List<Device.Relation> relations = new ArrayList<>();

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

    public List<Device.Relation> getRelations() {
        return relations;
    }

    public void addRelation(Device.Relation relation) {
        this.relations.add(relation);
    }
}
