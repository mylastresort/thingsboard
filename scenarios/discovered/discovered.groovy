import groovy.lang.GroovyShell

// ── Scenario metadata ─────────────────────────────────────────
def scenario = [
    name       : 'discovered',
    description: 'Auto-discovered from ThingsBoard (89 devices, 24 assets)',
    version    : 1,
]

// ── Device groups (by profile) ─────────────────────────────────
def devices = []
def shell = new GroovyShell()

new File(scenarioDir, 'devices/arm-robot.groovy').with { if (exists()) devices.addAll(shell.evaluate(it)) }
new File(scenarioDir, 'devices/big-robot.groovy').with { if (exists()) devices.addAll(shell.evaluate(it)) }
new File(scenarioDir, 'devices/conveyor.groovy').with { if (exists()) devices.addAll(shell.evaluate(it)) }
new File(scenarioDir, 'devices/pdm-model2.groovy').with { if (exists()) devices.addAll(shell.evaluate(it)) }
new File(scenarioDir, 'devices/pdm-model3.groovy').with { if (exists()) devices.addAll(shell.evaluate(it)) }
new File(scenarioDir, 'devices/scanner.groovy').with { if (exists()) devices.addAll(shell.evaluate(it)) }
new File(scenarioDir, 'devices/sensor.groovy').with { if (exists()) devices.addAll(shell.evaluate(it)) }
new File(scenarioDir, 'devices/small-robot.groovy').with { if (exists()) devices.addAll(shell.evaluate(it)) }

// ── Asset groups (by type) ──────────────────────────────────────
def assets = []

new File(scenarioDir, 'assets/ahu.groovy').with { if (exists()) assets.addAll(shell.evaluate(it)) }
new File(scenarioDir, 'assets/aob_benchmark.groovy').with { if (exists()) assets.addAll(shell.evaluate(it)) }
new File(scenarioDir, 'assets/building_1.groovy').with { if (exists()) assets.addAll(shell.evaluate(it)) }
new File(scenarioDir, 'assets/building_2.groovy').with { if (exists()) assets.addAll(shell.evaluate(it)) }
new File(scenarioDir, 'assets/building_3.groovy').with { if (exists()) assets.addAll(shell.evaluate(it)) }
new File(scenarioDir, 'assets/camera.groovy').with { if (exists()) assets.addAll(shell.evaluate(it)) }
new File(scenarioDir, 'assets/chiller.groovy').with { if (exists()) assets.addAll(shell.evaluate(it)) }
new File(scenarioDir, 'assets/compressor.groovy').with { if (exists()) assets.addAll(shell.evaluate(it)) }
new File(scenarioDir, 'assets/pump.groovy').with { if (exists()) assets.addAll(shell.evaluate(it)) }

return [scenario: scenario, devices: devices, assets: assets]
