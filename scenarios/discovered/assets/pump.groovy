import groovy.scenario.AssetProfileBuilder

// Assets with type: Pump (3 assets)
return [
    new AssetProfileBuilder()
        .type('Pump')
        .label('pump')
        .with {
            name = 'pump'
            relation('DEVICE', 'pump - Flow Rate', 'Contains')
            relation('DEVICE', 'pump - Discharge Pressure', 'Contains')
            relation('DEVICE', 'pump - Motor Current', 'Contains')
            relation('DEVICE', 'pump - Vibration RMS', 'Contains')
            relation('DEVICE', 'pump - Suction Pressure', 'Contains')
            relation('DEVICE', 'pump - Bearing Temp', 'Contains')
            build()
        },
    new AssetProfileBuilder()
        .type('Pump')
        .label('hydrolic_pump')
        .with {
            name = 'hydrolic_pump'
            relation('DEVICE', 'hydrolic_pump - Flow Rate', 'Contains')
            relation('DEVICE', 'hydrolic_pump - Discharge Pressure', 'Contains')
            relation('DEVICE', 'hydrolic_pump - Suction Pressure', 'Contains')
            relation('DEVICE', 'hydrolic_pump - Motor Current', 'Contains')
            relation('DEVICE', 'hydrolic_pump - Vibration RMS', 'Contains')
            relation('DEVICE', 'hydrolic_pump - Bearing Temp', 'Contains')
            build()
        },
    new AssetProfileBuilder()
        .type('Pump')
        .label('Pump')
        .with {
            name = 'Pump'
            relation('DEVICE', 'Pump - Flow Rate', 'Contains')
            relation('DEVICE', 'Pump - Suction Pressure', 'Contains')
            relation('DEVICE', 'Pump - Motor Current', 'Contains')
            relation('DEVICE', 'Pump - Discharge Pressure', 'Contains')
            relation('DEVICE', 'Pump - Bearing Temp', 'Contains')
            relation('DEVICE', 'Pump - Vibration RMS', 'Contains')
            build()
        },
]
