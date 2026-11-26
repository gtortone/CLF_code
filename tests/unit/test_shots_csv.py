"""logs/shots.csv: one row per shot, fixed columns, header in every file (lib/ShotsCsv.py)."""

import csv
import datetime
import io
import logging
import logging.handlers
import os
import sys

import pytest

from lib import ShotsCsv
from lib.FPGAData import Packet
from lib.GpsTime import unix_to_gps
from lib.Run import RunCalib, RunFD
from fakes import FakeDC

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "dashboard"))
import logparse as lp                                          # noqa: E402

# conftest replaces TimedRotatingFileHandler with a no-file handler: the real one is needed here
from conftest import REAL_TIMED_ROTATING_FILE_HANDLER as REAL_TRFH          # noqa: E402


class RealCsvHandler(ShotsCsv.HeaderMixin, REAL_TRFH):
    pass


T0 = 1_735_689_600


class Rad:
    def __init__(self, values):
        self.values = list(values)

    def setup(self):
        pass

    def flush_buffers(self):
        pass

    def discard_pending(self):
        return []

    def read_power(self, start=None):
        return self.values.pop(0)


class Data:
    def __init__(self, missing=()):
        self.missing = missing

    def flush(self):
        pass

    def read_shot(self, n, timeout_s):
        if n in self.missing:
            return None
        return Packet(T0 + n, 249_994_500.4, -20.2, n, "")


def _run(cls, rads, missing=()):
    dc = FakeDC()
    dc.data = Data(missing)
    dc.get_radiometer = lambda name: rads[name]
    run = cls(dc, {"identity": "clf", "clf": {}})
    run.log = lambda *a, **kw: None
    out = io.StringIO()
    run.shots_csv = logging.getLogger(f"test_shots_{id(out)}")
    run.shots_csv.propagate = False
    h = logging.StreamHandler(out)
    h.setFormatter(logging.Formatter("%(message)s"))
    run.shots_csv.addHandler(h)
    run.shots_csv.setLevel(logging.INFO)
    return run, out


def _rows(out):
    return list(csv.DictReader(io.StringIO(ShotsCsv.HEADER + "\n" + out.getvalue())))


def test_fd_rows():
    run, out = _run(RunFD, {"Rad1": Rad([0.5, float("nan")])}, missing=(2,))
    run.run_id = "FD-1735689000"
    run.log_shot(0, "Rad1")
    run.log_shot(1, "Rad1")
    r = _rows(out)
    assert [k for k in r[0]] == ShotsCsv.COLUMNS
    assert (r[0]["run_id"], r[0]["run_type"], r[0]["series"], r[0]["shot"]) == ("FD-1735689000", "FD", "", "0")
    assert r[0]["gps_seconds"] == str(unix_to_gps(T0 + 1))
    assert (r[0]["counter_ns"], r[0]["pps_delta_ns"], r[0]["counter_cycle"]) == ("249994500", "-20", "1")
    assert (r[0]["power_rad1"], r[0]["power_rad3"]) == ("0.5", "")     # Rad3 not read in FD
    # shot without FPGA packet and without reading
    assert (r[1]["gps_seconds"], r[1]["counter_ns"], r[1]["counter_cycle"]) == ("0", "0", "0")
    assert r[1]["power_rad1"] == "nan"
    datetime.datetime.strptime(r[0]["utc"], "%Y-%m-%dT%H:%M:%S.%f")


def test_calib_rows_have_both_radiometers_and_series():
    run, out = _run(RunCalib, {"Rad3": Rad([2.5e-3, 2.6e-3]), "Rad1": Rad([1.25, 1.3])})
    run.series = "energy"
    run.log_shot(0, "Rad3", also=("Rad1",))
    run.series = "pol90"
    run.log_shot(0, "Rad3", also=("Rad1",))
    r = _rows(out)
    assert [(x["run_type"], x["series"]) for x in r] == [("CALIB", "energy"), ("CALIB", "pol90")]
    assert (r[0]["power_rad3"], r[0]["power_rad1"]) == ("0.0025", "1.25")
    assert float(r[1]["power_rad3"]) / float(r[1]["power_rad1"]) == pytest.approx(2.0e-3)


def test_calib_run_sets_the_series(monkeypatch):
    import lib.Run as run_module
    monkeypatch.setattr(run_module.time, "sleep", lambda s: None)
    n = RunCalib(FakeDC(), {"identity": "clf", "clf": {}}).nshots
    run, out = _run(RunCalib, {"Rad3": Rad([1.0] * 4 * n), "Rad1": Rad([2.0] * 4 * n)})
    run.run()
    series = [x["series"] for x in _rows(out)]
    assert series == ["energy"] * n + ["pol0"] * n + ["pol90"] * n + ["pol180"] * n


def test_csv_failure_never_stops_the_run():
    run, out = _run(RunFD, {"Rad1": Rad([0.5])})
    errors = []
    run.log = lambda lvl, msg, **kw: errors.append(msg) if lvl == logging.ERROR else None

    class Broken:
        def info(self, msg):
            raise OSError("disk full")
    run.shots_csv = Broken()
    run.log_shot(0, "Rad1")
    assert any("shots.csv not written" in e for e in errors)


def test_run_type_from_class():
    assert RunFD(FakeDC(), {"identity": "clf", "clf": {}}).run_type == "FD"
    assert RunCalib(FakeDC(), {"identity": "clf", "clf": {}}).run_type == "CALIB"


# --- file: header in every file, also after the 18:00 rotation ---------------------------

def test_header_written_once_then_rows(tmp_path):
    path = tmp_path / "shots.csv"
    h = RealCsvHandler(str(path), ShotsCsv.HEADER, when="midnight", atTime=datetime.time(18, 0))
    h.setFormatter(logging.Formatter("%(message)s"))
    rec = lambda msg: logging.LogRecord("x", logging.INFO, "", 0, msg, None, None)
    h.emit(rec("row1"))
    h.close()
    h = RealCsvHandler(str(path), ShotsCsv.HEADER, when="midnight", atTime=datetime.time(18, 0))
    h.setFormatter(logging.Formatter("%(message)s"))
    h.emit(rec("row2"))                 # existing file: no second header
    h.doRollover()
    h.emit(rec("row3"))                 # new file after the rotation: header again
    h.close()
    rotated = [p for p in tmp_path.iterdir() if p.name != "shots.csv"]
    assert len(rotated) == 1
    assert rotated[0].read_text().splitlines() == [ShotsCsv.HEADER, "row1", "row2"]
    assert path.read_text().splitlines() == [ShotsCsv.HEADER, "row3"]


# --- run_id = the dashboard's run id -----------------------------------------------------

def test_run_id_matches_dashboard(monkeypatch, tmp_path):
    from lib import RunManager as rm_module
    from lib.RunCalendar import RunEntry
    from lib.Run import RunType

    rm = rm_module.RunManager.__new__(rm_module.RunManager)
    rm.dc, rm.params = FakeDC(), {"identity": "clf", "clf": {}}
    rm.job, rm.runentry, rm.run = None, None, None
    rm.scheduler_powered = False
    rm.hk = type("HK", (), {"get_alarm": lambda self: []})()
    lines = []
    rm.log = lambda lvl, msg, **kw: lines.append((datetime.datetime.now(), msg))
    monkeypatch.setattr(rm_module.multiprocessing, "Process",
                        lambda target, args: type("P", (), {"start": lambda self: None})())
    assert rm.submit(RunEntry(datetime.datetime.now(), RunType.FD, False, False), "cli")

    t, msg = lines[-1]
    log_line = f"{t:%Y-%m-%d %H:%M:%S},{t.microsecond // 1000:03d} - RunManager::submit - INFO - {msg}\n"
    (tmp_path / "run.log").write_text(log_line)
    runs, _, _ = lp.parse_runs(str(tmp_path))
    assert runs[0]["id"] == rm.run.run_id
