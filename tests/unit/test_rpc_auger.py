"""RPC_Auger (lib/RPC_Auger.py) against a fake board, and its selection in DeviceCollection."""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from lib import DeviceCollection as dcmod
from lib.RPC_Auger import RPCError, RPCAugerDevice

AUTH = "Basic " + base64.b64encode(b"admin:admin").decode()


class FakeBoard:
    """Replies like the board: /output/OUT<n>/<on|off>, /status (with the unused ADC data)."""

    def __init__(self):
        self.outputs = {f"OUT{i}": 0 for i in range(1, 7)}
        self.enable = 1
        self.stuck = set()          # outputs that answer but do not switch
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body):
                data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                fake.requests.append(self.path)
                if self.headers.get("Authorization") != AUTH:
                    return self._send(401, {"error": "unauthorized"})
                parts = self.path.strip("/").split("/")
                if parts == ["status"]:
                    return self._send(200, {"outputs": fake.outputs, "enable": fake.enable,
                                            "adc_mode": "internal",
                                            "voltages": {"AN0": 1.798, "AN1": 1.798}})
                if len(parts) == 3 and parts[0] == "output" and parts[1] in fake.outputs \
                        and parts[2] in ("on", "off"):
                    if parts[1] not in fake.stuck:
                        fake.outputs[parts[1]] = int(parts[2] == "on")
                    return self._send(200, {parts[1]: parts[2]})
                return self._send(404, {"error": "not found"})

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.ip, self.port = "127.0.0.1", self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def board():
    b = FakeBoard()
    yield b
    b.server.shutdown()
    b.server.server_close()


def test_on_off_status(board):
    rpc = RPCAugerDevice(board.ip, board.port)
    laser = rpc.add_outlet(3, "laser")
    assert laser.status() is False
    assert laser.on() is True
    assert board.outputs["OUT3"] == 1 and laser.status() is True
    assert laser.off() is True
    assert board.outputs["OUT3"] == 0
    assert "/output/OUT3/on" in board.requests and "/output/OUT3/off" in board.requests


def test_only_the_selected_output_changes(board):
    rpc = RPCAugerDevice(board.ip, board.port)
    rpc.add_outlet(2, "radiometer").on()
    assert [k for k, v in board.outputs.items() if v] == ["OUT2"]


def test_output_that_does_not_switch_returns_false(board):
    board.stuck.add("OUT1")
    assert RPCAugerDevice(board.ip, board.port).add_outlet(1, "RAMAN_inst").on() is False


def test_wrong_password(board):
    outlet = RPCAugerDevice(board.ip, board.port, password="wrong").add_outlet(1, "x")
    assert outlet.on() is False
    with pytest.raises(RPCError):
        outlet.status()


def test_board_not_answering_is_an_error_not_off():
    outlet = RPCAugerDevice("127.0.0.1", 9, timeout=0.5).add_outlet(1, "x")
    with pytest.raises(RPCError):          # never guessed as "off"
        outlet.status()
    assert outlet.on() is False


def test_unknown_output(board):
    with pytest.raises(RPCError):
        RPCAugerDevice(board.ip, board.port).add_outlet(7, "x").status()


# --- selection in DeviceCollection -------------------------------------------------------

class Cfg:
    def __init__(self, ports, outlets):
        self.ports, self.outlets = ports, outlets

    def get_port_params(self, port):
        return self.ports.get(port)


def _collection():
    dc = dcmod.DeviceCollection.__new__(dcmod.DeviceCollection)
    dc.serials, dc.outlets, dc.motors, dc.radiometers = {}, {}, {}, {}
    return dc


def _init_outlets(dc, cfg):
    dc.init_outlets(cfg)


OUTLETS = {"RAMAN_inst": {"port": "RPC", "id": 1}, "laser": {"port": "RPC", "id": 3}}


def test_rpc_auger_type(board):
    dc = _collection()
    _init_outlets(dc, Cfg({"RPC": {"type": "RPC_Auger", "ip": board.ip, "port": board.port, "user": "admin",
                                   "password": "admin", "timeout": 3}}, OUTLETS))
    assert len(dc.serials) == 1                         # one board for all outlets
    assert dc.get_outlet("laser").on() is True and board.outputs["OUT3"] == 1


def test_no_type_uses_old_serial_rpc(monkeypatch):
    made = []

    class FakeSerialRPC:
        def __init__(self, **params):
            made.append(params)

        def add_outlet(self, id, name):
            return (id, name)
    monkeypatch.setattr(dcmod, "RPCDevice", FakeSerialRPC)
    for ports in ({"RPC": {"port": "/dev/ttyr00", "baudrate": 9600}},
                  {"RPC": {"type": "serial", "port": "/dev/ttyr00", "baudrate": 9600}}):
        made.clear()
        dc = _collection()
        _init_outlets(dc, Cfg(ports, OUTLETS))
        assert made == [{"port": "/dev/ttyr00", "baudrate": 9600, "bytesize": 8, "parity": "N",
                         "stopbits": 1, "timeout": 1}]
        assert dc.get_outlet("laser") == (3, "laser")


def test_site_confs_still_serial():
    """CLF and XLF keep the serial RPC until the RPC_Auger block in ports.yml is enabled."""
    import os
    import yaml
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for site in ("clf", "xlf"):
        with open(os.path.join(root, "conf", site, "ports.yml")) as f:
            ports = {k: v for doc in yaml.safe_load_all(f) for k, v in doc.items()}
        assert ports["RPC"].get("type", "serial") == "serial"
