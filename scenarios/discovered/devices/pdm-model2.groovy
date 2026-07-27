import groovy.scenario.DeviceProfileBuilder

// Devices with profile: PdM-model2 (2 devices)
return [
    new DeviceProfileBuilder()
        .type('PdM-model2')
        .label('')
        .with {
            name = 'rerw'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('PdM-model2')
        .label('Predictive Maintenance Machine 11')
        .with {
            name = 'PdM-Machine-11'
            // relation: ASSET 'building_1' [Contains]
            // TODO: add telemetry config
            build()
        },
]
