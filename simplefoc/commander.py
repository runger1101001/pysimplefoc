
from enum import Enum
import serial as ser
from rx.subject import Subject
from rx import operators as ops
from .registers import SimpleFOCRegisters as regs


MonitoringFlags = {
    regs.REG_TARGET.id : 0b1000000,
    regs.REG_VOLTAGE_Q.id : 0b0100000,
    regs.REG_VOLTAGE_D.id : 0b0010000,
    regs.REG_CURRENT_Q.id : 0b0001000,
    regs.REG_CURRENT_D.id : 0b0000100,
    regs.REG_VELOCITY.id : 0b0000010,
    regs.REG_ANGLE.id  : 0b0000001 
}




def serial(port, baud):
    """ Create a Commander instance using a serial port connection.
        Note that the connection is not opened until the connect() method is called on the Commander instance.
    """
    ser_conn = ser.Serial()
    ser_conn.port = port
    ser_conn.baudrate = baud
    return Commander(ser_conn)



class Commander:
    """ Commander is the central class for controlling SimpleFOC devices via the commander text based protocol.

        Use it to obtain a FullControl instance for each motor you want to control.

        Monitoring is supported for up to one motor, using the usual SimpleFOC monitoring registers.
    """
    def __init__(self, connection):
        self.connection = connection
        self._subject = Subject()
        self._observable = self._subject.pipe(
            ops.share()
        )
        self._echosubject = Subject()
        self._echo = self._echosubject.pipe(
            ops.share()
        )
        self._in_sync = False
        self.monitor_downsample = 0

    def full_control(self, motor_letter):
        return FullControl(self, motor_letter)

    def send_command(self, command):
        self.connection.writelines([command.encode('ascii'), '\n'.encode('ascii')])
        self._echosubject.on_next(command)

    def scalar(self, letter, value):
        self.send_command(letter + str(value))

    def motion(self, letter, target, torque_limit=None, velocity_limit=None):
        if velocity_limit!=None and torque_limit==None:
            raise ValueError("Velocity limit cannot be set without torque limit")
        cmdstr = letter + 'M' + str(target)
        if velocity_limit!=None: cmdstr += ' ' + str(velocity_limit)
        if torque_limit!=None: cmdstr += ' ' + str(torque_limit)

    def pid(self, letter, p=None, i=None, d=None, ramp=None, limit=None):
        if p!=None: self.send_command(letter + 'P' + str(p))
        if i!=None: self.send_command(letter + 'I' + str(i))
        if d!=None: self.send_command(letter + 'D' + str(d))
        if ramp!=None: self.send_command(letter + 'R' + str(ramp))
        if limit!=None: self.send_command(letter + 'L' + str(limit))

    def filter(self, letter, value):
        self.send_command(letter + 'F' + str(value))

    def target(self, letter, value):
        self.scalar(letter, value)

    def listen(self, callback):
        self._observable.subscribe(callback)

    def observable(self):
        return self._observable

    def connect(self):
        self.connection.open()

    def disconnect(self):
        self.connection.close()
    
    def echo(self):
        return self._echo

    def console(self):
        return self.observable().pipe(
            ops.merge(self.echo())
        )
    


class FullControl:
    def __init__(self, commander, motor_letter):
        self.commander = commander
        self.letter = motor_letter

    def set_target(self, target):
        self.commander.send_command(self.letter + str(target))

    def set_mode(self, motion_control_type, torque_control_type):
        # todo check types
        self.commander.send_command(self.letter + 'C' + str(motion_control_type.value))
        self.commander.send_command(self.letter + 'T' + str(torque_control_type.value))

    def set_limits(self, max_voltage:float=None, max_current:float=None, max_velocity:float=None, max_angle:float=None, min_angle:float=None):
        if (max_voltage!=None): self.commander.send_command(self.letter + 'LU' + str(max_voltage))
        if (max_current!=None): self.commander.send_command(self.letter + 'LC' + str(max_current))
        if (max_velocity!=None): self.commander.send_command(self.letter + 'LV' + str(max_velocity))
        # todo add max and min angle limits to SimpleFOC
        #self.commander.send_command(self.letter + '' + str(max_angle))
        #self.commander.send_command(self.letter + '' + str(min_angle))

    def disable(self):
        self.enable(False)

    def enable(self, enable=True):
        cmd = self.letter + 'E' + ('1' if enable else '0')
        self.commander.send_command(cmd)

    def listen(self, callback):
        self.commander.listen(callback)

    def telemetry(self):
        pass

    def set_monitoring(self, registers):
        regval = 0
        for reg in registers:
            if reg.id in MonitoringFlags:
                regval |= MonitoringFlags[reg.id]
        self.commander.send_command(self.letter + 'MS' + str(regval))

    def start_monitoring(self, downsample=100):
        self.commander.send_command(self.letter + 'MD' + str(downsample))

    def stop_monitoring(self):
        self.start_monitoring(0)