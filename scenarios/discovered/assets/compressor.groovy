import groovy.scenario.AssetProfileBuilder

// Assets with type: Compressor (2 assets)
return [
    new AssetProfileBuilder()
        .type('Compressor')
        .label('compressor')
        .with {
            name = 'compressor'
            relation('DEVICE', 'compressor - Discharge Pressure', 'Contains')
            relation('DEVICE', 'compressor - Vibration RMS', 'Contains')
            relation('DEVICE', 'compressor - Motor Current', 'Contains')
            relation('DEVICE', 'compressor - Oil Pressure', 'Contains')
            relation('DEVICE', 'compressor - Suction Pressure', 'Contains')
            relation('DEVICE', 'compressor - Bearing Temp', 'Contains')
            build()
        },
    new AssetProfileBuilder()
        .type('Compressor')
        .label('industrial gas turbine')
        .with {
            name = 'industrial gas turbine'
            relation('DEVICE', 'industrial gas turbine - Discharge Pressure', 'Contains')
            relation('DEVICE', 'industrial gas turbine - Suction Pressure', 'Contains')
            relation('DEVICE', 'industrial gas turbine - Bearing Temp', 'Contains')
            relation('DEVICE', 'industrial gas turbine - Vibration RMS', 'Contains')
            relation('DEVICE', 'industrial gas turbine - Motor Current', 'Contains')
            relation('DEVICE', 'industrial gas turbine - Oil Pressure', 'Contains')
            build()
        },
]
