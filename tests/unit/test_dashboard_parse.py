"""Dashboard log parsing on both log formats (old: unix seconds + buggy counter, new: GPS seconds + ns)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "dashboard"))
import logparse as lp                                          # noqa: E402

RUN_LOG = """\
2025-12-13 01:35:00,832 - RunManager::submit - INFO - start FD run
2025-12-13 01:35:00,838 - RunFD::prepare - INFO - prepare
2025-12-13 01:35:28,631 - RunFD::prepare - INFO - laser setup
2025-12-13 01:35:53,823 - RunFD::prepare - INFO - done
2025-12-13 01:35:53,823 - RunFD::prepare - INFO - laser warmup and wait for laser fire auth
2025-12-13 01:36:11,703 - RunFD::prepare - INFO - done
2025-12-13 01:36:31,578 - RunFD::run - INFO - start FD Run
2025-12-13 01:36:32,375 - RunFD::run - INFO - power 0 shot: 2.5300E-04, seconds: 1765528037, counter: 35028254, pps distance: -20ns, counter cycle: 50
2025-12-13 01:36:33,375 - RunFD::run - INFO - power 1 shot: 2.8000E-04, seconds: 0, counter: 0, pps distance: 0ns, counter cycle: 0
2025-12-13 01:36:34,375 - RunFD::run - INFO - power 2 shot: 2.9500E-04, seconds: 1765589793, counter: 35028254, pps distance: -20ns, counter cycle: 3
2025-12-13 01:36:35,375 - RunFD::run - INFO - power 3 shot: -1, seconds: 1765589794, counter: 35028274, pps distance: -10ns, counter cycle: 4
2025-12-13 01:50:00,000 - RunManager::submit - ERROR - TANK run cannot start due to alarms [{'dev': 'dio', 'name': 'rain', 'value': True, 'alarm': True}]
2026-11-02 02:05:00,000 - RunManager::submit - INFO - start FD run
2026-11-02 02:06:30,000 - RunFD::run - INFO - start FD Run
2026-11-02 02:06:31,000 - RunFD::run - INFO - power 0 shot: 0.00045, gps_seconds: 1477620409, counter: 249994080.0, pps distance: -20.0ns, counter cycle: 1
2026-11-02 02:06:32,000 - RunFD::run - INFO - power 1 shot: nan, gps_seconds: 1477620410, counter: 249994080.0, pps distance: -20.0ns, counter cycle: 2
2026-11-02 02:07:00,000 - RunManager::kill - WARNING - FD run killed
"""

HK_LOG = """\
2026-10-21 18:00:02,170 - housekeeping - INFO -  battery1=14.42[V] rain=False[] t3=4193305.0[degC] gps_fix=True[]
2026-10-21 18:00:13,482 - housekeeping - INFO -  battery1=14.36[V] rain=True[] t3=4193305.0[degC] gps_fix=True[]
2026-10-21 18:00:20,000 - housekeeping - WARNING - host clock - GPS = +1.003 s (PPS): check NTP
"""


@pytest.fixture
def logs(tmp_path):
    (tmp_path / "run.log").write_text(RUN_LOG)
    (tmp_path / "hk.log").write_text(HK_LOG)
    return str(tmp_path)


def test_runs_old_and_new_format(logs):
    runs, refusals, kills = lp.parse_runs(logs)
    old, new = runs
    assert old["type"] == "FD" and old["n_shots"] == 4
    assert old["n_packet"] == 3 and old["n_stale"] == 1              # shot 0: packet of the night before
    assert old["n_wrong"] == 0 and old["n_power_bad"] == 1           # -1
    assert old["laser_setup_s"] == pytest.approx(25.192) and old["fire_auth_s"] == pytest.approx(17.88)
    assert old["prepare_s"] == pytest.approx(90.746)
    # old buggy counter 35028254 -> tick 34999xxx (XLF FD, 350 ms); t_gps = tick*10 - (pps - 10)
    s2 = old["shots"][2]
    assert s2["t_gps_ns"] == pytest.approx(349_994_500 + 30, abs=5_000)
    assert new["n_shots"] == 2 and new["n_packet"] == 2 and new["n_stale"] == 0 and new["n_wrong"] == 0
    assert new["shots"][0]["t_gps_ns"] == pytest.approx(249_994_080 + 30)
    assert new["n_power_bad"] == 1                                   # nan
    assert new["status"] == "killed"
    assert refusals == [{"t": pytest.approx(lp._epoch("2025-12-13 01:50:00", "000")), "type": "TANK",
                         "reason": "alarm", "alarms": ["rain"]}]


def test_hk_values_and_invalid(logs):
    t = lp._epoch("2026-10-21 18:00:02", "170")
    hk = lp.parse_hk(logs, t - 60, t + 60)
    assert hk["battery1"]["unit"] == "V" and not hk["battery1"]["bool"]
    assert hk["rain"]["bool"] and max(v for v in hk["rain"]["v"] if v is not None) == 1.0
    assert all(v is None for v in hk["t3"]["v"])                    # 4193305 C = faulted channel


def test_events_from_all_logs(logs):
    events, all_events = lp.parse_events(logs, 0, 2e9)
    files = {e["file"] for e in all_events}
    assert files == {"run.log", "hk.log"}
    assert any(e["level"] == "ERROR" and "rain" in e["msg"] for e in all_events)


def test_night_of():
    assert lp.night_of(lp._epoch("2025-12-13 01:36:32", "0")) == "2025-12-12"
    assert lp.night_of(lp._epoch("2025-12-12 23:10:00", "0")) == "2025-12-12"


def test_epoch_matches_strptime():
    import datetime as dt
    for s, ms in (("2025-12-13 01:36:32", "375"), ("2024-02-29 23:59:59", "999"), ("2026-01-01 00:00:00", "0")):
        ref = dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp()
        assert lp._epoch(s, ms) == pytest.approx(ref + int(ms) / 1000)


def test_old_rotated_files_outside_the_range_are_not_read(tmp_path, monkeypatch):
    for name in ("hk.log.2024-03-01", "hk.log.2026-10-19", "hk.log.2026-10-20", "hk.log.oddname", "hk.log"):
        (tmp_path / name).write_text(HK_LOG)
    t = lp._epoch("2026-10-21 18:00:02", "170")
    names = [os.path.basename(p) for p in lp._files(str(tmp_path), "hk.log", t - 3 * 86400)]
    assert names == ["hk.log.2026-10-19", "hk.log.2026-10-20", "hk.log.oddname", "hk.log"]
    assert len(lp._files(str(tmp_path), "hk.log")) == 5           # no range: all of them

    read = []
    monkeypatch.setattr(lp, "_parse_hk_file", lambda p, real=lp._parse_hk_file: read.append(p) or real(p))
    lp.hk_rows(str(tmp_path), t - 86400, t + 60)
    assert not any(p.endswith("2024-03-01") for p in read)


def test_events_keep_only_warnings_and_errors(tmp_path):
    (tmp_path / "device.log").write_text(
        "2026-10-21 18:00:00,000 - VXM::cmd - DEBUG - lots of dialogue\n"
        "2026-10-21 18:00:01,000 - VXM::cmd - WARNING - no answer\n")
    assert [(e[3], e[4]) for e in lp._parse_events_file(str(tmp_path / "device.log"))] == [("WARNING", "no answer")]
