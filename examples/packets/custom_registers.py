
import simplefoc.packets as packets
from simplefoc.registers import SimpleFOCRegisters

# lets add a custom register, just for fun - a temperature sensor
SimpleFOCRegisters.add_register(name='REG_TEMPERATURE', id=0xE0, read_types=['f'], write_types=[])
# And another one, we can write this one too, the alert level for the temperature sensor
SimpleFOCRegisters.add_register('REG_TEMPERATURE_ALERT', 0xE1, ['f'], ['f'])
# Registers can return more than one value, e.g. the temperatures for the last 10s
SimpleFOCRegisters.add_register('REG_TEMPERATURE_TREND', 0xE2, ['f','f','f','f','f','f','f','f','f','f'])

motors = packets.connect_serial('COM6', 115200)

motors.start_comms_thread() # TODO finalize method name

result = motors.get_register(0, SimpleFOCRegisters.REG_TEMPERATURE_SENSOR1, 5.0)

if result is None:
    print('No response received.')
else:
    print('Temperature: ', result)

motors.disconnect()