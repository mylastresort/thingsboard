import groovy.scenario.AssetProfileBuilder

// Assets with type: camera (4 assets)
return [
    new AssetProfileBuilder()
        .type('camera')
        .label('building_1')
        .with {
            name = 'cam3'
            build()
        },
    new AssetProfileBuilder()
        .type('camera')
        .label('building_2')
        .with {
            name = 'cam4'
            build()
        },
    new AssetProfileBuilder()
        .type('camera')
        .label('builidng_1')
        .with {
            name = 'cam1'
            build()
        },
    new AssetProfileBuilder()
        .type('camera')
        .label('building_1')
        .with {
            name = 'cam2'
            build()
        },
]
