import groovy.scenario.AssetProfileBuilder

// Assets with type: Chiller (2 assets)
return [
    new AssetProfileBuilder()
        .type('Chiller')
        .label('Chiller')
        .with {
            name = 'Chiller'
            relation('DEVICE', 'Chiller - Power Input', 'Contains')
            relation('DEVICE', 'Chiller - Tonnage', 'Contains')
            relation('DEVICE', 'Chiller - Chilled Water Flow', 'Contains')
            relation('DEVICE', 'Chiller - Supply Temp', 'Contains')
            relation('DEVICE', 'Chiller - Condenser Pressure', 'Contains')
            relation('DEVICE', 'Chiller - Condenser Water Flow', 'Contains')
            relation('DEVICE', 'Chiller - Return Temp', 'Contains')
            relation('DEVICE', 'Chiller - Evaporator Pressure', 'Contains')
            build()
        },
    new AssetProfileBuilder()
        .type('Chiller')
        .label('Cooling Tower')
        .with {
            name = 'Cooling Tower'
            relation('DEVICE', 'Cooling Tower - Power Input', 'Contains')
            relation('DEVICE', 'Cooling Tower - Tonnage', 'Contains')
            relation('DEVICE', 'Cooling Tower - Condenser Water Flow', 'Contains')
            relation('DEVICE', 'Cooling Tower - Supply Temp', 'Contains')
            relation('DEVICE', 'Cooling Tower - Chilled Water Flow', 'Contains')
            relation('DEVICE', 'Cooling Tower - Return Temp', 'Contains')
            relation('DEVICE', 'Cooling Tower - Condenser Pressure', 'Contains')
            relation('DEVICE', 'Cooling Tower - Evaporator Pressure', 'Contains')
            build()
        },
]
