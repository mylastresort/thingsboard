import groovy.scenario.DeviceProfileBuilder

// Devices with profile: big-robot (7 devices)
return [
    new DeviceProfileBuilder()
        .type('big-robot')
        .label('Building 1')
        .with {
            name = 'D4 N2'
            // relation: ASSET 'building_1' [Contains]
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'noise'
                metric('noise') { min 70.0; max 90.0 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('big-robot')
        .label('Building 1')
        .with {
            name = 'D4 N3'
            // relation: ASSET 'building_1' [Contains]
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'noise'
                metric('noise') { min 70.0; max 90.0 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('big-robot')
        .label('Building 1')
        .with {
            name = 'D4 N4'
            // relation: ASSET 'building_1' [Contains]
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'noise'
                metric('noise') { min 70.0; max 90.0 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('big-robot')
        .label('Building 1')
        .with {
            name = 'D4 N1'
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'noise'
                metric('noise') { min 70.0; max 90.0 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('big-robot')
        .label('Building 2')
        .with {
            name = '7Y81'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('big-robot')
        .label('Building 2')
        .with {
            name = '82H2'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('big-robot')
        .label('Building 2')
        .with {
            name = '9Z15'
            // TODO: add telemetry config
            build()
        },
]
