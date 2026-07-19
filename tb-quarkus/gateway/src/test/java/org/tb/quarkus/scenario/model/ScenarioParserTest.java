package org.tb.quarkus.scenario.model;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ScenarioParserTest {

    private final ScenarioParser parser = new ScenarioParser();

    @Test
    void parseSimpleGroovy() throws Exception {
        String groovy = """
                def scenario = [name: 'test', description: 'A test scenario', version: 1]
                def devices = []

                devices << new groovy.scenario.DeviceProfileBuilder()
                    .type('DEFAULT')
                    .label('Test Sensor')
                    .with {
                        name = 'Sensor-1'
                        telemetry {
                            source('random')
                            intervalMs(3000)
                            metric('temperature') { min(20); max(35) }
                        }
                        build()
                    }

                return [scenario: scenario, devices: devices]
                """;

        Scenario scenario = parser.parseGroovy(groovy);

        assertEquals("test", scenario.getName());
        assertEquals("A test scenario", scenario.getDescription());
        assertEquals(1, scenario.getVersion());
        assertEquals(1, scenario.getDevices().size());

        Device device = scenario.getDevices().get(0);
        assertEquals("Sensor-1", device.getName());
        assertEquals("DEFAULT", device.getType());
        assertEquals("Test Sensor", device.getLabel());

        Telemetry tel = device.getTelemetry();
        assertNotNull(tel);
        assertEquals("stream", tel.getMode());
        assertEquals("random", tel.getSource());
        assertEquals(3000, tel.getIntervalMs());
        assertTrue(tel.getMetrics().contains("temperature"));
        assertEquals(20.0, tel.getMetricRanges().get("temperature").getMin());
        assertEquals(35.0, tel.getMetricRanges().get("temperature").getMax());
    }

    @Test
    void parseMultipleDevices() throws Exception {
        String groovy = """
                def scenario = [name: 'multi', version: 1]
                def devices = []

                devices << new groovy.scenario.DeviceProfileBuilder()
                    .type('DEFAULT')
                    .with {
                        name = 'D1'
                        telemetry {
                            source('random')
                            metric('temp') { min(0); max(100) }
                        }
                        build()
                    }

                devices << new groovy.scenario.DeviceProfileBuilder()
                    .type('DEFAULT')
                    .with {
                        name = 'D2'
                        telemetry {
                            mode('load')
                            source('csv')
                            file('data.csv')
                            metrics('pressure')
                        }
                        build()
                    }

                return [scenario: scenario, devices: devices]
                """;

        Scenario scenario = parser.parseGroovy(groovy);

        assertEquals("multi", scenario.getName());
        assertEquals(2, scenario.getDevices().size());
        assertEquals("D1", scenario.getDevices().get(0).getName());
        assertEquals("D2", scenario.getDevices().get(1).getName());
        assertEquals("stream", scenario.getDevices().get(0).getTelemetry().getMode());
        assertEquals("load", scenario.getDevices().get(1).getTelemetry().getMode());
    }

    @Test
    void deviceRelations() {
        Device device = new Device();
        device.setName("Sensor-1");
        device.setType("DEFAULT");

        device.addRelation(new Device.Relation("ASSET", "asset-123", "Building A", "Contains"));
        device.addRelation(new Device.Relation("DEVICE", "device-456", "Gateway-1", "ConnectedTo"));

        assertEquals(2, device.getRelations().size());
        assertEquals("ASSET", device.getRelations().get(0).getEntityType());
        assertEquals("Building A", device.getRelations().get(0).getEntityName());
        assertEquals("Contains", device.getRelations().get(0).getType());
        assertEquals("DEVICE", device.getRelations().get(1).getEntityType());
    }

    @Test
    void parseAssets() throws Exception {
        String groovy = """
                def scenario = [name: 'with-assets', version: 1]
                def devices = []
                def assets = []

                devices << new groovy.scenario.DeviceProfileBuilder()
                    .type('DEFAULT')
                    .with {
                        name = 'Sensor-1'
                        telemetry {
                            source('random')
                            metric('temp') { min(0); max(100) }
                        }
                        build()
                    }

                assets << new groovy.scenario.AssetProfileBuilder()
                    .type('building')
                    .with {
                        name = 'Building A'
                        relation('DEVICE', 'Sensor-1', 'Contains')
                        build()
                    }

                return [scenario: scenario, devices: devices, assets: assets]
                """;

        Scenario scenario = parser.parseGroovy(groovy);

        assertEquals("with-assets", scenario.getName());
        assertEquals(1, scenario.getDevices().size());
        assertEquals(1, scenario.getAssets().size());

        Asset asset = scenario.getAssets().get(0);
        assertEquals("Building A", asset.getName());
        assertEquals("building", asset.getType());
        assertEquals(1, asset.getRelations().size());
        assertEquals("DEVICE", asset.getRelations().get(0).getEntityType());
        assertEquals("Sensor-1", asset.getRelations().get(0).getEntityName());
        assertEquals("Contains", asset.getRelations().get(0).getType());
    }
}
