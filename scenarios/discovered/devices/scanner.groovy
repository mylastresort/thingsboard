import groovy.scenario.DeviceProfileBuilder

// Devices with profile: scanner (4 devices)
return [
    new DeviceProfileBuilder()
        .type('scanner')
        .label('Building 2')
        .with {
            name = 'J529'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('scanner')
        .label('Building 1')
        .with {
            name = 'D2 T2'
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'temperature'
                metric('temperature') { min 70.0; max 80.0 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('scanner')
        .label('Building 1')
        .with {
            name = 'D2 T1'
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'temperature'
                metric('temperature') { min 70.0; max 80.0 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('scanner')
        .label('Building 1')
        .with {
            name = 'D2 T3'
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'temperature'
                metric('temperature') { min 70.0; max 80.0 }
            }
            build()
        },
]
