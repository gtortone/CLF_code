"""Calibration run: Rad3 and Rad1 read for every shot, ratio available in run.log."""

import os
import sys

from lib.FPGAData import Packet
from lib.Run import RunCalib, RunFD
from fakes import FakeDC

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "dashboard"))
import logparse as lp                                          # noqa: E402


class Rad:
    def __init__(self, name, values, events):
        self.name, self.values, self.events = name, list(values), events

    def setup(self):
        self.events.append(("setup", self.name))

    def flush_buffers(self):
        self.events.append(("flush", self.name))

    def discard_pending(self):
        self.events.append(("discard", self.name))
        return []

    def read_power(self, start=None):
        self.events.append(("read", self.name))
        return self.values.pop(0)


class Data:
    def flush(self):
        pass

    def read_shot(self, n, timeout_s):
        return Packet(1_735_689_600 + n, 249_994_500, -20, n, "")


def _dc(rad3_values, rad1_values):
    dc = FakeDC()
    dc.data = Data()
    rads = {"Rad3": Rad("Rad3", rad3_values, dc.events), "Rad1": Rad("Rad1", rad1_values, dc.events)}
    dc.get_radiometer = lambda name: rads[name]
    return dc


def _lines(run):
    lines = []
    run.log = lambda lvl, msg, **kw: lines.append(msg)
    return lines


def test_calib_shot_line_has_both_powers():
    dc = _dc([2.5e-3, float("nan")], [1.25, 1.30])
    run = RunCalib(dc, {"identity": "clf", "clf": {}})
    lines = _lines(run)
    run.start_shots('Rad3', 'Rad1')
    run.log_shot(0, 'Rad3', also=('Rad1',))
    run.log_shot(1, 'Rad3', also=('Rad1',))
    assert lines[0].startswith("power 0 shot: 0.0025, gps_seconds:")
    assert lines[0].endswith("counter cycle: 1, power Rad1: 1.25")
    assert lines[1].startswith("power 1 shot: nan,") and lines[1].endswith(", power Rad1: 1.3")
    # both flushed at start, both stale readings dropped before every shot
    assert ("flush", "Rad3") in dc.events and ("flush", "Rad1") in dc.events
    assert dc.events.count(("discard", "Rad1")) == 2


def test_other_runs_line_unchanged():
    dc = _dc([], [0.5])
    run = RunFD(dc, {"identity": "clf", "clf": {}})
    lines = _lines(run)
    run.log_shot(0, 'Rad1')
    assert lines[0].endswith("counter cycle: 1") and "power Rad1" not in lines[0]


def test_dashboard_still_parses_the_calib_line():
    msg = ("power 0 shot: 0.0025, gps_seconds: 1420000000, counter: 249994500, "
           "pps distance: -20ns, counter cycle: 1, power Rad1: 1.25")
    s = lp._shot(msg, 1735689601.0)
    assert s is not None and s["power"] == 0.0025 and s["cycle"] == 1


def test_calib_prepare_sets_up_rad1(monkeypatch):
    import lib.Run as run_module
    monkeypatch.setattr(run_module.time, "sleep", lambda s: None)
    dc = _dc([], [])
    run = RunCalib(dc, {"identity": "clf", "clf": {}})
    _lines(run)
    monkeypatch.setattr(run, "wait_laser_ready", lambda: True)
    monkeypatch.setattr(run, "sync_time", lambda: True)
    run.prepare()
    assert ("setup", "Rad3") in dc.events and ("setup", "Rad1") in dc.events
