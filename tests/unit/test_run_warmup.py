"""Laser warm-up run: in the calendar before the first run of the night, and what it does."""

import datetime

import pytest

import lib.Run as run_module
from lib.FPGAData import Packet
from lib.Run import RunType, RunWarmup
from lib.RunCalendar import CalendarEntry, RunCalendar

from fakes import FakeDC

NIGHT = CalendarEntry(start_date=datetime.datetime(2026, 11, 26, 0, 30),
                      end_date=datetime.datetime(2026, 11, 26, 8, 30), has_fd_run=True)
CLF = {"run_list": ["fd", "tank", "raman", "calib"], "start_minutes": [5, 20, 35, 50]}
XLF = {"run_list": ["fd", "tank", "calib"], "start_minutes": [5, 20, 35, 50]}


def timetable(identity, site):
    rc = RunCalendar.__new__(RunCalendar)
    rc.params = {"identity": identity, identity: site}
    rc.identity = identity
    return rc.get_timetable_for_entry(NIGHT)


def test_clf_warmup_30_min_before_the_first_raman():
    tt = timetable("clf", CLF)
    assert tt[0].runtype == RunType.WARMUP and tt[0].first
    assert tt[1].runtype == RunType.RAMAN and not tt[1].first
    assert tt[1].start_time - tt[0].start_time == datetime.timedelta(minutes=30)
    assert tt[0].start_time == datetime.datetime(2026, 11, 25, 23, 30)
    assert sum(r.runtype == RunType.WARMUP for r in tt) == 1
    assert tt[-1].runtype == RunType.CALIB and tt[-1].last


def test_xlf_warmup_30_min_before_the_first_run():
    tt = timetable("xlf", XLF)
    assert tt[0].runtype == RunType.WARMUP
    assert tt[1].start_time - tt[0].start_time == datetime.timedelta(minutes=30)
    assert tt[1].runtype in (RunType.FD, RunType.TANK)


def test_warmup_minutes_from_parameters_and_disabled_with_zero():
    tt = timetable("clf", dict(CLF, warmup_before_min=45))
    assert tt[1].start_time - tt[0].start_time == datetime.timedelta(minutes=45)
    tt = timetable("clf", dict(CLF, warmup_before_min=0))
    assert tt[0].runtype == RunType.RAMAN and tt[0].first


# --- the run --------------------------------------------------------------------------

class Data:
    def __init__(self):
        self.read = []

    def flush(self):
        pass

    def read_shot(self, n, timeout_s):
        self.read.append(n)
        return Packet(1_735_689_600 + n, 249_994_500, -20, n, "")


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setattr(run_module.time, "sleep", lambda s: None)
    dc = FakeDC()
    dc.data = Data()
    r = RunWarmup(dc, {"identity": "clf", "clf": {"fd_trigger_ms": 249.99411}})
    r.sync_time = lambda: True
    r.lines = []
    r.log = lambda lvl, msg, **kw: r.lines.append(msg)
    return r


def test_warmup_sequence(run):
    dc = run.dc
    assert run.prepare() == 0
    run.run()
    ev = dc.events
    # everything powered, laser warm, fire mode only after the hold, back to standby
    assert dc.fpga.dio["inverter"] is True
    assert {("outlet_on", o) for o in ("radiometer", "laser", "VXM")} <= set(ev)
    assert ev.index(("laser", "warmup")) < ev.index(("laser", "fire"))
    assert ("laser", "standby") in ev[ev.index(("laser", "fire")):]
    text = [l for l in run.lines if isinstance(l, str)]       # (laser temperatures are tuples)
    assert "hold laser warm for 5 min" in text
    # 20 test shots, logged
    assert dc.data.read == list(range(1, 21))
    assert sum(l.startswith("power ") for l in text) == 20
    assert dc.fpga.registers["shots_num"] == 20
    # no cover, no flipper, nothing switched off
    assert not any(e[0] == "outlet_on" and "cover" in e[1].lower() for e in ev)
    assert "flipper_raman" not in dc.fpga.dio
    assert not any(e[0] == "outlet_off" for e in ev)
    assert dc.fpga.dio["laser_en"] is False


def test_warmup_fire_refused_goes_to_standby_without_shots(run):
    run.dc.laser.fire = lambda: -1
    assert run.prepare() == 0
    run.run()
    assert run.dc.data.read == []
    assert run.dc.events[-1] == ("laser", "standby")


def test_warmup_abort_switches_everything_off(run):
    run.prepare()
    run.abort()
    ev = run.dc.events
    assert ("laser", "standby") in ev
    assert {("outlet_off", o) for o in ("radiometer", "laser", "VXM")} <= set(ev)
    assert run.dc.fpga.dio["inverter"] is False
