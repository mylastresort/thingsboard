import groovy.scenario.AssetProfileBuilder

// Assets with type: building 2 (1 assets)
return [
    new AssetProfileBuilder()
        .type('building 2')
        .label('building_2')
        .with {
            name = 'building_2'
            relation('DEVICE', 'D18UP', 'Contains')
            relation('ASSET', 'cam4', 'Contains')
            relation('DEVICE', '1K75', 'Contains')
            relation('DEVICE', 'C422', 'Contains')
            relation('DEVICE', '9Z15', 'Contains')
            relation('DEVICE', '5V09', 'Contains')
            relation('DEVICE', '82H2', 'Contains')
            relation('DEVICE', '7Y81', 'Contains')
            relation('DEVICE', 'F934', 'Contains')
            relation('DEVICE', '844Z', 'Contains')
            relation('DEVICE', '9A55', 'Contains')
            relation('DEVICE', 'E704', 'Contains')
            relation('DEVICE', 'J529', 'Contains')
            relation('DEVICE', 'X900', 'Contains')
            relation('DEVICE', 'L129', 'Contains')
            build()
        },
]
