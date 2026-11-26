"""
Shift view of the dashboard: few, clear answers for the night shifter.

    - did the scheduled runs start? (done / expected, and which ones)
    - are the shots on time? (valid timestamps, shot time vs the usual one)
    - is the laser energy stable? (each run vs the median of the range)
    - is the GPS ok? (fix, holdover, FPGA clock lock)
    - batteries and solar panels

Thresholds below; everything else (plots per run, events, housekeeping) is in the
"Details" tab.
"""

import collections
import os
import statistics
import sys

import logparse as lp

ROOT = lp.ROOT
sys.path.insert(0, os.path.join(ROOT, "tools"))
import night_report as nr                               # noqa: E402

GOOD_PCT_MIN = nr.GOOD_PCT_MIN      # valid shot timestamps per run, % (as the morning report)
TIMING_DEV_NS = 200                 # shot time vs the median of the same run type, ns
ENERGY_DEV_PCT = 5.0                # run energy vs the median of the same run type, %
GPS_BAD_MIN_S = nr.GPS_BAD_MIN_S    # GPS without fix / in holdover longer than this: problem
LOG_GAP_S = nr.LOG_GAP_S            # no new log line for this long during the night: problem

MATCH_BEFORE_S = 300                # a run started up to 5 min before its scheduled time ...
MATCH_AFTER_S = 1800                # ... or up to 30 min after it is that scheduled run
RUNNING_S = 180                     # last run with a log line this recent: still running

SHOT_TYPES = ("FD", "TANK", "CALIB", "WARMUP")     # runs with laser shots (log_shot)
ENERGY_TYPES = ("FD", "TANK")                     # Rad1, comparable from run to run
POWER_HK = ("battery", "solar")                   # hk names shown in the shift view

OK, WARN, BAD = "ok", "warn", "bad"


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def run_checks(runs):
    """Per run: timing (valid timestamps, shot time deviation) and energy deviation, each
    against the median of the runs of the same type in the range. Adds keys to the runs."""
    t_typ = {t: _median([r["t_gps_ms"] for r in runs if r["type"] == t]) for t in SHOT_TYPES}
    p_typ = {t: _median([r["power_median"] for r in runs if r["type"] == t]) for t in ENERGY_TYPES}
    for r in runs:
        r["timing_dev_ns"] = r["energy_dev_pct"] = None
        r["timing_ok"] = r["energy_ok"] = None                  # None: not applicable / no data
        if r["type"] in SHOT_TYPES and r["n_shots"]:
            if r["t_gps_ms"] is not None and t_typ[r["type"]] is not None:
                r["timing_dev_ns"] = (r["t_gps_ms"] - t_typ[r["type"]]) * 1e6
            r["timing_ok"] = (r["good_pct"] is not None and r["good_pct"] >= GOOD_PCT_MIN
                              and r["timing_dev_ns"] is not None and abs(r["timing_dev_ns"]) <= TIMING_DEV_NS)
        if r["type"] in ENERGY_TYPES and r["power_median"] and p_typ[r["type"]]:
            r["energy_dev_pct"] = 100.0 * (r["power_median"] / p_typ[r["type"]] - 1)
            r["energy_ok"] = abs(r["energy_dev_pct"]) <= ENERGY_DEV_PCT
    return runs


def schedule(expected, runs, refusals, now):
    """One row per scheduled run (+ runs started by hand), in time order:
    {"t", "type", "state", "run"}; state: done, problem, refused, missing, running,
    waiting (time reached, not started yet), scheduled (in the future), manual (not in
    the calendar: started by hand); "planned" False for the manual ones."""
    run_of = _match(expected, runs, lambda r: r["start"])
    refusal_of = _match(expected, refusals, lambda f: f["t"], skip=run_of)
    used = {id(r) for r in run_of.values()}
    rows = []
    for i, (t, typ) in enumerate(expected):
        run = run_of.get(i)
        row = {"t": t, "type": typ, "run": run, "refusal": None, "planned": True}
        if run:
            row["state"] = _run_state(run, now)
        else:
            if i in refusal_of:
                row["state"], row["refusal"] = "refused", refusal_of[i]
            elif now < t:
                row["state"] = "scheduled"
            elif now < t + MATCH_AFTER_S:
                row["state"] = "waiting"
            else:
                row["state"] = "missing"
        rows.append(row)
    for r in runs:
        if id(r) not in used:
            state = _run_state(r, now)
            rows.append({"t": r["start"], "type": r["type"], "run": r, "refusal": None, "planned": False,
                         "state": "running" if state == "running" else "manual"})
    rows.sort(key=lambda x: x["t"])
    return rows


def _match(expected, items, t_of, skip=()):
    """{index in expected: item} pairing each scheduled run (not in `skip`) with at most
    one item (run or refusal) of the same type within the window, closest pairs first: an
    item is never given to two scheduled runs, nor to a farther one when a closer one exists."""
    pairs = sorted((abs(t_of(it) - t), i, k)
                   for i, (t, typ) in enumerate(expected) if i not in skip
                   for k, it in enumerate(items)
                   if it["type"] == typ and t - MATCH_BEFORE_S <= t_of(it) <= t + MATCH_AFTER_S)
    out, taken = {}, set()
    for _, i, k in pairs:
        if i not in out and k not in taken:
            out[i] = items[k]
            taken.add(k)
    return out


def _run_state(run, now):
    if now - run["end"] < RUNNING_S and run["status"] in ("ok", "no shots"):
        return "running"
    bad = run["status"] != "ok" or run.get("timing_ok") is False or run.get("energy_ok") is False
    return "problem" if bad else "done"


def summary(expected, runs, refusals, timeref, last_log_t, now, t_from, t_to):
    """Answers of the shift view, with an overall level and the list of problems."""
    run_checks(runs)
    rows = schedule(expected, runs, refusals, now)
    problems = []                   # (level, text)
    per_run = collections.defaultdict(list)     # kind -> [(level, "FD 01:20", detail)]

    exp = collections.Counter(t for _, t in expected)
    planned = [x for x in rows if x["planned"]]
    started = collections.Counter(x["type"] for x in planned if x["state"] in ("done", "problem", "running"))
    missing = [x for x in rows if x["state"] == "missing"]
    for x in missing:
        per_run["missing"].append((BAD, f"{x['type']} {nr.utc(x['t'])}", "never started"))
    for x in rows:
        r = x["run"]
        if x["state"] == "refused":
            f = x["refusal"]
            why = ("alarm " + ", ".join(f["alarms"])) if f["reason"] == "alarm" else "another job running"
            per_run["refused"].append((WARN, f"{x['type']} {nr.utc(x['t'])}", f"not started: {why}"))
        if not r or x["state"] == "running":
            continue
        who = f"{r['type']} {nr.utc(r['start'])}"
        if r["status"] in ("killed", "error"):
            what = r["status"] + (": " + r["errors"][0][:100] if r["status"] == "error" and r["errors"] else "")
            per_run["failed"].append((BAD, who, what))
        elif r["status"] == "no shots":
            per_run["failed"].append((BAD, who, "no shots"))
        if r["timing_ok"] is False:
            per_run["timing"].append((WARN, who, f"shots not on time ({_pct(r['good_pct'])} valid timestamps"
                                      + (f", {r['timing_dev_ns']:+.0f} ns" if r["timing_dev_ns"] is not None else "")
                                      + ")"))
        if r["energy_ok"] is False:
            per_run["energy"].append((WARN, who, f"energy {r['energy_dev_pct']:+.1f} % from the usual"))
    for kind, label in GROUPS:
        problems += _grouped(per_run[kind], label)

    timing_runs = [r for r in runs if r["timing_ok"] is not None]
    energy_runs = [r for r in runs if r["energy_ok"] is not None]
    energy_devs = [r["energy_dev_pct"] for r in energy_runs]

    gps = None
    if timeref:
        good = 100.0 * (1 - timeref["bad_s"] / timeref["total_s"]) if timeref["total_s"] else None
        gps = {"good_pct": good, "bad_s": timeref["bad_s"], "tacc_max": timeref["tacc_max"],
               "lock_lost": len(timeref["lock_lost"]) if timeref["lock_known"] else None,
               "ok": timeref["bad_s"] < GPS_BAD_MIN_S and not timeref["lock_lost"]}
        if timeref["bad_s"] >= GPS_BAD_MIN_S:
            problems.insert(0, (BAD, f"GPS without fix or in holdover for {nr._dur(timeref['bad_s'])}: "
                                     "check antenna and cable"))
        if timeref["lock_lost"]:
            problems.insert(0, (BAD, f"FPGA clock lost lock {len(timeref['lock_lost'])}× "
                                     f"(from {nr.utc(timeref['lock_lost'][0])}): shot times may be wrong"))

    if t_from <= now <= t_to + 3600 and last_log_t < now - LOG_GAP_S:
        problems.insert(0, (BAD, f"no new log since {nr.utc(last_log_t) if last_log_t else 'ever'} UTC: "
                                 "PC or main.py down?"))

    level = BAD if any(l == BAD for l, _ in problems) else WARN if problems else OK
    return {
        "level": level,
        "problems": [{"level": l, "text": t} for l, t in problems],
        "runs": {
            "expected": sum(exp.values()),
            "expected_so_far": sum(1 for x in planned if x["t"] <= now),
            "started": sum(started.values()),
            "by_type": {t: {"expected": exp[t], "started": started[t]}
                        for t in nr.RUN_TYPES if exp[t] or started[t]},
            "missing": len(missing),
            "refused": sum(1 for x in rows if x["state"] == "refused"),
            "manual": sum(1 for x in rows if not x["planned"]),
        },
        "timing": {"runs": len(timing_runs), "ok": sum(1 for r in timing_runs if r["timing_ok"]),
                   "good_pct_min": GOOD_PCT_MIN, "dev_max_ns": TIMING_DEV_NS},
        "energy": {"runs": len(energy_runs), "ok": sum(1 for r in energy_runs if r["energy_ok"]),
                   "spread_pct": (max(energy_devs) - min(energy_devs)) if energy_devs else None,
                   "dev_max_pct": ENERGY_DEV_PCT},
        "gps": gps,
        "schedule": [_row_json(x) for x in rows],
        "energy_points": [{"id": r["id"], "type": r["type"], "t": r["start"], "dev": r["energy_dev_pct"],
                           "ok": r["energy_ok"]} for r in energy_runs],
    }


GROUPS = [("missing", "never started"), ("failed", "failed (killed, errors or no shots)"),
          ("refused", "not started (alarm or another job)"), ("timing", "with shots not on time"),
          ("energy", "with the energy away from the usual")]
GROUP_MIN = 4       # this many runs with the same problem: one line instead of one per run


def _grouped(items, label):
    """[(level, text)]: one line per run, or one line for all of them when they are many
    (the shifter needs to see what is wrong, the run list has the details)."""
    if len(items) < GROUP_MIN:
        return [(lvl, f"{who} {detail}") for lvl, who, detail in items]
    level = BAD if any(lvl == BAD for lvl, _, _ in items) else WARN
    whos = ", ".join(who for _, who, _ in items[:3])
    return [(level, f"{len(items)} runs {label}: {whos}, … (see the run list)")]


def _pct(v):
    return "—" if v is None else f"{v:.0f} %"


def _row_json(x):
    r = x["run"]
    out = {"t": x["t"], "type": x["type"], "state": x["state"], "planned": x["planned"]}
    if r:
        out.update({"id": r["id"], "start": r["start"], "status": r["status"], "n_shots": r["n_shots"],
                    "good_pct": r["good_pct"], "timing_ok": r["timing_ok"], "timing_dev_ns": r["timing_dev_ns"],
                    "energy_ok": r["energy_ok"], "energy_dev_pct": r["energy_dev_pct"]})
    if x["refusal"]:
        f = x["refusal"]
        out["why"] = ("alarm " + ", ".join(f["alarms"])) if f["reason"] == "alarm" else "another job running"
    return out


def power_hk(hk):
    """Only the batteries and solar panels of parse_hk()."""
    return {k: v for k, v in hk.items() if k.startswith(POWER_HK)}
