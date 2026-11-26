import serial
import time
import logging
import datetime
from dataclasses import dataclass
from functools import partial
from logging.handlers import TimedRotatingFileHandler

# Protocol (User's Manual, "General Format Overview"): command "$name data<CR>", only the first
# 5 characters of name are used; every complete command gets one acknowledgement packet
# "$name data", "$Bad Command" or "$Bad Value", within 5 seconds.
RESPONSE_TIMEOUT_S = 5.0
STANDBY_RETRIES = 3

# State Byte (manual p. 33), D7 .. D0
STATE_FIRE = 0x80           # D7 FIRE authorized
STATE_STANDBY = 0x40        # D6 STANDBY authorized
STATE_CONFIG = 0x3E         # D5 Q-switched, D4 diode trigger ext, D3 Q-switch trigger ext,
                            # D2 diodes enabled, D1 Q-switch enabled: the configuration of the runs
# Happy Byte 1 (global, manual p. 34)
HB1_WARNING = 0x01          # laser keeps working
HB1_NOT_READY = 0x02        # laser cannot fire (e.g. temperature still out of range)
HB1_INTERLOCK = 0x04
# HB2 / HB3 bits D2..D0: which temperature is in WARNING / NOT-READY range (manual p. 35)
TEMPERATURE_NAMES = {1: "pump head", 2: "dump resistor", 3: "interface plate", 4: "spare sensor"}
HB2_NAMES = {0x08: "diode trigger frequency too high", 0x10: "remote run BNC triggers disabled"}
HB3_NAMES = {0x08: "TEC power supply", 0x10: "diode power supply", 0x20: "emergency over-temperature",
             0x40: "self-test (I2C sensors / EEPROM)"}
HB4_NAMES = {0x80: "J1 disconnected", 0x40: "J2 disconnected", 0x20: "remote interlock open",
             0x10: "E-stop open", 0x08: "controller cover open", 0x04: "low coolant flow",
             0x02: "low coolant level"}

# fire only below these temperatures (1/10 C): the laser has its own limits, these are ours
FIRE_MAX_TEMPS = (500, 450, 450)        # pump head, dump resistor, interface plate
# names of the $TEMPS values, in their order; minimum temperatures to fire well are per site
# (parameters.yml <site>: laser_min_temp_c: {head: 42, dump: 26}): READY alone is too early
TEMP_NAMES = ("head", "dump", "plate")

_now = time.monotonic   # module level, so that tests can replace the clock
_sleep = time.sleep


def _command_name(text):
    """First 5 characters of the command name, as the laser compares them."""
    return text.strip().split()[0].lstrip('$')[:5].upper() if text.strip() else ""


def _bits(byte, names):
    return [name for bit, name in names.items() if byte & bit]


@dataclass(frozen=True)
class LaserStatus:
    """Answer to $STATUS ?: State Byte and the four Happy Bytes (manual p. 33-35)."""
    state: int
    hb1: int
    hb2: int
    hb3: int
    hb4: int

    @classmethod
    def parse(cls, answer):
        """LaserStatus of '$STATUS SB AA BB CC DD', None if malformed."""
        parts = answer.split()
        if len(parts) != 6 or parts[0] != '$STATUS':
            return None
        try:
            return cls(*(int(p, 16) for p in parts[1:]))
        except ValueError:
            return None

    @property
    def fire(self):
        return bool(self.state & STATE_FIRE)

    @property
    def standby(self):
        return bool(self.state & STATE_STANDBY)

    @property
    def configured(self):
        return self.state & STATE_CONFIG == STATE_CONFIG

    @property
    def not_ready(self):
        return bool(self.hb1 & HB1_NOT_READY)

    @property
    def interlock(self):
        return bool(self.hb1 & HB1_INTERLOCK)

    @property
    def ready(self):
        """Laser can fire: in STANDBY (or already FIRE), configured for the runs, READY
        (no NOT-READY, no interlock). A WARNING is fine: the laser keeps working."""
        return (self.standby or self.fire) and self.configured and not self.not_ready and not self.interlock

    def describe(self):
        """'SB 7E HB 03 01 01 00: STANDBY, NOT-READY (pump head temperature), WARNING (...)'"""
        mode = "FIRE" if self.fire else "STANDBY" if self.standby else "SLEEP"
        what = [mode]
        if not self.configured:
            what.append(f"configuration {self.state & STATE_CONFIG:#04x} (runs need {STATE_CONFIG:#04x})")
        if self.hb1 & HB1_NOT_READY:
            what.append("NOT-READY (" + ", ".join(self._causes(self.hb3, HB3_NAMES)) + ")")
        if self.hb1 & HB1_INTERLOCK:
            what.append("INTERLOCK (" + ", ".join(_bits(self.hb4, HB4_NAMES) or ["?"]) + ")")
        if self.hb1 & HB1_WARNING:
            what.append("WARNING (" + ", ".join(self._causes(self.hb2, HB2_NAMES)) + ")")
        return (f"SB {self.state:02X} HB {self.hb1:02X} {self.hb2:02X} {self.hb3:02X} {self.hb4:02X}: "
                + ", ".join(what))

    @staticmethod
    def _causes(byte, names):
        out = _bits(byte, names)
        if byte & 0x07:
            out.insert(0, f"{TEMPERATURE_NAMES.get(byte & 0x07, 'unknown sensor')} temperature")
        return out or ["?"]


class Centurion:

    def __init__(self, port, baudrate=57600, parity=serial.PARITY_EVEN, timeout=2):
        self.port = port
        self.serial = None
        self.params = dict(baudrate=baudrate, parity=parity, timeout=timeout)
        self._last_status = None            # last LaserStatus description logged
        self.min_temps = {}                 # {"head": 420, ...} in 1/10 C, see set_min_temps
        self._last_waiting = None           # temperatures still below minimum, last logged

        # logger first: it is needed to report a failure opening the port
        self.logger = logging.getLogger("device")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            formatter = logging.Formatter('%(asctime)s - %(classname)s::%(funcName)s - %(levelname)s - %(message)s')
            handler = TimedRotatingFileHandler('logs/device.log', when='midnight',
                atTime=datetime.time(hour=18, minute=0))
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.log = partial(self.logger.log, extra={'classname': self.__class__.__name__})

        try:
            self.serial = serial.Serial(**self.params)
        except serial.SerialException as e:
            self.log(logging.ERROR, f"CENT:CONN:Unable to create serial device: {e}")
            raise

        self.serial.port = port             # opened at the first command (check_open)

    def open(self):
        try:
            self.serial.open()
        except serial.SerialException as e:
            self.log(logging.ERROR, f"CENT:CONN:Unable to open device {self.port}: {e}")

    def check_open(func):
        def wrapper(self, *args, **kwargs):
            if self.serial.is_open is False:
                self.serial.open()
            return func(self, *args, **kwargs)
        return wrapper

    # ------------------------------------------------------------------ protocol

    @check_open
    def read_response(self, timeout_s=RESPONSE_TIMEOUT_S):
        """One acknowledgement packet (up to CR or LF), '' if none arrives within timeout_s.

        Returns as soon as the packet is complete: the old fixed read(255) always waited
        the whole serial timeout and missed packets arriving later than that."""
        deadline = _now() + timeout_s
        saved_timeout = self.serial.timeout
        data = b""
        try:
            while True:
                remaining = deadline - _now()
                if remaining <= 0:
                    break
                self.serial.timeout = min(remaining, 0.1)
                c = self.serial.read(1)
                if not c:
                    continue
                if c in b"\r\n":
                    if data.strip():
                        break
                    continue                    # terminator left from the previous packet
                data += c
        except serial.SerialException as e:
            self.log(logging.ERROR, f"CENT:READ_R:ERROR:Unable to read response: {e}")
            return ""
        finally:
            self.serial.timeout = saved_timeout
        # 'replace': a noise byte must not raise UnicodeDecodeError
        response = ''.join(filter(str.isprintable, data.decode('ascii', 'replace'))).strip()
        # every packet at DEBUG: the 1 s polls while waiting for READY would flood device.log
        self.log(logging.DEBUG, response)
        return response

    @check_open
    def send_command(self, command):
        """Send a command and return its acknowledgement packet; '' on $Bad Command,
        $Bad Value, timeout or serial error (all logged)."""
        command = command.strip()
        name = _command_name(command)
        try:
            self.serial.reset_input_buffer()    # drop late answers to previous commands
            self.serial.write(f"{command}\r".encode())
        except serial.SerialException as e:
            self.log(logging.ERROR, f"CENT:SEND_COMM:Unable to send {command} command: {e}")
            return ""
        deadline = _now() + RESPONSE_TIMEOUT_S
        while True:
            response = self.read_response(max(deadline - _now(), 0))
            if not response:
                self.log(logging.ERROR, f"CENT:SEND_COMM:no answer to {command} within {RESPONSE_TIMEOUT_S}s")
                return ""
            if response.upper().startswith("$BAD"):
                self.log(logging.ERROR, f"CENT:SEND_COMM:{command} -> {response}")
                return ""
            if _command_name(response) == name:
                return response
            # answer to an earlier command arrived late: not ours
            self.log(logging.WARNING, f"CENT:SEND_COMM:{command}: ignored unrelated packet {response!r}")

    @check_open
    def flush_buffers(self):
        """Drop anything pending (send_command also drops late answers before each command)."""
        try:
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            return 0
        except Exception as e:
            self.log(logging.ERROR, f"CENT:FLUSH_BUFFERS:Unable to flush buffers: {e}")
            return -1

    def comm_test(self):
        response = self.send_command("$HVERS ?")
        if response.startswith("$HVERS"):
            self.log(logging.INFO, f"CENT:COMM_TEST:PASSED OK ({response})")
            return 0
        self.log(logging.ERROR, f"CENT:COMM_TEST:Failed (answer {response!r})")
        return -2

    # ------------------------------------------------------------------ parameters

    def set_parameter(self, parameter, value):
        """0 if the laser acknowledged exactly '<parameter> <value>', -1 otherwise (logged)."""
        answer = self.send_command(f"{parameter} {value}")
        parts = answer.split()
        if len(parts) == 2 and _command_name(parts[0]) == _command_name(parameter) and parts[1] == f'{value}':
            self.log(logging.INFO, f"CENT:PARAMETER_SET:Parameter {parts[0]}, value set: {parts[1]}")
            return 0
        self.log(logging.ERROR, f"CENT:PARAMETER_SET:ERROR:Unable to set {parameter} {value} (answer {answer!r})")
        return -1

    def check_parameter(self, parameter):
        """Value (string) of a parameter, -1 on failure. The laser answers with the first 5
        characters of the name ($QSDELAY ? -> $QSDEL 145): compared on those."""
        answer = self.send_command(f"{parameter} ?")
        parts = answer.split()
        if len(parts) == 2 and _command_name(parts[0]) == _command_name(parameter):
            self.log(logging.INFO, f"CENT:PARAMETER_CHECK:Parameter {parts[0]}, value checked: {parts[1]}")
            return parts[1]
        self.log(logging.ERROR, f"CENT:PARAMETER_CHECK:ERROR:Unable to check {parameter} (answer {answer!r})")
        return -1

    def set_mode(self, freq = 100, diode = 1, qson= 0, qswitch = 1, dtrig = 1, qstrig = 1, dpw = 100, qsdelay = 145):
        """STANDBY and the run configuration; 0 when the State Byte shows it (READY is
        waited for later, by the run: fire_auth)."""
        try:
            self.log(logging.INFO, "CENT:SET_MODE:Setting up Centurion Laser...")
            self.log(logging.INFO, "CENT:SET_MODE:Going Standby...")
            self.send_command("$STANDBY")

            for _ in range(3):
                #setting frequency (100 == 2Hz)
                self.set_parameter("$DFREQ", freq)
                #setting diodes (off = 0, enabled = 1)
                self.set_parameter("$DIODE", diode)
                #setting Q-switch (off = 0, enabled = 1)
                self.set_parameter("$QSON", qson)
                #setting laser to be Q-switched (long pulse = 0, Q-switched = 1)
                self.set_parameter("$QSWIT", qswitch)
                #setting diode trigger in external mode (internal = 0, external = 1)
                self.set_parameter("$DTRIG", dtrig)
                #setting Q-swicth trigger to external mode (internal = 0, external = 1)
                self.set_parameter("$QSTRI", qstrig)
                #setting diodes pulse (energy of the laser)
                self.set_parameter("$DPW", dpw)
                #setting delay for Q-switch (relevant only for internal trigger)
                self.set_parameter("$QSDEL", qsdelay)
                if self.status() == 0x7E:
                    self.log(logging.INFO, "set up complete")
                    return 0
            self.log(logging.ERROR, "CENT:SET_MODE:ERROR:state not 0x7E after 3 attempts")
            return -1
        except Exception as e:
            self.log(logging.ERROR, f"CENT:SET_MODE:ERROR:Some problem occurred:{e}")
            return -1

    def check_mode(self):
        self.log(logging.INFO, "CENT:CHECK_MODE:Checking values:")
        for p in ("$DFREQ", "$DIODE", "$QSON", "$QSWIT", "$DTRIG", "$QSTRI", "$DPW", "$QSDEL"):
            self.check_parameter(p)
        return 0

    def check_qs_delay(self):
        return self.check_parameter("$QSDELAY")

    def check_pwdth(self):
        """Diode pulse width ($DPW) as a string, -1 on failure."""
        return self.check_parameter("$DPW")

    def set_pwdth(self, pwd):
        """0 if the laser took the new diode pulse width, -1 otherwise."""
        return self.set_parameter("$DPW", pwd)

    # ------------------------------------------------------------------ status

    def read_full_status(self):
        """LaserStatus (State Byte + Happy Bytes), None if the answer is missing or malformed.
        A change of status is logged (INFO), the same status again is not."""
        answer = self.send_command("$STATUS ?")
        st = LaserStatus.parse(answer)
        if st is None:
            self.log(logging.ERROR, f"CENT:STATUS:ERROR:unexpected answer {answer!r}")
            self._last_status = None
            return None
        text = st.describe()
        if text != self._last_status:
            self.log(logging.WARNING if st.not_ready or st.interlock else logging.INFO, f"CENT:STATUS:{text}")
            self._last_status = text
        return st

    def status(self):
        """State Byte, None if the answer is missing or malformed."""
        st = self.read_full_status()
        return None if st is None else st.state

    def set_min_temps(self, min_temp_c):
        """Minimum temperatures to fire, {"head": 42.0, "dump": 26.0} in C (None/{}: none).
        Unknown names raise ValueError (a typo in parameters.yml must not disable a check)."""
        min_temp_c = min_temp_c or {}
        unknown = set(min_temp_c) - set(TEMP_NAMES)
        if unknown:
            raise ValueError(f"laser_min_temp_c: unknown {sorted(unknown)} (known: {list(TEMP_NAMES)})")
        self.min_temps = {name: int(round(float(v) * 10)) for name, v in min_temp_c.items()}
        self._last_waiting = None

    def below_min_temps(self, temps):
        """[(name, value, minimum)] (1/10 C) of the temperatures still below their minimum."""
        return [(name, t, self.min_temps[name]) for name, t in zip(TEMP_NAMES, temps)
                if name in self.min_temps and t < self.min_temps[name]]

    def fire_auth(self):
        """True when the laser can fire well: STANDBY, configured, READY (Happy Bytes
        without NOT-READY / INTERLOCK) and every temperature at its site minimum.

        The State Byte alone (0x7E) is not enough: it reads 7E also while the laser is
        NOT-READY. READY alone is not enough either: the laser reports it with the pump head
        at ~39 C, but fires well only at ~42-44 C (site dependent, set_min_temps)."""
        st = self.read_full_status()
        if st is None or not st.ready:
            return False
        if not self.min_temps:
            return True
        temps = self.temperature()
        if temps is None:
            return False
        below = self.below_min_temps(temps)
        waiting = tuple(name for name, _, _ in below)
        if waiting != self._last_waiting:   # logged when what is missing changes, not every poll
            if below:
                self.log(logging.INFO, "CENT:READY:READY, waiting for temperature: " + ", ".join(
                    f"{name} {t / 10:.1f} < {lim / 10:.1f} C" for name, t, lim in below))
            else:
                self.log(logging.INFO, "CENT:READY:temperatures reached: " + ", ".join(
                    f"{name} {t / 10:.1f} C" for name, t in zip(TEMP_NAMES, temps)))
            self._last_waiting = waiting
        return not below

    def read_bytes(self):
        """Log the full status and the shot counters."""
        if self.read_full_status() is None:
            return -1
        for cmd, what in (("$SHOT ?", "Shots counter"), ("$USHOT ?", "User shots counter")):
            response = self.send_command(cmd)
            if response:
                self.log(logging.INFO, f"CENT:READ_BYTES:{what}:{response}")
        return 0

    def temperature(self):
        """(head, dump, plate) in 1/10 C, None if the answer is missing or malformed."""
        temps = self.send_command("$TEMPS ?")
        parts = temps.split()
        if len(parts) == 4 and parts[0] == '$TEMPS':
            try:
                return int(parts[1]), int(parts[2]), int(parts[3])
            except ValueError:
                pass
        self.log(logging.ERROR, f"CENT:TEMPS:ERROR:unexpected answer {temps!r}")
        return None

    # ------------------------------------------------------------------ modes

    def standby(self):
        """STANDBY, checked: 0 when the State Byte shows the laser out of FIRE, -1 after
        STANDBY_RETRIES attempts (logged as ERROR: the laser may still be able to fire)."""
        for attempt in range(1, STANDBY_RETRIES + 1):
            self.log(logging.INFO, "CENT:STANDBY:Going Standby...")
            answer = self.send_command('$STANDBY')
            st = self.read_full_status()
            if answer and st is not None and not st.fire:
                return 0
            if not answer and st is None:
                # silent laser (outlet off, cable): retrying only delays the abort/finish
                self.log(logging.ERROR, "CENT:STANDBY:ERROR:laser not answering")
                return -1
            self.log(logging.WARNING, f"CENT:STANDBY:attempt {attempt}: answer {answer!r}, "
                                      f"status {st.describe() if st else None}")
        self.log(logging.ERROR, f"CENT:STANDBY:ERROR:laser not confirmed out of FIRE after "
                                f"{STANDBY_RETRIES} attempts")
        return -1

    def warmup(self):
        """STANDBY with diodes and Q-switch enabled: the laser conditions itself until READY
        (waited for with fire_auth). 0 if every command was acknowledged, -1 otherwise."""
        ok = True
        for cmd, what in (('$STANDBY', "Going Standby"), ('$DIODE 1', "Turning On Diodes"),
                          ("$QSON 1", "Q-Switch enabling")):
            self.log(logging.INFO, f"CENT:WARMUP:{what}...")
            if not self.send_command(cmd):
                ok = False
        self.read_bytes()
        if not ok:
            self.log(logging.ERROR, "CENT:WARMUP:ERROR:not every command acknowledged (see above)")
        return 0 if ok else -1

    def sleep(self):
        self.log(logging.INFO, "CENT:SLEEP:Sending Centurion to sleep")
        if self.send_command("$STOP"):         # STOP takes no data (manual)
            self.log(logging.INFO, "CENT:SLEEP:Centurion sent to sleep")
            return 0
        return -1

    def fire(self):
        """FIRE mode, after a fresh temperature readout within FIRE_MAX_TEMPS and at least
        the site minimum temperatures (set_min_temps).
        0: $FIRE acknowledged; -1: no temperature readout; -2: temperature above maximum;
        -3: $FIRE not acknowledged; -4: temperature below the minimum to fire well."""
        temps = self.temperature()      # fresh readout only: never old or default values
        if temps is None:
            self.log(logging.ERROR, "CENT:FIRE:temperature readout failed - not firing")
            return -1
        if any(t > limit for t, limit in zip(temps, FIRE_MAX_TEMPS)):
            self.log(logging.ERROR, f"CENT:FIRE:temperature out of range (head {temps[0]}, "
                                    f"dump {temps[1]}, plate {temps[2]}) - not firing")
            return -2
        below = self.below_min_temps(temps)
        if below:
            self.log(logging.ERROR, "CENT:FIRE:temperature below the minimum to fire well (" + ", ".join(
                f"{name} {t / 10:.1f} < {lim / 10:.1f} C" for name, t, lim in below) + ") - not firing")
            return -4
        if not self.send_command("$FIRE"):
            self.log(logging.ERROR, "CENT:FIRE:$FIRE not acknowledged - not in fire mode")
            return -3
        # the State Byte should now report FIRE (D7). Logged only (with the full status, to
        # see why), to be confirmed on the real laser before refusing the run on it.
        deadline = _now() + RESPONSE_TIMEOUT_S
        while True:
            st = self.read_full_status()
            if st is not None and st.fire:
                break
            if _now() >= deadline:
                self.log(logging.WARNING, "CENT:FIRE:$FIRE acknowledged but FIRE bit D7 not set: "
                                          f"{st.describe() if st else 'no status'}")
                break
            _sleep(0.5)
        return 0


if __name__ == "__main__":
    c = Centurion("/dev/ttyr01")
    print(c.temperature())
    print(c.read_full_status())
