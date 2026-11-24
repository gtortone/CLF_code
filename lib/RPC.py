import serial
import re
import time

class RPCDevice:

    def __init__(self, port, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=2):
        self.outlets = {}
        self.port = port
        self.serial = None
        self.params = locals()
        self.params.pop('port')
        self.params.pop('self')

        try:
            self.serial = serial.Serial(**self.params)
        except serial.SerialException as e:
            print(f"RPC:CONN: Unable to create serial device: {e}")

        self.serial.port = port

    def open(self):
        try:
            self.serial.open()
        except serial.SerialException as e:
            print(f"RPC:CONN: Unable to open device {self.port}: {e}")

    def check_open(func):
        def wrapper(self, *args, **kwargs):
            if self.serial.is_open is False:
                self.serial.open()
            return func(self, *args, **kwargs)
        return wrapper

    def add_outlet(self, id, name):
        self.outlets[name] = RPCOutlet(self.serial, id)
        return self.outlets[name]

    def get_outlet(self, name):
        return self.outlets[name]

    @check_open
    def wait_prompt(self):
        output = ""
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()
        self.serial.write('\r\n'.encode('utf-8'))
        self.serial.flush()
        while "RPC>" not in output:
            buffer = self.serial.read_all().decode('utf-8', 'ignore')
            output += buffer

        time.sleep(0.2)
        return output

    @check_open
    def status(self):
        output = self.wait_prompt()
        lines = output.splitlines()

        map = {}
        for line in lines:
            match = re.match(r"([1-6])\)\.{3}(.*): (On|Off)", line)
            if match:
                map[match.group(1)] = {"device": str.rstrip(match.group(2)), "state": match.group(3)}

        return str.lower(map[str(self.id)]['state']) == 'on'        

    def set(self, id, state):
        cmd = ["off", "on"]

        self.wait_prompt()
        self.serial.write(f"{cmd[state]} {id}\r\n".encode())
        self.serial.flush()
        output = ""
        while True:
            buffer = self.serial.read_all().decode('utf-8', 'ignore')
            output += buffer
            if "(Y/N)?" in output:
                break
            if "ERROR" in output:
                self.serial.reset_input_buffer()
                self.serial.reset_output_buffer()
                self.serial.flush()
                self.wait_prompt()
                self.serial.write(f"{cmd[state]} {id}\r\n".encode())
                self.serial.flush()
                output = ""                

        self.serial.write(b"y\r\n")  # confirm command
        self.serial.write('\r\n'.encode('utf-8'))
        self.serial.flush()

        if self.status() == state:
            return True

        return False

    @check_open
    def on(self):
        return self.set(self.id, 1)

    @check_open
    def off(self):
        return self.set(self.id, 0)

class RPCOutlet(RPCDevice):

    def __init__(self, serial, id):
        self.serial = serial
        self.id = id

