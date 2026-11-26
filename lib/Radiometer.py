import math
import time
import serial
import logging
import datetime
from functools import partial
from logging.handlers import TimedRotatingFileHandler

RADIOMETER_WAIT = 2

_now = time.monotonic      # module level, so that tests can replace the clock


def read_powers(radiometers):
    """The triggered value of the same shot from each radiometer, read one after the other
    with ONE common deadline (READ_TIMEOUT_S after the call, i.e. after the FPGA packet):
    a radiometer that does not answer cannot push the next one past the next shot."""
    start = _now()
    return [r.read_power(start=start) for r in radiometers]

class Radiometer:

    model: str = "unknown"

    def __init__(self, port, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=1):
        self.port = None
        self.serial = None
        self.ready = False
        self.params = locals()
        self.params.pop('port')
        self.params.pop('self')

        try:
            self.serial = serial.Serial(**self.params)
        except serial.SerialException as e:
            print(f"RADM_MON_{self.model}:Unable to create serial device: {e}") 
            raise e

        self.serial.port = port

        self.logger = logging.getLogger("device")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            formatter = logging.Formatter('%(asctime)s - %(classname)s::%(funcName)s - %(levelname)s - %(message)s')
            handler = TimedRotatingFileHandler('logs/device.log', when='midnight',
                atTime=datetime.time(hour=18, minute=0))
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.log = partial(self.logger.log, extra={'classname': self.__class__.__name__})


    def open(self):
        try:
            self.serial.open()
        except serial.SerialException as e:
            print(f"RPC:CONN: Unable to open device {self.port}: {e}")        

    def is_ready(self):
        return self.ready

    @staticmethod
    def check_open(func):
        def wrapper(self, *args, **kwargs):
            if self.serial.is_open is False:
                self.serial.open()
            return func(self, *args, **kwargs) 
        return wrapper
    
    # wait for one triggered value at most this long. read_power() is called right after
    # the FPGA packet of the shot (Run.log_shot), so the wait must stay below the shot
    # period (1 s): the next shot's value can never be taken. Readings can arrive late
    # (radiometer + MOXA NPort buffering): those slower than SLOW_READING_S are logged.
    READ_TIMEOUT_S = 0.95
    SLOW_READING_S = 0.5

    def _parse_value(self, line):
        """Measured value in a line of the triggered output, None if the line is not a value."""
        raise NotImplementedError

    @check_open
    def read_power(self, start=None):
        """Value of the next triggered measurement (10^-3 J); NaN on any error.
        `start` (module clock _now()): when the wait began, to read several radiometers of
        the same shot one after the other within one common deadline (read_powers)."""
        if not self.ready:
            self.log(logging.ERROR, f"RADM_MON_{self.model}: not ready (setup not done)")
            return math.nan
        start = _now() if start is None else start
        deadline = start + self.READ_TIMEOUT_S
        saved_timeout = self.serial.timeout
        last_look = False
        try:
            while True:
                remaining = deadline - _now()
                if remaining <= 0:
                    if last_look:
                        self.log(logging.ERROR, f"RADM_MON_{self.model}: no value within {self.READ_TIMEOUT_S}s")
                        return math.nan
                    # deadline already used by another radiometer: still take a value
                    # that is already received (non-blocking read)
                    last_look, remaining = True, 0
                self.serial.timeout = remaining
                self._rx = getattr(self, '_rx', b"") + self.serial.read_until(b"\r")
                if not self._rx.endswith(b"\r"):
                    continue            # timeout in the middle of a line: never parse a cut number
                line, self._rx = self._rx.decode(errors='replace').strip(), b""
                if not line:
                    continue
                value = self._parse_value(line)
                if value is not None:
                    waited = _now() - start
                    if waited > self.SLOW_READING_S:
                        self.log(logging.WARNING, f"RADM_MON_{self.model}: slow reading, {waited:.2f}s after the shot")
                    return value
                self.log(logging.WARNING, f"RADM_MON_{self.model}: skipped unexpected line {line!r}")
        except serial.SerialException as e:
            self.log(logging.ERROR, f"RADM_MON_{self.model}: read error: {e}")
            return math.nan
        finally:
            self.serial.timeout = saved_timeout

    @check_open
    def discard_pending(self):
        """Read and drop what is already received (called just before a shot): a reading
        there now belongs to an earlier shot (e.g. the last one of the previous run, that
        the port flush at the start did not remove) and must not be taken for this shot.
        The dropped lines are logged. Returns them."""
        try:
            data = getattr(self, '_rx', b"") + self.serial.read_all()
        except serial.SerialException as e:
            self.log(logging.ERROR, f"RADM_MON_{self.model}: read error: {e}")
            return []
        self._rx = b""
        lines = [l.strip() for l in data.decode(errors='replace').split("\r") if l.strip()]
        if lines:
            self.log(logging.WARNING, f"RADM_MON_{self.model}: dropped {len(lines)} reading(s) received "
                                      f"before the shot: {lines}")
        return lines

    @check_open
    def flush_buffers(self):
        self._rx = b""                  # partial line kept by read_power()
        try:
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
        except Exception as e:
            print(f"RADM_MON_{self.model}:FLUSH_BUFFERS:Unable to flush buffers")
            return -1

    @check_open
    def set(self, label, value):
        try:
            self.flush_buffers()
            self.serial.write(f"{label} {value}\r".encode())
        except serial.SerialException as e:
            print(f"RADM_MON_{self.model}:SET:Unable to send {label} {value}: {e}")
            return None
        try:
            ret = self.serial.read_until("\r".encode())[:-1].decode(errors='ignore')
        except serial.SerialException as e:
            print(f"RADM_MON_{self.model}:SET:Unable to read result {label} {value}: {e}")
            return None

        if ret[0] != '?':
            return ret[1:]
        else:
            print(f"RADM_MON_{self.model}:SET:Unable to set {label} {value}")
            return None


class Radiometer3700(Radiometer):

    model = "3700"

    def info(self):
        #self.flush_buffers()
        try:
            id = self.get("ID")
            vers = self.get("VR")
            probe = self.get("PA")
            status = self.get("ST")
            if id and vers and probe and status:
                print(f"RADM_MON_{self.model}:RAD_INFO:Radiometer identity: {id}")
                print(f"RADM_MON_{self.model}:RAD_INFO:Radiometer version: {vers}")
                print(f"RADM_MON_{self.model}:RAD_INFO:Probe id and type: {probe}")
                print(f"RADM_MON_{self.model}:RAD_INFO:Status: {status}")
        except Exception as e:
            print(f"RADM_MON_{self.model}:RAD_INFO:ERROR:Some problem occurred: {e}")

    @Radiometer.check_open
    def get(self, label):
        try:
            self.flush_buffers()
            self.serial.write(f"{label}\r".encode())
        except serial.SerialException as e:
            print(f"RADM_MON_{self.model}:GET:Unable to get {label}: {e}")
            return None
        try:
            ret = self.serial.read_until("\r".encode())[:-1].decode(errors='ignore')
        except serial.SerialException as e:
            print(f"RADM_MON_{self.model}:SET:Unable to read result {label}: {e}")
            return None

        if ret:
            if ret[0] == '?':
                print(f"RADM_MON_{self.model}:GET:Unable to get {label}")
                return None
            else:
                return ret
        return None

    def setup(self):
        try:
            #self.flush_buffers()
            self.set("TG", 3)
            self.set("SS", 0)
            self.set("FA", 1.00)
            self.set("EV", 1)
            self.set("BS", 0)
            self.set("RA", 2)
            self.get("AD")
        except Exception as e:
            #print(f"RADM_MON_{self.model}:SET_UP:ERROR:Some problem occurred: {e}")
            self.log(logging.ERROR, f"RADM_MON_{self.model}:SET_UP:ERROR:Some problem occurred: {e}")
            
        self.log(logging.INFO, f"RADM_MON_{self.model}:SET_UP: Radiometer setup completed")
        self.ready = True

    def set_range(self, range):
        self.flush_buffers()
        self.set("RA", range)

    def _parse_value(self, line):
        # triggered output: one plain number per shot
        try:
            return float(line)
        except ValueError:
            return None

class RadiometerOphir(Radiometer):

    model = "OPHIR"

    @Radiometer.check_open
    def get(self, label):
        try:
            self.flush_buffers()
            self.serial.write(f"{label} ?\r".encode())
        except serial.SerialException as e:
            print(f"RADM_MON_{self.model}:GET:Unable to get {label}: {e}")
            return None
        try:
            ret = self.serial.read_until("\r".encode())[:-1].decode(errors='ignore')
        except serial.SerialException as e:
            print(f"RADM_MON_{self.model}:SET:Unable to read result {label}: {e}")
            return None

        if ret:
            if ret[0] == '?':
                print(f"RADM_MON_{self.model}:GET:Unable to get {label}")
                return None
            elif ret[0] == '*':
                return ret[1:]
        return None

    def info(self):
        self.flush_buffers()
        try: 
            id = self.get("$II")
            probe = self.get("$HI")
            battery = self.get("$BC")

            if id and probe and battery:
                print(f"RADM_{self.model}:RAD_INFO:Radiometer identity: {id}")                
                print(f"RADM_{self.model}:RAD_INFO:Probe id and type: {probe}")
                print(f"RADM_{self.model}:RAD_INFO:Battery conditions: {battery}")
                return 0
            else:
                missing = []
                if not id:
                    missing.append("id")
                if not probe:
                    missing.append("probe")
                if not battery:
                    missing.append("battery")
                print(f"RAD_{self.model}:RAD_INFO:ERROR:Unable to retrieve info: {missing}")
        except Exception as e:
            print(f"RAD_{self.model}:RAD_INFO:ERROR:Some problem occurred: {e}")
            return -1

    def setup(self):
        try:
            self.flush_buffers()
            self.set("$DU", 1)
            self.set("$CS", "1 0 1")
        except Exception as e:
            #print(f"RADM_MON_{self.model}:SET_UP:ERROR:Some problem occurred: {e}")
            self.log(logging.ERROR, f"RADM_MON_{self.model}:SET_UP:ERROR:Some problem occurred: {e}")

        #print(f"RADM_MON_{self.model}:SET_UP done")
        self.log(logging.INFO, f"RADM_MON_{self.model}:SET_UP: Radiometer setup completed")
        self.ready = True

    def _parse_value(self, line):
        # triggered output: '*<value>' per shot
        if not line.startswith("*"):
            return None
        try:
            return float(line[1:])
        except ValueError:
            return None
