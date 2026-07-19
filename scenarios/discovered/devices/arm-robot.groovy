import groovy.scenario.DeviceProfileBuilder

// Devices with profile: arm-robot (12 devices)
return [
    new DeviceProfileBuilder()
        .type('arm-robot')
        .label('Building 1')
        .with {
            name = 'D5 P7'
            // relation: ASSET 'building_1' [Contains]
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'pressure'
                metric('pressure') { min 0.2625; max 0.7875 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('arm-robot')
        .label('Building 2')
        .with {
            name = 'D18UP'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('arm-robot')
        .label('Building 1')
        .with {
            name = 'D5 P2'
            // relation: ASSET 'building_1' [Contains]
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'pressure'
                metric('pressure') { min 0.2625; max 0.7875 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('arm-robot')
        .label('Building 1')
        .with {
            name = 'D5 P3'
            // relation: ASSET 'building_1' [Contains]
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'pressure'
                metric('pressure') { min 0.2625; max 0.7875 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('arm-robot')
        .label('Building 1')
        .with {
            name = 'D5 P4'
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'pressure'
                metric('pressure') { min 0.2625; max 0.7875 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('arm-robot')
        .label('Building 1')
        .with {
            name = 'D5 P5'
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'pressure'
                metric('pressure') { min 0.2625; max 0.7875 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('arm-robot')
        .label('Building 1')
        .with {
            name = 'D5 P6'
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'pressure'
                metric('pressure') { min 0.2625; max 0.7875 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('arm-robot')
        .label('Building 2')
        .with {
            name = 'L129'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('arm-robot')
        .label('Building 1')
        .with {
            name = 'D5 P1'
            telemetry {
                mode 'stream'
                source 'random'
                interval_ms 2000
                metrics 'pressure'
                metric('pressure') { min 0.2625; max 0.7875 }
            }
            build()
        },
    new DeviceProfileBuilder()
        .type('arm-robot')
        .label('Building 2')
        .with {
            name = '1K75'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('arm-robot')
        .label('Building 2')
        .with {
            name = '5V09'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('arm-robot')
        .label('Building 2')
        .with {
            name = '844Z'
            // TODO: add telemetry config
            build()
        },
]
