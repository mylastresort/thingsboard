package org.tb.quarkus.scenario.model;

import java.util.ArrayList;
import java.util.List;

public class Scenario {
    private String name;
    private String description;
    private int version;
    private final List<Device> devices = new ArrayList<>();
    private final List<Asset> assets = new ArrayList<>();

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public int getVersion() {
        return version;
    }

    public void setVersion(int version) {
        this.version = version;
    }

    public List<Device> getDevices() {
        return devices;
    }

    public List<Asset> getAssets() {
        return assets;
    }
}
