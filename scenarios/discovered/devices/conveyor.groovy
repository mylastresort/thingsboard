import groovy.scenario.DeviceProfileBuilder

// Devices with profile: conveyor (1 devices)
return [
    new DeviceProfileBuilder()
        .type('conveyor')
        .label('Building 1')
        .with {
            name = 'Conveyor'
            // TODO: add telemetry config
            build()
        },
]
