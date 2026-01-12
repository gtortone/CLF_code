import serial
import re
import time

def wait_prompt():
    output = ""
    s.reset_input_buffer()
    s.reset_output_buffer()
    s.write('\r\n'.encode('utf-8'))
    s.flush()
    while "RPC>" not in output:
        buffer = s.read_all().decode('utf-8', 'ignore')
        output += buffer

    time.sleep(0.2)
    return output

def rpc_outlet_set(s, id, state):
    wait_prompt()

    cmd = ["off", "on"]

    print(f"turning {state} outlet {id}...")
    s.write(f"{cmd[state]} {id}\r\n".encode())
    s.flush()
    output = ""
    while True:
        buffer = s.read_all().decode('utf-8', 'ignore')
        output += buffer
        if "(Y/N)?" in output:
            break
        if "ERROR" in output:
            s.reset_input_buffer()
            s.reset_output_buffer()
            s.flush()
            wait_prompt()
            s.write(f"{cmd[state]} {id}\r\n".encode())
            s.flush()
            output = ""

    s.write(b"y\r\n")  # confirm command
    s.write('\r\n'.encode('utf-8'))
    s.flush()

    if rpc_outlet_status(s, id) == state:
        return True

    return False

def rpc_outlet_on(s, id):
    return rpc_outlet_set(s, id, 1)

def rpc_outlet_off(s, id):
    return rpc_outlet_set(s, id, 0)

def rpc_outlet_status(s, id):
    output = wait_prompt()
    lines = output.splitlines()

    map = {}
    for line in lines:
        match = re.match(r"([1-6])\)\.{3}(.*): (On|Off)", line)
        if match:
            map[match.group(1)] = {"device": str.rstrip(match.group(2)), "state": match.group(3)}
    
    return str.lower(map[str(id)]['state']) == 'on'

def rpc_status_all(s):
    output = wait_prompt()
    lines = output.splitlines()

    map = {}
    for line in lines:
        match = re.match(r"([1-6])\)\.{3}(.*): (On|Off)", line)
        if match:
            map[match.group(1)] = {"device": str.rstrip(match.group(2)), "state": match.group(3)}
    
    return map
        

s = serial.Serial('/dev/ttyr00', baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=2)

print(rpc_outlet_on(s,1))
print(rpc_outlet_on(s,2))
print(rpc_outlet_on(s,3))
print(rpc_outlet_on(s,4))
time.sleep(30)
print(rpc_outlet_off(s,1))
print(rpc_outlet_off(s,2))
print(rpc_outlet_off(s,3))
print(rpc_outlet_off(s,4))


