
import simplefoc.packets as packets
from simplefoc import TorqueControlType
from simplefoc import MotionControlType
import time, sys, signal

MOTOR_ID = 0
TARGET_VOLTAGE = 0.5

motors = packets.serial('/dev/tty.pci-serial22', 115200)
motor = motors.use(MOTOR_ID)

motor.listen(lambda p: print(p))

motors.connect()

motor.set_limits(max_voltage=12.0, max_current=1.0, max_velocity=20.0)
motor.set_mode(MotionControlType.torque, TorqueControlType.voltage)

def signalhandler(signum):
    print("Disabling motor...")
    motor.set_target(0.0)
    time.sleep(1.0)
    motor.disable()
    motors.disconnect()
    print("Serial port closed.")
    sys.exit(0)

signal.signal(signal.SIGINT, signalhandler)

while True:
    motor.set_target(TARGET_VOLTAGE)
    time.sleep(10.0)
    motor.set_target(0.0)
    time.sleep(1.0)
    motor.set_target(-TARGET_VOLTAGE)
    time.sleep(10.0)
    motor.set_target(0.0)
    time.sleep(1.0)


