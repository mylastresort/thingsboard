import groovy.scenario.DeviceProfileBuilder

// Devices with profile: PdM-model3 (1 devices)
return [
    new DeviceProfileBuilder()
        .type('PdM-model3')
        .label('Predictive Maintenance Machine 1')
        .with {
            name = 'PdM-Machine-1'
            // relation: ASSET 'building_1' [Contains]
            telemetry {
                mode 'stream'
                source 'csv'
                file 'PdM_telemetry_MachineID1.csv'
                interval_ms 2000
                loop true
                metrics 'volt', 'rotate', 'pressure', 'vibration'
            }
            build()
        },
]
