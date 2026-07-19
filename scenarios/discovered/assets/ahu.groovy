import groovy.scenario.AssetProfileBuilder

// Assets with type: Ahu (1 assets)
return [
    new AssetProfileBuilder()
        .type('Ahu')
        .label('AHU')
        .with {
            name = 'AHU'
            relation('DEVICE', 'AHU - Supply Air Temp', 'Contains')
            relation('DEVICE', 'AHU - Return Air Temp', 'Contains')
            relation('DEVICE', 'AHU - Filter Pressure Drop', 'Contains')
            relation('DEVICE', 'AHU - Heating Coil Valve', 'Contains')
            relation('DEVICE', 'AHU - Fan Speed', 'Contains')
            relation('DEVICE', 'AHU - Damper Position', 'Contains')
            relation('DEVICE', 'AHU - Cooling Coil Valve', 'Contains')
            build()
        },
]
