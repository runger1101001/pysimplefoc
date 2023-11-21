
import time, re, threading, math, serial as ser
from rx.subject import Subject
from rx import operators as ops
from .registers import SimpleFOCRegisters as regs
from simplefoc import Frame, FrameType

MonitoringFlags = {
    regs.REG_TARGET.id : int('1000000',2),
    regs.REG_VOLTAGE_Q.id : int('0100000',2),
    regs.REG_VOLTAGE_D.id : int('0010000',2),
    regs.REG_CURRENT_Q.id : int('0001000',2),
    regs.REG_CURRENT_D.id : int('0000100',2),
    regs.REG_VELOCITY.id : int('0000010',2),
    regs.REG_ANGLE.id  : int('0000001',2)
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
            ops.filter(lambda x: not self.__is_monitoring_data(x)),
            ops.share()
        )
        self._monitoring_header = None
        self._telemetry = self._subject.pipe(
            ops.filter(lambda x: self._monitoring_header is not None),
            ops.filter(lambda x: self.__is_monitoring_data(x)),
            ops.map(lambda x: self.__parse_monitoring_data(x)),
            ops.filter(lambda x: x is not None),
            ops.share()
        )
        self._echosubject = Subject()
        self._echo = self._echosubject.pipe(
            ops.share()
        )
        self._in_sync = False
        self.monitor_downsample = 0
        self.is_running = False

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
        self.is_running = True
        self._read_thread = threading.Thread(target=self.__run)
        self._read_thread.start()

    def disconnect(self):
        self.is_running = False
        self._read_thread.join()
        self.connection.close()
    
    def echo(self):
        return self._echo

    def console(self):
        return self.observable().pipe(
            ops.merge(self.echo())
        )

    def telemetry(self):
        return self._telemetry
    
    def use_monitoring_registers(self, registers):
        regval = 0
        for reg in registers:
            if reg.id in MonitoringFlags:
                regval |= MonitoringFlags[reg.id]
        header = Frame(frame_type=FrameType.HEADER, registers=[], telemetryid=0)
        for reg in [regs.REG_TARGET, regs.REG_VOLTAGE_Q, regs.REG_VOLTAGE_D, regs.REG_CURRENT_Q, regs.REG_CURRENT_D, regs.REG_VELOCITY, regs.REG_ANGLE]:
            if regval & MonitoringFlags[reg.id] != 0:
                header.registers.append(reg)
        self._monitoring_header = header if len(header.registers) > 0 else None
    
    def __is_monitoring_data(self, line:str):
        return re.match(r'[0-9-]', line)

    def __parse_monitoring_data(self, line:str):
        t = Frame(frame_type=FrameType.TELEMETRY, telemetryid=0, header=self._monitoring_header, values=[float(f) for f in line.split(',')], timestamp=time.time())
        if len(t.values) != len(t.header.registers):
            return None
        return t

    def __run(self):
        while self.is_running:
            if self.connection.in_waiting > 0:
                self.__processLine()
            else:
                time.sleep(0.001)

    def __processLine(self):
        line = self.connection.readline()
        if line is not None:
            line = line.decode('ascii').strip()
            if len(line) > 0:
                self._subject.on_next(line)




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

    def set_motor_parameters(self, resistance:float=None, kv:float=None, inductance:float=None):
        if kv != None: self.commander.send_command(self.letter + 'K' + str(kv))
        if resistance != None: self.commander.send_command(self.letter + 'R' + str(resistance))
        if inductance != None: self.commander.send_command(self.letter + 'I' + str(inductance))

    def set_velocity_pid(self, p:float = None, i:float = None, d:float = None, limit:float = None, ramp:float = None, tf:float = None):
        if p != None: self.commander.send_command(self.letter + 'VP' + str(p))
        if i != None: self.commander.send_command(self.letter + 'VI' + str(i))
        if d != None: self.commVnder.send_command(self.letter + 'VD' + str(d))
        if limit != None: self.Vommander.send_command(self.letter + 'VL' + str(limit))
        if ramp != None: self.commaVder.send_command(self.letter + 'VR' + str(ramp))
        if tf != None: self.commanVer.send_command(self.letter + 'VF' + str(tf))

    def set_angle_pid(self, p:float = None, i:float = None, d:float = None, limit:float = None, ramp:float = None, tf:float = None):
        if p != None: self.commander.send_command(self.letter + 'AP' + str(p))
        if i != None: self.commander.send_command(self.letter + 'AI' + str(i))
        if d != None: self.commander.send_command(self.letter + 'AD' + str(d))
        if limit != None: self.commander.send_command(self.letter + 'AL' + str(limit))
        if ramp != None: self.commander.send_command(self.letter + 'AR' + str(ramp))
        if tf != None: self.commander.send_command(self.letter + 'AF' + str(tf))

    def set_current_q_pid(self, p:float = None, i:float = None, d:float = None, limit:float = None, ramp:float = None, tf:float = None):
        if p != None: self.commander.send_command(self.letter + 'QP' + str(p))
        if i != None: self.commander.send_command(self.letter + 'QI' + str(i))
        if d != None: self.commander.send_command(self.letter + 'QD' + str(d))
        if limit != None: self.commander.send_command(self.letter + 'QL' + str(limit))
        if ramp != None: self.commander.send_command(self.letter + 'QR' + str(ramp))
        if tf != None: self.commander.send_command(self.letter + 'QF' + str(tf))

    def set_current_p_pid(self, p:float = None, i:float = None, d:float = None, limit:float = None, ramp:float = None, tf:float = None):
        if p != None: self.commander.send_command(self.letter + 'DP' + str(p))
        if i != None: self.commander.send_command(self.letter + 'DI' + str(i))
        if d != None: self.commander.send_command(self.letter + 'DD' + str(d))
        if limit != None: self.commander.send_command(self.letter + 'DL' + str(limit))
        if ramp != None: self.commander.send_command(self.letter + 'DR' + str(ramp))
        if tf != None: self.commander.send_command(self.letter + 'DF' + str(tf))

    def set_sensor_offsets(self, offset:float=None, zero_electrical_angle:float=None):
        if offset != None: self.commander.send_command(self.letter + 'SM' + str(offset))
        if zero_electrical_angle != None: self.commander.send_command(self.letter + 'SE' + str(zero_electrical_angle))

    def disable(self):
        self.enable(False)

    def enable(self, enable=True):
        cmd = self.letter + 'E' + ('1' if enable else '0')
        self.commander.send_command(cmd)

    def listen(self, callback):
        self.commander.listen(callback)

    def telemetry(self):
        return self.commander.telemetry()

    def set_monitoring(self, registers):
        regval = 0
        for reg in registers:
            if reg.id in MonitoringFlags:
                regval |= MonitoringFlags[reg.id]
        self.commander.send_command(self.letter + 'MS' + bin(regval)[2:].zfill(7))
        self.commander.use_monitoring_registers(registers)

    def get_monitoring(self, register):
        if register.id in MonitoringFlags:
            num = 6 - int(math.log2(MonitoringFlags[register.id]))
            self.commander.send_command(self.letter + 'MG' + str(num))

    def start_monitoring(self, downsample=100):
        self.commander.send_command(self.letter + 'MD' + str(downsample))

    def stop_monitoring(self):
        self.start_monitoring(0)