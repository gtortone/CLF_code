"""
RPC_Auger: power outlets on the custom board made by the Auger staff (Luckfox, HTTP
server), same interface as the old serial RPC in lib/RPC.py.

    GET /output/OUT<n>/on   -> {"OUT<n>": "on"}
    GET /output/OUT<n>/off  -> {"OUT<n>": "off"}
    GET /status             -> {"outputs": {"OUT1": 0, ..., "OUT6": 0}, "enable": 1, ...}

HTTP basic authentication. The ADC readings in /status are not used.

Selected in conf/<site>/ports.yml with `type: RPC_Auger` on the RPC port, address in `ip`
and `port` (see DeviceCollection); without `type` the old serial RPC is used.
"""

import base64
import json
import datetime
import logging
import urllib.error
import urllib.request
from functools import partial
from logging.handlers import TimedRotatingFileHandler

class RPCError(IOError):
    """The RPC_Auger did not answer or answered something unexpected."""

class RPCAugerDevice:

    def __init__(self, ip, port=8080, user="admin", password="admin", timeout=3):
        self.url = f"http://{ip}:{port}"
        self.timeout = timeout
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}"}
        self.outlets = {}

        self.logger = logging.getLogger("device")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            formatter = logging.Formatter('%(asctime)s - %(classname)s::%(funcName)s - %(levelname)s - %(message)s')
            handler = TimedRotatingFileHandler('logs/device.log', when='midnight',
                atTime=datetime.time(hour=18, minute=0))
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.log = partial(self.logger.log, extra={'classname': self.__class__.__name__})

    def _get(self, path):
        req = urllib.request.Request(self.url + path, headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except (urllib.error.URLError, OSError, ValueError) as e:  # HTTP error, timeout, bad JSON
            raise RPCError(f"RPC {self.url}{path}: {e}") from e

    def outputs(self):
        """State of all outputs, {'OUT1': True, ...}."""
        answer = self._get("/status")
        try:
            outputs = answer["outputs"]
        except (KeyError, TypeError):
            raise RPCError(f"RPC {self.url}/status: no 'outputs' in {answer!r}")
        if answer.get("enable", 1) != 1:
            self.log(logging.WARNING, f"RPC {self.url}: outputs not enabled (enable={answer.get('enable')})")
        return {k: bool(v) for k, v in outputs.items()}

    def add_outlet(self, id, name):
        self.outlets[name] = RPCAugerOutlet(self, id, name)
        return self.outlets[name]

    def get_outlet(self, name):
        return self.outlets[name]


class RPCAugerOutlet:

    def __init__(self, device, id, name=""):
        self.device = device
        self.id = id
        self.name = name
        self.output = f"OUT{id}"

    def status(self):
        """True if on. RPCError if the RPC does not answer (never guessed as off)."""
        outputs = self.device.outputs()
        if self.output not in outputs:
            raise RPCError(f"RPC {self.device.url}: {self.output} not in {sorted(outputs)}")
        return outputs[self.output]

    def set(self, state):
        cmd = "on" if state else "off"
        try:
            answer = self.device._get(f"/output/{self.output}/{cmd}")
            if answer.get(self.output) != cmd:
                self.device.log(logging.ERROR, f"RPC {self.output} ({self.name}) {cmd}: unexpected answer {answer!r}")
            if self.status() == bool(state):
                return True
            self.device.log(logging.ERROR, f"RPC {self.output} ({self.name}) {cmd}: state not changed")
        except (RPCError, AttributeError) as e:
            self.device.log(logging.ERROR, f"RPC {self.output} ({self.name}) {cmd} failed: {e}")
        return False

    def on(self):
        return self.set(1)

    def off(self):
        return self.set(0)

    def __repr__(self):
        return f"RPCAugerOutlet({self.output}, {self.name})"
