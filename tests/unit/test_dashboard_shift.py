"""Shift tab of the dashboard (dashboard/shift.py): scheduled vs started runs, timing,
energy, grouping of the problems, and the /api/shift endpoint."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "dashboard"))
import shift                                                   # noqa: E402

T = 1_764_000_000.0          # some night


def run(typ, start, status="ok", n_shots=50, good=100.0, t_gps_ms=250.0, power=1.0e-3):
    return {"id": f"{typ}-{int(start)}", "type": typ, "start": start, "end": start + 120, "status": status,
            "errors": ["boom"] if status == "error" else [], "n_shots": n_shots, "good_pct": good,
            "t_gps_ms": t_gps_ms, "power_median": power}


def states(rows):
    return [(x["type"], x["state"]) for x in rows]


# --- schedule ---------------------------------------------------------------------------

def test_schedule_states():
    expected = [(T, "FD"), (T + 900, "FD"), (T + 1800, "TANK"), (T + 2700, "FD"), (T + 9000, "FD")]
    runs = shift.run_checks([run("FD", T + 2), run("TANK", T + 1830), run("FD", T + 5000)])
    refusals = [{"t": T + 2700, "type": "FD", "reason": "alarm", "alarms": ["rain"]}]
    now = T + 8000
    rows = shift.schedule(expected, runs, refusals, now)
    assert states(rows) == [("FD", "done"), ("FD", "missing"), ("TANK", "done"), ("FD", "refused"),
                            ("FD", "manual"), ("FD", "waiting" if now >= T + 9000 else "scheduled")]
    assert rows[3]["refusal"]["alarms"] == ["rain"]
    assert [x["planned"] for x in rows] == [True, True, True, True, False, True]


def test_running_run_is_not_a_problem():
    runs = shift.run_checks([run("FD", T, status="no shots", n_shots=0)])
    rows = shift.schedule([(T, "FD")], runs, [], now=T + 130)       # last line 10 s ago
    assert states(rows) == [("FD", "running")]


def test_waiting_then_missing():
    assert states(shift.schedule([(T, "FD")], [], [], now=T + 60)) == [("FD", "waiting")]
    assert states(shift.schedule([(T, "FD")], [], [], now=T + 3600)) == [("FD", "missing")]


# --- per-run checks ---------------------------------------------------------------------

def test_timing_and_energy_checks():
    runs = shift.run_checks([run("FD", T), run("FD", T + 900, t_gps_ms=250.0005),     # +500 ns
                             run("FD", T + 1800, good=80.0), run("FD", T + 2700, power=1.1e-3),
                             run("FD", T + 3600)])
    assert [r["timing_ok"] for r in runs] == [True, False, False, True, True]
    assert runs[1]["timing_dev_ns"] == pytest_approx(500)
    assert [r["energy_ok"] for r in runs] == [True, True, True, False, True]
    assert runs[3]["energy_dev_pct"] == pytest_approx(10.0)


def test_calib_energy_not_compared():
    runs = shift.run_checks([run("CALIB", T, power=5e-3), run("RAMAN", T + 100, n_shots=0, power=None)])
    assert runs[0]["energy_ok"] is None and runs[0]["timing_ok"] is True
    assert runs[1]["timing_ok"] is None and runs[1]["energy_ok"] is None


def pytest_approx(v):
    import pytest
    return pytest.approx(v, abs=1e-6)


# --- summary ----------------------------------------------------------------------------

TIMEREF_OK = {"total_s": 40000, "bad_s": 0, "periods": [], "tacc_max": 20, "lock_lost": [], "lock_known": True}


def test_all_ok():
    expected = [(T + i * 900, "FD") for i in range(4)]
    runs = [run("FD", t + 1) for t, _ in expected]
    s = shift.summary(expected, runs, [], TIMEREF_OK, T + 4000, T + 4000, T - 3600, T + 80000)
    assert s["level"] == "ok" and s["problems"] == []
    assert s["runs"]["started"] == 4 and s["runs"]["expected_so_far"] == 4
    assert s["timing"] == {"runs": 4, "ok": 4, "good_pct_min": shift.GOOD_PCT_MIN, "dev_max_ns": shift.TIMING_DEV_NS}
    assert s["gps"]["ok"] and s["gps"]["lock_lost"] == 0


def test_problems_and_level():
    expected = [(T, "FD"), (T + 900, "FD")]
    runs = [run("FD", T + 1, status="killed")]
    timeref = dict(TIMEREF_OK, bad_s=900, periods=[[T, T + 900]])
    s = shift.summary(expected, runs, [], timeref, T + 4000, T + 4000, T - 3600, T + 80000)
    assert s["level"] == "bad"
    texts = [p["text"] for p in s["problems"]]
    assert texts[0].startswith("GPS without fix")
    assert any("never started" in t for t in texts) and any("killed" in t for t in texts)


def test_many_runs_with_the_same_problem_are_one_line():
    expected = [(T + i * 900, "FD") for i in range(10)]
    runs = [run("FD", t + 1, good=0.0, t_gps_ms=None) for t, _ in expected]
    s = shift.summary(expected, runs, [], TIMEREF_OK, T + 9500, T + 9500, T - 3600, T + 80000)
    assert s["level"] == "warn"
    assert len(s["problems"]) == 1
    assert s["problems"][0]["text"].startswith("10 runs with shots not on time: FD ")


def test_logs_stopped_during_the_night():
    s = shift.summary([], [], [], None, last_log_t=T, now=T + 7200, t_from=T - 3600, t_to=T + 80000)
    assert s["level"] == "bad" and "PC or main.py down" in s["problems"][0]["text"]
    # an old night: no such check
    s = shift.summary([], [], [], None, last_log_t=T, now=T + 10 * 86400, t_from=T - 3600, t_to=T + 80000)
    assert s["level"] == "ok"


# --- endpoint -----------------------------------------------------------------------------

def test_api_shift(tmp_path, monkeypatch):
    import app as dash
    (tmp_path / "run.log").write_text(
        "2025-11-25 01:05:00,100 - RunManager::submit - INFO - start FD run\n"
        "2025-11-25 01:05:31,375 - RunFD::run - INFO - power 0 shot: 0.00022, gps_seconds: 1448067949, "
        "counter: 249994500, pps distance: -20ns, counter cycle: 1\n")
    monkeypatch.setitem(dash.app.config, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(dash, "_params", lambda: {})
    c = dash.app.test_client()
    d = c.get("/api/shift").get_json()
    assert d["night"] == "2025-11-24" and d["latest_night"] == "2025-11-24"
    assert [(x["type"], x["state"]) for x in d["schedule"]] == [("FD", "manual")]
    assert c.get("/api/shift?night=2025-11-23").get_json()["schedule"] == []
    assert c.get("/api/shift?night=bad").status_code == 400
    assert c.get("/api/data?days=3").status_code == 200
