import groovy.scenario.AssetProfileBuilder

// Assets with type: building 3 (1 assets)
return [
    new AssetProfileBuilder()
        .type('building 3')
        .label('building_3')
        .with {
            name = 'building_3'
            build()
        },
]
