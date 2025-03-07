import serial
import time

VXM_COMMAND = 255
VXM_RETURN = 50
VMX_WAIT = 800000

class VXM:

    def __init__(self, port, baudrate = 9600, timeout = VMX_WAIT, parity = serial.PARITY_NONE, string_return = 255):
        self.motors = {}
        self.port = None
        self.serial = None
        ####vxm conf####

        self.stpx = 80
        self.stpy = 80
        self.spdx = 1200
        self.spdy = 1500
        self.lmtx = 28540
        self.lmty = 28498
        #AZIMUTHAL number of steps from limit switch to zero (North)
        #POSX 2902 changed by medina Y15M04D28
        self.POSX = 2974

        #VERTICAL number of step from limit swit to zero (horizontal plane)
        #POSY 8677   modified by Kevin and Carlos on Mar 2017
        self.POSY = 8598

        if isinstance(port, str):
            self.port = port
            self.serial = serial.Serial(self.port, baudrate, timeout=timeout, parity=parity)
        elif isinstance(port, serial.Serial):
            self.serial = port
            self.port = self.serial.port
        else:
            raise TypeError

    def add_motor(self, id, name):
        self.motors[name] = self.Motor(self.serial, id)
        return self.motors[name]

    def get_motor(self, name):
        return self.motors[name]

    class Motor:

        def __init__(self, serial, id):
            self.serial = serial
            self.id = id
            self.string_return = 255

        def is_connected(self):
            self.flush_buffers()
            self.send_command("E")
            self.send_command("C")
            self.send_command("V")

            ready = self.read_command()
            if ready == "R": 
                print(f"VXM:CONNECT:Connected to {self.port} at {self.baudrate} baud")
                return True
            else: 
                for i in range(0, 10):
                    ready = self.read_command()
                    print(f"VXM:CONNECT:Attempt {i}, response: {ready}")
                    if ready == "R":
                        print(f"VXM:CONNECT:Connected to {self.port} at {self.baudrate} baud")
                        return True
                    else:
                        print(f"VXM:CONNECT:ERROR:Unable to reach device at {self.port}. Trying again...")
                
                print("VXM:CONNECT:ERROR:Maximum number of trial exceeded")
                return False

        def read_command(self):   
            if self.serial and self.serial.is_open:
                try:
                    response = self.serial.read(self.string_return).decode(errors='ignore').strip()
                    response = str(response)
                    return response
                except serial.SerialException: 
                    print(f"VXM:READ_R:ERROR:Unable to read response")
                    return -1
            return ""

        def send_command(self, command):
            if self.serial and self.serial.is_open:
                try:
                    self.serial.flushInput()
                    self.serial.write(f"{command}\r".encode())
                    time.sleep(0.5)

                    response = self.read_command()

                    return response

                except serial.SerialException as e:
                    print(f"VXM:SEND_COMM:Unable to send {command} command: {e}")
                    return -1
            else:
                print(f"VXM:SEND_COMM:Serial port is not open")
                return -1
            
        def flush_buffers(self):
            try:
                self.serial.reset_input_buffer()
                self.serial.reset_output_buffer()
                time.sleep(0.1)
                return 0
            except Exception as e:
                print(f"VXM:FLUSH_BUFFERS:Unable to flush buffers: {e}")
                return -1
            
        def set_model(self, model):
            self.flush_buffers()
            ready = self.send_command(f"setM{self.id}M{model}")
            
            if ready and ready== "^":
                print(f"VXM:SET_MODEL:VXM at {self.port}:Motor {self.id} model set: {model}")
                return 0
            else:
                print(f"VXM:SET_MODEL:ERROR:VXM at {self.serial}:ìUnable to set motor {self.id} model")
                return -1
          
        def set_acc(self, value):
            self.flush_buffers()
            ready= self.send_command(f"A{self.id}M{value}")

            if ready and ready== "^":
                print(f"VXM:SET_ACC:VXM at {self.port}:Motor {self.id} acceleration set: {value}")
                return 0
            else:
                print(f"VXM:SET_ACC:ERROR:VXM at {self.serial}:Unable to set motor {self.id} acceleration")
                return -1

        def set_speed(self, value):
            self.flush_buffers()
            ready = self.send_command(f"S{self.id}M{value}")
            if ready and ready== "^":
                print(f"VXM:SET_SPEED:VXM at {self.port}:Motor {self.id} speed set: {value}")
                return 0
            else:
                print(f"VXM:SET_SPEED:ERROR:VXM at {self.serial}:Unable to set motor {self.id} speed")
                return -1
            
        def run(self):
            self.flush_buffers()
            ready = self.read_command("R")
            try:
                while ready != "^":
                    time.sleep(0.5)
                    ready = self.read_command("R")

                print(f"VXM:RUN:Executed")
                return 0
            except Exception as e:
                print(f"VXM:RUN:ERROR:VXM at {self.serial}:Unable to execute:{e}")
                return -1

        def wait(self,dtime):
            self.flush_buffers()
            wait_time = int(f"{dtime}0")
            command_str = f"P{dtime}"
            try:
                read = self.send_command(command_str)
                if command_str == read:
                    self.run()
                    print(f"VXM:WAIT:done waiting, ready for next step...")
                    return 0
                else:
                    print(f"VXM:WAIT:ERROR:command expected: {command_str}, command read: {read}")
                    return -1
            except Exception as e:
                print(f"VXM:SET_SPEED:ERROR:VXM at {self.serial}:Unable to set waiting:{e}")
                return -2
        
        def move_FWD(self, pos):
            self.flush_buffers()
            command_str = f"I{self.id}M{pos}"
            try:
                read = self.send_command(command_str)
                if command_str == read:
                    self.run()
                    print(f"VXM:MOVE_FWD:VXM at {self.serial}: motor {self.id} in position {pos}")
                    return 0 
                else:
                    print(f"VXM:MOVE_FWD:ERROR:command expected: {command_str}, command read: {read}")
                    return -1
            except Exception as e:
                print(f"VXM:MOVE_FWD:ERROR:VXM at {self.serial}:unable to move motor {self.id} in position {pos}:{e}")
                return -2
            
        def move_BWD(self, pos):
            self.flush_buffers()
            command_str = f"I{self.id}M-{pos}"
            try:
                read = self.send_command(f"I{self.id}M-{pos}")
                if command_str == read:
                    self.run()
                    print(f"VXM:MOVE_BWD:VXM at {self.serial}: motor {self.id} in position {pos}")
                    return 0 
                else:
                    print(f"VXM:MOVE_BWD:ERROR:command expected: {command_str}, command read: {read}")
                    return -1
            except Exception as e:
                print(f"VXM:MOVE_BWD:ERROR:VXM at {self.serial}:unable to move motor {self.id} in position {pos}:{e}")
                return -2
               
        def move_Neg0(self):
            self.flush_buffers()
            command_str = f"I{self.id}M-0"
            try:
                read = self.send_command(command_str)
                if command_str == read:
                    self.run()
                    print(f"VXM:MOVE_NEG0:VXM at {self.serial}: motor {self.id} in negative zero position")
                    return 0 
                else: 
                    print(f"VXM:MOVE_NEG0:ERROR:command expected: {command_str}, command read: {read}")
                    return -1
            except Exception as e:
                print(f"VXM:MOVE_NEG0:ERROR:VXM at {self.serial}:unable to move motor {self.id} in negative zero position:{e}")
                return -2
            
        def move_Pos0(self):
            self.flush_buffers()
            command_str = f"I{self.id}M0"
            try:
                read = self.send_command(command_str)
                if command_str == read:
                    self.run()
                    print(f"VXM:MOVE_POS0:VXM at {self.serial}: motor {self.id} in positive zero position")
                    return 0 
                else: 
                    print(f"VXM:MOVE_POS0:ERROR:command expected: {command_str}, command read: {read}")
                    return -1
            except Exception as e:
                print(f"VXM:MOVE_POS0:ERROR:VXM at {self.serial}:unable to move motor {self.id} in positive zero position:{e}")
                return -2
            
        def move_ABS0(self):
            self.flush_buffers()
            command_str = f"IA{self.id}M0"
            try:
                read = self.send_command(command_str)
                if command_str == read:
                    self.run()
                    print(f"VXM:MOVE_ABS0:VXM at {self.serial}: motor {self.id} in absolute 0 position")
                else:
                    print(f"VXM:MOVE_ABS0:ERROR:command expected:{command_str}, command read:{read}")
                    return -1
            except Exception as e:
                print(f"VXM:MOVE_ABS0:ERROR:VXM at {self.serial}:unable to move motor {self.id} in absolute 0 position:{e}")
                  
        def move_ABS(self, abs_pos):
            self.flush_buffers()
            abs_pos = int(abs_pos)
            command_str = f"IA{self.id}M{abs_pos}"
            if self.id == 1:
                current_pos = self.send_command("X")
            else:
                current_pos = self.send_command("Y")
            current_pos = int(current_pos)


            if current_pos == abs_pos:
                print(f"VXM:MOVE_ABS:VXM at {self.serial}:motor {self.id} already in absolute position {abs_pos}")
            else:
                try:
                    read = self.send_command(command_str)
                    if command_str == read: 
                        self.run()

                        print(f"VXM:MOVE_ABS:VXM at {self.serial}:motor {self.id} in absolute position {abs_pos}")
                        return 0 
                    else: 
                        print(f"VXM:MOVE_ABS:ERROR:command expected: {command_str}, command read: {read}")
                        return -1
                except Exception as e:
                    print(f"VXM:MOVE_ABS:ERROR:VXM at {self.serial}:unable to move motor {self.id} in absolute position {abs_pos}:{e}")
                    return -2

        def set_ABSzero(self, abs_zero):
            self.flush_buffers()
            self.move_ABS(self.id, abs_zero)
            try:
                self.send_command(f"IA{self.id}M-0")
                while self.read_command() != "^": 
                    time.sleep(0.5)
                print(f"VXM:MOVE_ABS:VXM at {self.serial}: motor {self.id} in absolute position {abs_zero}")
                return 0 
            except Exception as e:
                print(f"VXM:MOVE_ABS:ERROR:VXM at {self.serial}:unable to move motor {self.id} in absolute position {abs_zero}:{e}")
                return -1
        
if __name__ == "__main__":
    # usage with serial object as parameter
    #s = serial.Serial("/dev/ttyUSB0", 9600)
    #vxm = VXM(s)

    vxm = VXM("/dev/ttyUSB0", 9600, 2)
    m1 = vxm.add_motor(0, "NorthSouth")
    m1.move_ABS(0)

