
import simplefoc.commander as commander
from simplefoc import TorqueControlType
from simplefoc import MotionControlType
import time, sys, signal

MOTOR_ID = 'M'
TARGET_VOLTAGE = 5

motors = commander.serial('/dev/tty.usbmodem1441101', 115200)
motor = motors.full_control(MOTOR_ID)

motor.listen(print)
motors.connect()

motor.set_limits(max_voltage=6.0, max_current=1.0, max_velocity=20.0)
motor.set_mode(MotionControlType.velocity_openloop, TorqueControlType.voltage)
motor.enable()

def signalhandler(signum, other):
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
    time.sleep(3.0)
    motor.set_target(0.0)
    time.sleep(1.0)
    motor.set_target(-TARGET_VOLTAGE)
    time.sleep(3.0)
    motor.set_target(0.0)
    time.sleep(1.0)
