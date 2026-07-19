import groovy.scenario.DeviceProfileBuilder

// Devices with profile: sensor (53 devices)
return [
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Power Input')
        .with {
            name = 'Chiller - Power Input'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Tonnage')
        .with {
            name = 'Chiller - Tonnage'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Condenser Water Flow')
        .with {
            name = 'Chiller - Condenser Water Flow'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Chilled Water Flow')
        .with {
            name = 'Chiller - Chilled Water Flow'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Return Temp')
        .with {
            name = 'Chiller - Return Temp'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Supply Temp')
        .with {
            name = 'Chiller - Supply Temp'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Condenser Pressure')
        .with {
            name = 'Chiller - Condenser Pressure'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Evaporator Pressure')
        .with {
            name = 'Chiller - Evaporator Pressure'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Supply Air Temp')
        .with {
            name = 'AHU - Supply Air Temp'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Return Air Temp')
        .with {
            name = 'AHU - Return Air Temp'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Fan Speed')
        .with {
            name = 'AHU - Fan Speed'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Damper Position')
        .with {
            name = 'AHU - Damper Position'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Filter Pressure Drop')
        .with {
            name = 'AHU - Filter Pressure Drop'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Cooling Coil Valve')
        .with {
            name = 'AHU - Cooling Coil Valve'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Heating Coil Valve')
        .with {
            name = 'AHU - Heating Coil Valve'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Discharge Pressure')
        .with {
            name = 'compressor - Discharge Pressure'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Suction Pressure')
        .with {
            name = 'compressor - Suction Pressure'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Bearing Temp')
        .with {
            name = 'compressor - Bearing Temp'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Vibration RMS')
        .with {
            name = 'compressor - Vibration RMS'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Motor Current')
        .with {
            name = 'compressor - Motor Current'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Oil Pressure')
        .with {
            name = 'compressor - Oil Pressure'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Discharge Pressure')
        .with {
            name = 'industrial gas turbine - Discharge Pressure'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Suction Pressure')
        .with {
            name = 'industrial gas turbine - Suction Pressure'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Bearing Temp')
        .with {
            name = 'industrial gas turbine - Bearing Temp'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Vibration RMS')
        .with {
            name = 'industrial gas turbine - Vibration RMS'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Motor Current')
        .with {
            name = 'industrial gas turbine - Motor Current'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Oil Pressure')
        .with {
            name = 'industrial gas turbine - Oil Pressure'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Flow Rate')
        .with {
            name = 'pump - Flow Rate'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Discharge Pressure')
        .with {
            name = 'pump - Discharge Pressure'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Suction Pressure')
        .with {
            name = 'pump - Suction Pressure'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Motor Current')
        .with {
            name = 'pump - Motor Current'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Bearing Temp')
        .with {
            name = 'pump - Bearing Temp'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Vibration RMS')
        .with {
            name = 'pump - Vibration RMS'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Flow Rate')
        .with {
            name = 'hydrolic_pump - Flow Rate'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Discharge Pressure')
        .with {
            name = 'hydrolic_pump - Discharge Pressure'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Suction Pressure')
        .with {
            name = 'hydrolic_pump - Suction Pressure'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Motor Current')
        .with {
            name = 'hydrolic_pump - Motor Current'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Bearing Temp')
        .with {
            name = 'hydrolic_pump - Bearing Temp'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Vibration RMS')
        .with {
            name = 'hydrolic_pump - Vibration RMS'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Power Input')
        .with {
            name = 'Cooling Tower - Power Input'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Tonnage')
        .with {
            name = 'Cooling Tower - Tonnage'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Condenser Water Flow')
        .with {
            name = 'Cooling Tower - Condenser Water Flow'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Chilled Water Flow')
        .with {
            name = 'Cooling Tower - Chilled Water Flow'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Return Temp')
        .with {
            name = 'Cooling Tower - Return Temp'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Supply Temp')
        .with {
            name = 'Cooling Tower - Supply Temp'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Condenser Pressure')
        .with {
            name = 'Cooling Tower - Condenser Pressure'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Evaporator Pressure')
        .with {
            name = 'Cooling Tower - Evaporator Pressure'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Flow Rate')
        .with {
            name = 'Pump - Flow Rate'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Discharge Pressure')
        .with {
            name = 'Pump - Discharge Pressure'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Suction Pressure')
        .with {
            name = 'Pump - Suction Pressure'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Motor Current')
        .with {
            name = 'Pump - Motor Current'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Bearing Temp')
        .with {
            name = 'Pump - Bearing Temp'
            // TODO: add telemetry config
            build()
        },
    new DeviceProfileBuilder()
        .type('sensor')
        .label('Vibration RMS')
        .with {
            name = 'Pump - Vibration RMS'
            // TODO: add telemetry config
            build()
        },
]
