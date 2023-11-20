from enum import Enum


class TorqueControlType(Enum):
  voltage            = 0x00
  dc_current         = 0x01
  foc_current        = 0x02


class MotionControlType(Enum):
  torque            = 0x00
  velocity          = 0x01
  angle             = 0x02
  velocity_openloop = 0x03
  angle_openloop    = 0x04


class FOCModulationType(Enum):
  SinePWM            = 0x00
  SpaceVectorPWM     = 0x01
  Trapezoid_120      = 0x02
  Trapezoid_150      = 0x03


class FOCMotorStatus(Enum):
  motor_uninitialized = 0x00
  motor_initializing  = 0x01
  motor_uncalibrated  = 0x02
  motor_calibrating   = 0x03
  motor_ready         = 0x04
  motor_error         = 0x08
  motor_calib_failed  = 0x0E
  motor_init_failed   = 0x0F


class FrameType(Enum):
    REGISTER = 'R'
    RESPONSE = 'r'
    TELEMETRY = 'T'
    HEADER = 'H'
    SYNC = 'S'
    ALERT = 'A'



class Frame(object):
    def __init__(self, frame_type, register=None, values=None, alert=None, registers=None, telemetryid=None, motor_id=None, header=None, timestamp=None):
        self.frame_type = frame_type
        self.register = register
        self.values = values
        self.alert = alert
        self.registers = registers
        self.telemetryid = telemetryid
        self.motor_id = motor_id
        self.header = header
        self.timestamp = timestamp

    def __repr__(self): # TODO prettify this output
        return self.__dict__.__str__()
