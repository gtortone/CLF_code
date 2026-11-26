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


class Clock:
    """time.monotonic / time.sleep of lib.Run: a shot takes 1 s, sleeps advance the clock."""
    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.t += s


class Rad:
    """Rad1 giving the energies of `batches` (one list per batch of 10, then the last again)."""
    def __init__(self, batches, clock):
        self.batches, self.clock, self.n = batches, clock, 0

    def setup(self):
        pass

    def flush_buffers(self):
        pass

    def discard_pending(self):
        return []

    def read_power(self, start=None):
        batch = self.batches[min(self.n // 10, len(self.batches) - 1)]
        v = batch[self.n % 10]
        self.n += 1
        self.clock.t += 1.0
        return v


@pytest.fixture
def make_run(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(run_module.time, "sleep", clock.sleep)
    monkeypatch.setattr(run_module.time, "monotonic", clock.monotonic)

    def make(batches=([1.0] * 10,), site=None):
        dc = FakeDC()
        dc.data = Data()
        rad = Rad(list(batches), clock)
        dc.get_radiometer = lambda name: rad
        r = RunWarmup(dc, {"identity": "clf", "clf": dict({"fd_trigger_ms": 249.99411}, **(site or {}))})
        r.sync_time = lambda: True
        r.lines = []
        r.log = lambda lvl, msg, **kw: r.lines.append(msg)
        r.clock = clock
        return r
    return make


@pytest.fixture
def run(make_run):
    return make_run()


def text(run):
    return [l for l in run.lines if isinstance(l, str)]       # (laser temperatures are tuples)


def test_warmup_sequence(run):
    dc = run.dc
    assert run.prepare() == 0
    run.run()
    ev = dc.events
    # everything powered, laser warm, fire mode, back to standby
    assert dc.fpga.dio["inverter"] is True
    assert {("outlet_on", o) for o in ("radiometer", "laser", "VXM")} <= set(ev)
    assert ev.index(("laser", "warmup")) < ev.index(("laser", "fire"))
    assert ("laser", "standby") in ev[ev.index(("laser", "fire")):]
    # constant energy: stable at the second batch (the first has nothing to compare with)
    assert dc.data.read == list(range(1, 11)) * 2
    assert sum(l.startswith("power ") for l in text(run)) == 20
    assert dc.fpga.registers["shots_num"] == 10
    assert "laser energy stable after 2 batches" in text(run)
    # no cover, no flipper, nothing switched off
    assert not any(e[0] == "outlet_on" and "cover" in e[1].lower() for e in ev)
    assert "flipper_raman" not in dc.fpga.dio
    assert not any(e[0] == "outlet_off" for e in ev)
    assert dc.fpga.dio["laser_en"] is False


def test_energy_still_rising_takes_more_batches(make_run):
    rising = [[v] * 10 for v in (0.80, 0.90, 0.95, 0.96)]        # +12.5 %, +5.6 %, +1.1 %
    r = make_run(rising)
    r.prepare()
    r.run()
    assert len(r.dc.data.read) == 40                            # stable at batch 4 (+1.1 %)
    assert any(l.startswith("batch 4:") and l.endswith("-> stable") for l in text(r))
    assert any(l.startswith("batch 3:") and l.endswith("-> not stable yet") for l in text(r))
    assert "wait 60 s" in text(r)


def test_noisy_energy_is_not_stable(make_run):
    noisy = [[1.0, 1.2] * 5]                                     # spread ~9 %
    r = make_run(noisy, site={"warmup_max_min": 5})
    r.prepare()
    r.run()
    assert not any("energy stable after" in l for l in text(r))
    assert any("not stable within 5 min" in l for l in text(r))


def test_missing_readings_are_not_stable(make_run):
    r = make_run([[float("nan")] * 5 + [1.0] * 5], site={"warmup_max_min": 3})
    r.prepare()
    r.run()
    assert any(l.startswith("batch 1: 5/10 readings") for l in text(r))
    assert any("not stable within 3 min" in l for l in text(r))


def test_time_limit_default_15_min(make_run):
    r = make_run([[v] * 10 for v in [0.5 + 0.05 * k for k in range(100)]])   # always rising
    assert r.max_s == 15 * 60
    r.prepare()
    t0 = r.clock.t
    r.run()
    assert r.clock.t - t0 <= 15 * 60                             # never past the limit
    assert any("not stable within 15 min" in l for l in text(r))
    assert r.dc.events[-1] == ("laser", "standby")               # back to standby, nothing off
    assert not any(e[0] == "outlet_off" for e in r.dc.events)


def test_batches_in_shots_csv(make_run):
    r = make_run()
    rows = []
    r.shots_csv = type("L", (), {"info": lambda self, row: rows.append(row)})()
    r.prepare()
    r.run()
    assert [row.split(",")[3] for row in rows] == ["batch1"] * 10 + ["batch2"] * 10


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
