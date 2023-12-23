#
# Interact with SimpleFOC using a stream of packets/frames, and deal with the variables/commands using a "register" abstraction
#
# For use with SimpleFOC BinaryComms or ASCIIComms.
# Not for use with SimpleFOC Commander (see commander.py for that one).
#

from enum import Enum
from .registers import parse_register, Register, SimpleFOCRegisters
import serial as ser
import time, struct, threading
from .motors import Motors
from rx.subject import Subject
from rx import operators as ops
from simplefoc import Frame, FrameType



class ProtocolType(Enum):
    binary = 0
    ascii = 1

MARKER = 0xA5



def serial(port, baud, protocol=ProtocolType.binary):
    ser_conn = ser.Serial()
    ser_conn.port = port
    ser_conn.baudrate = baud
    comms = None
    if protocol == ProtocolType.binary:
        comms = BinaryComms(ser_conn)
    elif protocol == ProtocolType.ascii:
        comms = ASCIIComms(ser_conn)
    else:
        raise ValueError("Unknown protocol type")
    return Motors(comms)


def parse_value(valuestr):
    if valuestr.startswith('0x'):
        return int(valuestr, 16)
    if valuestr.startswith('0b'):
        return int(valuestr, 2)
    if valuestr.endswith('f') or valuestr.endswith('F') or valuestr.find('.')>=0:
        return float(valuestr)
    return int(valuestr)    


def parse_register_and_values(command:str):
    regstr, valuesstr = command.split('=')[0:2]
    reg = parse_register(regstr)
    values = [parse_value(v) for v in valuesstr.split(',')]
    return reg, values




class Comms(object):
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
        self.is_running = False

    def disconnect(self):
        if self.is_running:
            self.is_running = False
            self._read_thread.join()
        self.connection.close()
        self._subject.on_completed()

    def connect(self):
        self.connection.open()
        self.is_running = True
        self._read_thread = threading.Thread(target=self.__run)
        self._read_thread.start()

    def get_frame(self):
        raise NotImplementedError()

    def get_frame_blocking(self, timeout=0.0):
        frame = None
        timestamp = time.time()
        while frame is None and (timeout <= 0.0 or time.time() - timestamp < timeout):
            frame = self.get_frame()
        return frame
    
    def observable(self):
        return self._observable

    def echo(self):
        return self._echo

    def __run(self):
        while self.is_running:
            if self.connection.in_waiting > 0:
                f = self.get_frame()
                if f is not None:
                    self._subject.on_next(f)
            else:
                time.sleep(0.001)




class ASCIIComms(Comms):
    def __init__(self, connection):
        super().__init__(connection)
        self._buffer = ''

    def get_frame(self):
        while self.connection.in_waiting > 0:
            character = self.connection.read().decode('ascii')
            if character == '\n':
                if self._in_sync:
                    frame = self.__parseFrame(self._buffer)
                    self._buffer = ''
                    return frame
                else:
                    self._buffer = ''
                    self._in_sync = True
                    self.send_frame(Frame(frame_type=FrameType.SYNC))
            elif character == '\r':
                pass
            else:
                self._buffer += character
        return None

    def send_frame(self, frame):
        framestr = ""
        match frame.frame_type:
            case FrameType.REGISTER:
                framestr += 'R'
                framestr += str(frame.register.id)
                if frame.values is not None and len(frame.values) > 0:
                    framestr += '='
                    framestr += ','.join([str(v) for v in frame.values])
            case FrameType.SYNC:
                framestr += 'S'
                framestr += '1' if self._in_sync else '0'
            case FrameType.ALERT:
                framestr += 'A'
                framestr += str(frame.alert)
            case FrameType.RESPONSE:
                framestr += 'r'
                framestr += str(frame.register)
                framestr += '='
                framestr += ','.join([str(v) for v in frame.values])
            case FrameType.TELEMETRY:
                framestr += 'T'
                framestr += str(frame.telemetryid)
                framestr += '='
                framestr += ','.join([str(v) for v in frame.values])
            case FrameType.HEADER:
                framestr += 'H'
                framestr += str(frame.telemetryid)
                framestr += '='
                framestr += ','.join([(str(v[0]) +":"+ str[int(v[1])]) for v in frame.registers])
        framestr += '\n'
        self.connection.write(framestr.encode('ascii'))
        self._echosubject.on_next(framestr[:-1])

    def parse_telemetry(self, packet, header):
        packet.header = header
        return packet # nothing to do here, ascii telemetry can parse the values during parsing the frame
    
    def __parseFrame(self, framestr):
        if framestr.startswith('R'):
            reg, values = parse_register_and_values(framestr[1:])
            return Frame(frame_type=FrameType.REGISTER, register=reg, values=values)
        if framestr.startswith('r'):
            reg, values = parse_register_and_values(framestr[1:])
            return Frame(frame_type=FrameType.RESPONSE, register=reg, values=values)
        if framestr.startswith('T'):
            telemetryid, valuesstr = framestr[1:].split('=')[0:2]
            values = [parse_value(v) for v in valuesstr.split(',')]
            return Frame(frame_type=FrameType.TELEMETRY, values=values, telemetryid=int(telemetryid))
        if framestr.startswith('H'):
            telemetryid, valuesstr = framestr[1:].split('=')[0:2]
            registers = [[int(x) for x in r.split(':')] for r in valuesstr.split(',')]
            return Frame(frame_type=FrameType.HEADER, registers=registers, telemetryid=int(telemetryid))
        if framestr.startswith('S'):
            remote_in_sync = (framestr[1] != '0')
            return Frame(frame_type=FrameType.SYNC, values=[remote_in_sync])
        if framestr.startswith('A'):
            alert = framestr[1:]
            return Frame(frame_type=FrameType.ALERT, alert=alert)
        return None




class BinaryComms(Comms):
    def __init__(self, connection):
        super().__init__(connection)
        self._expected = 0
        self._marker = False
        self._buffer = bytearray()

    def get_frame(self):
        while self.connection.in_waiting > 0:
            byte = self.connection.read()
            frame = self.__processByte(byte)
            if frame is not None:
                return frame
        return None

    def send_frame(self, frame):
        self.connection.write(MARKER.to_bytes(1))
        self.connection.write(self.__frame_size(frame).to_bytes(1))
        match frame.frame_type:
            case FrameType.REGISTER:
                if not isinstance(frame.register, Register):
                    frame.register = Register.by_id(frame.register)
                self.connection.write(b'R')
                self.connection.write(int(frame.register).to_bytes(1))
                self.__write_values(frame)
            case FrameType.SYNC:
                self.connection.write(b'S')
                self.connection.write(int(1 if self._in_sync else 0).to_bytes(1))
            case FrameType.ALERT:
                self.connection.write(b'A')
                self.connection.write(str(frame.alert).encode('ascii'))
            case FrameType.RESPONSE:
                if not isinstance(frame.register, Register):
                    frame.register = Register.by_id(frame.register)
                self.connection.write(b'r')
                self.connection.write(int(frame.register).to_bytes(1))
                self.__write_values(frame)
            case FrameType.TELEMETRY:
                self.connection.write(b'T')
                self.connection.write(int(frame.telemetryid).to_bytes(1))
                self.__write_values(frame) # todo finish this, telemetry isn't a single register - don't really need to write telemetry frames though for normal use
            case FrameType.HEADER:
                self.connection.write(b'H')
                self.connection.write(len(frame.registers).to_bytes(1))
                for r in frame.registers:
                    self.connection.write(int(r[0]).to_bytes(1))
                    self.connection.write(int(r[1]).to_bytes(1))
        self._echosubject.on_next(frame)

    def parse_telemetry(self, packet, header):
        packet.header = header
        values = []
        if header is not None:
            pos = 0
            for reg in header.registers:
                for t in reg.read_types:
                    val, size = self.__parse_value(reg.values, pos, t)
                    pos += size
                    values.append(val)
        packet.values = values
        return packet

    def __write_values(self, frame, offset=0):
        if frame.values is not None and len(frame.values) > 0:
            for i, t in enumerate(frame.register.write_types):
                match t:
                    case 'f':
                        self.connection.write(struct.pack('f', float(frame.values[offset+i])))
                    case 'i':
                        self.connection.write(int(frame.values[offset+i]).to_bytes(4))
                    case 'b':
                        self.connection.write(int(frame.values[offset+i]).to_bytes(1))
                    case _:
                        raise Exception("Unsupported value type")

    def __frame_size(self, frame):
        match frame.frame_type:
            case FrameType.REGISTER:
                size = 2
                if frame.values is not None and len(frame.values) > 0:
                    size += sum((1 if t == 'b' else 4) for t in frame.register.write_types)
                return size
            case FrameType.SYNC:
                return 2
            case FrameType.ALERT:
                return 1 + len(frame.alert)
            case FrameType.RESPONSE:
                size = 2
                if frame.values is not None and len(frame.values) > 0:
                    size += sum((1 if t == 'b' else 4) for t in frame.register.write_types)
                return size
            case FrameType.TELEMETRY:
                size = 2
                # todo correct length for TELEMETRY frame... but writing telemetry isn't really needed for normal use
                return size
            case FrameType.HEADER:
                size = 1 + 2 * len(frame.registers)
                return size

    def __processByte(self, byte):
        if byte == MARKER:
            if self._expected == 0:
                self._in_sync = False
                self._marker = True
                self._buffer.clear()
                return None
            if len(self._buffer) == self._expected:
                self._in_sync = True
                frame = self.__parseFrame(self._buffer)
                if frame is None:
                    self._in_sync = False
                self._expected = 0
                self._marker = True
                self._buffer.clear()
                return frame
            else:
                self._buffer.append(byte)
                return None
        elif len(self._buffer) == self._expected and self._expected > 0:
            self._in_sync = False
            self._expected = 0
            self._buffer.clear()
            return None
        if self._marker:
            self._expected = byte
            self._marker = False
            return None
        self._buffer.append(byte)
        return None
    
    def __parseFrame(self, buffer):
        if buffer[0] == ord('R'):
            reg = SimpleFOCRegisters.by_id(buffer[1])
            values = []
            pos = 2
            for t in reg.read_types:
                val, size = self.__parse_value(buffer, pos, t)
                pos += size
                values.append(val)
            return Frame(frame_type=FrameType.REGISTER, register=reg, values=values)
        if buffer[0] == ord('r'):
            reg = buffer[1]
            values = []
            pos = 2
            for t in reg.read_types:
                val, size = self.__parse_value(buffer, pos, t)
                pos += size
                values.append(val)
            return Frame(frame_type=FrameType.RESPONSE, register=reg, values=values)
        if buffer[0] == ord('T'):
            id = buffer[1] # we can read the id byte, but we don't yet have the header to parse the values
            return Frame(frame_type=FrameType.TELEMETRY, telemetryid=id, values=buffer[2:])
        if buffer[0] == ord('H'):
            num_registers = buffer[1]
            registers = []
            for i in range(2, len(buffer), 2):
                registers.append([buffer[i], buffer[i+1]])
            return Frame(frame_type=FrameType.HEADER, registers=registers)
        if buffer[0] == ord('S'):
            remote_in_sync = (buffer[1] != 0)
            return Frame(frame_type=FrameType.SYNC, values=[remote_in_sync])
        if buffer[0] == ord('A'):
            alert = buffer[1:].decode('ascii')
            return Frame(frame_type=FrameType.ALERT, alert=alert)

    def __parse_value(self, buffer, pos, t):
        match t:
            case 'f':
                if pos+4>len(buffer):
                    return None, 4
                return struct.unpack('f', buffer[pos:pos+4]), 4
            case 'i':
                if pos+4>len(buffer):
                    return None, 4
                return int.from_bytes(buffer[pos:pos+4]), 4
            case 'b':
                if pos+1>len(buffer):
                    return None, 1
                return int.from_bytes(buffer[pos:pos+1]), 1
            case _:
                raise Exception("Unsupported value type")