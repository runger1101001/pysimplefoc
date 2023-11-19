#
# Functions and classes to help with SimpleFOC telenetry output
#

from rx import operators as ops
from .registers import SimpleFOCRegisters
from simplefoc import FrameType


MAX_TELEMTRY_IDS = 8


class Telemetry:
    """ SimpleFOC Telemetry class

        Used to configure and start/stop telemetry output from the driver.

        Typically, you will get a Telemetry instance by calling motors.telemetry()

        
    """
    def __init__(self, motors):
        self.motors = motors
        self.motors.connection.observable().pipe(
            ops.filter(lambda p: p.frame_type == FrameType.HEADER)
        ).subscribe(self.__update_header)
        self.header = [ None ] * MAX_TELEMTRY_IDS
        self._telemetry = self.motors.connection.observable().pipe(
            ops.filter(lambda p: p.frame_type == FrameType.TELEMETRY),
            ops.filter(lambda p: self.headers[p.telemetryid] is not None),
            ops.map(lambda p: self.connection.parse_telemetry(p, self.headers[p.telemetryid])),
            ops.share()
        )

    def set_registers(self, registers, motors=None, telemetryid=0):
        if motors is None:
            motors = [0] * len(registers)
        if len(registers) != len(motors):
            raise Exception("registers and motors must be the same length")
        self.motors.set_register(0, SimpleFOCRegisters.REG_TELEMETRY_REG, telemetryid, registers, motors)

#    def set_period(self, period=0.25):
#        pass # todo implement period as a register?

    def set_downsample(self, downsample=100):
        self.motors.set_register(0, SimpleFOCRegisters.REG_TELEMETRY_DOWNSAMPLE, downsample)

    def start(self):
        self.motors.set_register(0, SimpleFOCRegisters.REG_TELEMETRY_CTRL, 1)

    def stop(self):
        self.motors.set_register(0, SimpleFOCRegisters.REG_TELEMETRY_CTRL, 0)

    def header(self, telemetryid=0):
        return self.headers[telemetryid]
    
    def fetch_headers(self):
        self.motors.get_register(0, SimpleFOCRegisters.REG_TELEMETRY_REG)

    #
    # Get an observable of the telemetry data
    #
    def observable(self):
        return self._telemetry
    
    def listen(self, listener_func):
        self.observable().subscribe(listener_func)

    def __update_header(self, packet):
        self.header[packet.telemetryid] = packet
