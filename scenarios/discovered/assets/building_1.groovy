import groovy.scenario.AssetProfileBuilder

// Assets with type: building 1 (9 assets)
return [
    new AssetProfileBuilder()
        .type('building 1')
        .with {
            name = 'Simulation'
            build()
        },
    new AssetProfileBuilder()
        .type('building 1')
        .label('contact')
        .with {
            name = 'Contact'
            build()
        },
    new AssetProfileBuilder()
        .type('building 1')
        .label('building 1')
        .with {
            name = 'building_1'
            relation('DEVICE', 'Conveyor', 'Contains')
            relation('DEVICE', 'D2 T1', 'Contains')
            relation('DEVICE', 'D2 T2', 'Contains')
            relation('DEVICE', 'D2 T3', 'Contains')
            relation('DEVICE', 'D3 L1', 'Contains')
            relation('DEVICE', 'D3 L2', 'Contains')
            relation('DEVICE', 'D3 L3', 'Contains')
            relation('DEVICE', 'D3 L4', 'Contains')
            relation('DEVICE', 'D4 N1', 'Contains')
            relation('DEVICE', 'D4 N4', 'Contains')
            relation('DEVICE', 'D5 P1', 'Contains')
            relation('DEVICE', 'D5 P2', 'Contains')
            relation('DEVICE', 'D5 P3', 'Contains')
            relation('DEVICE', 'D5 P4', 'Contains')
            relation('DEVICE', 'D5 P5', 'Contains')
            relation('DEVICE', 'D5 P6', 'Contains')
            relation('ASSET', 'cam3', 'Contains')
            relation('ASSET', 'cam1', 'Contains')
            relation('ASSET', 'cam2', 'Contains')
            relation('ASSET', 'Contact', 'Contains')
            relation('DEVICE', 'D4 N3', 'Contains')
            relation('DEVICE', 'D4 N2', 'Contains')
            relation('DEVICE', 'D5 P7', 'Contains')
            build()
        },
    new AssetProfileBuilder()
        .type('building 1')
        .label('temperature')
        .with {
            name = 'Temperature'
            relation('DEVICE', 'D2 T1', 'Contains')
            relation('DEVICE', 'D2 T2', 'Contains')
            relation('DEVICE', 'D2 T3', 'Contains')
            build()
        },
    new AssetProfileBuilder()
        .type('building 1')
        .with {
            name = 'Rotate'
            build()
        },
    new AssetProfileBuilder()
        .type('building 1')
        .label('vibration')
        .with {
            name = 'Vibration'
            relation('DEVICE', 'Conveyor', 'Contains')
            build()
        },
    new AssetProfileBuilder()
        .type('building 1')
        .label('pressure')
        .with {
            name = 'Pressure'
            relation('DEVICE', 'D5 P6', 'Contains')
            relation('DEVICE', 'D5 P2', 'Contains')
            relation('DEVICE', 'D5 P3', 'Contains')
            relation('DEVICE', 'D5 P1', 'Contains')
            relation('DEVICE', 'D5 P4', 'Contains')
            relation('DEVICE', 'D5 P5', 'Contains')
            build()
        },
    new AssetProfileBuilder()
        .type('building 1')
        .label('level')
        .with {
            name = 'Level'
            relation('DEVICE', 'D3 L4', 'Contains')
            relation('DEVICE', 'D3 L1', 'Contains')
            relation('DEVICE', 'D3 L2', 'Contains')
            relation('DEVICE', 'D3 L3', 'Contains')
            build()
        },
    new AssetProfileBuilder()
        .type('building 1')
        .label('noise')
        .with {
            name = 'Noise'
            relation('DEVICE', 'D4 N2', 'Contains')
            relation('DEVICE', 'D4 N3', 'Contains')
            relation('DEVICE', 'D4 N4', 'Contains')
            relation('DEVICE', 'D4 N1', 'Contains')
            build()
        },
]
