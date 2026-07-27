import groovy.scenario.AssetProfileBuilder

// Assets with type: AOB_Benchmark (1 assets)
return [
    new AssetProfileBuilder()
        .type('AOB_Benchmark')
        .label('AssetOpsBench scenario fixtures')
        .with {
            name = 'AOB_Benchmark_Scenarios'
            build()
        },
]
