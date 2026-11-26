"""
logs/shots.csv: one row per laser shot of the FD, TANK, CALIB and WARMUP runs, for the
analyses (same values as the "power <i> shot: ..." lines of run.log, without parsing).

One file per night: rotated at 18:00 like run.log (shots.csv.YYYY-MM-DD), each file
starts with the header line.

Columns:
    utc            PC time of the row, UTC, ms (YYYY-MM-DDTHH:MM:SS.mmm)
    run_id         <RUN TYPE>-<unix seconds of the run start>, as in the dashboard
    run_type       FD, TANK, CALIB, WARMUP
    series         calibration run: energy, pol0, pol90, pol180 (empty for the others)
    shot           shot index in the series, from 0
    gps_seconds    FPGA timestamp: GPS seconds (0 = no packet for this shot)
    counter_ns     FPGA timestamp: ns from the PPS
    pps_delta_ns   FPGA timestamp: PPS distance, ns
    counter_cycle  FPGA shot number in the sequence (from 1)
    power_rad1     Rad1 energy (empty = Rad1 not read in this run, nan = no reading)
    power_rad3     Rad3 energy (same)
"""

import datetime
import logging
import os
from logging.handlers import TimedRotatingFileHandler

COLUMNS = ["utc", "run_id", "run_type", "series", "shot", "gps_seconds", "counter_ns",
           "pps_delta_ns", "counter_cycle", "power_rad1", "power_rad3"]
HEADER = ",".join(COLUMNS)
RADIOMETER_COLUMNS = {"Rad1": "power_rad1", "Rad3": "power_rad3"}

LOGGER_NAME = "shots_csv"


class HeaderMixin:
    """For a file handler: writes `header` at the top of every new file (at start if the
    file is new or empty, and after each rotation, when the handler opens a new file)."""

    def __init__(self, filename, header, **kwargs):
        self.header = header
        super().__init__(filename, **kwargs)

    def _open(self):
        stream = super()._open()
        if os.path.getsize(self.baseFilename) == 0:
            stream.write(self.header + self.terminator)
            stream.flush()
        return stream


class CsvRotatingFileHandler(HeaderMixin, TimedRotatingFileHandler):
    pass


def shots_logger(path="logs/shots.csv"):
    """The logger of the shots.csv rows (handler added once per process)."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False                # rows only in the CSV, never in other logs
    if not logger.handlers:
        handler = CsvRotatingFileHandler(path, HEADER, when='midnight',
                                         atTime=datetime.time(hour=18, minute=0))
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
    return logger


def row(run_id, run_type, series, shot, gps_seconds, counter_ns, pps_delta_ns, counter_cycle,
        powers, now=None):
    """CSV line of one shot. `powers`: {radiometer name: energy} of the radiometers read."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cols = {name: "" for name in RADIOMETER_COLUMNS.values()}
    for name, value in powers.items():
        if name in RADIOMETER_COLUMNS:
            cols[RADIOMETER_COLUMNS[name]] = str(value)
    values = [now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}",
              run_id, run_type, series, shot, gps_seconds, counter_ns, pps_delta_ns, counter_cycle,
              cols["power_rad1"], cols["power_rad3"]]
    return ",".join(str(v) for v in values)
