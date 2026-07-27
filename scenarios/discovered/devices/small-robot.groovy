import groovy.scenario.DeviceProfileBuilder

// Devices with profile: small-robot (9 devices)
return [
    new DeviceProfileBuilder()
        .type('small-robot')
        .label('Building 2')
        .with {
            name = 'C422'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('small-robot')
        .label('Building 2')
        .with {
            name = 'X900'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('small-robot')
        .label('Building 2')
        .with {
            name = 'E704'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('small-robot')
        .label('Building 2')
        .with {
            name = '9A55'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('small-robot')
        .label('Building 1')
        .with {
            name = 'D3 L1'
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'level'
                metric('level') { min 65.0; max 75.0 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('small-robot')
        .label('Building 1')
        .with {
            name = 'D3 L2'
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'level'
                metric('level') { min 65.0; max 75.0 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('small-robot')
        .label('Building 1')
        .with {
            name = 'D3 L3'
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'level'
                metric('level') { min 65.0; max 75.0 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('small-robot')
        .label('Building 1')
        .with {
            name = 'D3 L4'
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'level'
                metric('level') { min 65.0; max 75.0 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('small-robot')
        .label('Building 2')
        .with {
            name = 'F934'
            // TODO: add telemetry config
            build()
        },
]
