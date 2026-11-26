"""Radiometer.read_power(): one triggered value per shot, NaN on error, never the next shot's value."""

import math

import pytest

import lib.Radiometer as rad_module
from lib.Radiometer import Radiometer3700, RadiometerOphir


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t


class Serial:
    """Delivers (arrival_time, bytes) items; read_until returns what arrived by the timeout."""
    is_open = True

    def __init__(self, clock, items):
        self.clock = clock
        self.items = list(items)
        self.timeout = 0.2

    def read_until(self, terminator):
        deadline = self.clock.t + self.timeout
        if self.items and self.items[0][0] <= deadline:
            t, data = self.items.pop(0)
            self.clock.t = max(self.clock.t, t)
            return data
        self.clock.t = deadline                # nothing arrived: timeout
        return b""

    def reset_input_buffer(self):
        self.items = [(t, d) for t, d in self.items if t > self.clock.t]

    def reset_output_buffer(self):
        pass

    def read_all(self):
        """Everything arrived so far, without waiting."""
        now = [d for t, d in self.items if t <= self.clock.t]
        self.items = [(t, d) for t, d in self.items if t > self.clock.t]
        return b"".join(now)


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(rad_module, "_now", c.now, raising=False)
    return c


def make(cls, clock, items, ready=True):
    r = object.__new__(cls)
    r.serial = Serial(clock, items)
    r.ready = ready
    r.messages = []
    r.log = lambda level, msg: r.messages.append(msg)
    return r


def test_value(clock):
    assert make(Radiometer3700, clock, [(0.1, b"1.234\r")]).read_power() == 1.234


def test_line_split_by_timeout_is_not_cut(clock):
    # "1.2" arrives, the rest after the serial timeout: must read 1.234, not 1.2
    r = make(Radiometer3700, clock, [(0.1, b"1.2"), (0.5, b"34\r")])
    assert r.read_power() == 1.234


def test_timeout_gives_nan(clock):
    r = make(Radiometer3700, clock, [])
    assert math.isnan(r.read_power())
    assert clock.t == pytest.approx(Radiometer3700.READ_TIMEOUT_S)
    assert any("no value" in m for m in r.messages)


def test_missing_shot_does_not_take_next_value(clock):
    # shot 1 gives no reading; shot 2's value arrives 1 s later
    r = make(Radiometer3700, clock, [(1.1, b"2.000\r")])
    assert math.isnan(r.read_power())          # shot 1
    assert r.read_power() == 2.0               # shot 2 gets its own value


def test_unexpected_line_skipped(clock):
    r = make(Radiometer3700, clock, [(0.05, b"OK\r"), (0.1, b"0.5\r")])
    assert r.read_power() == 0.5
    assert any("skipped" in m for m in r.messages)


def test_not_ready_gives_nan(clock):
    assert math.isnan(make(Radiometer3700, clock, [(0.1, b"1.0\r")], ready=False).read_power())


@pytest.mark.parametrize("line,expected", [(b"*1.5E-3\r", 1.5e-3), (b"*3.25\r", 3.25)])
def test_ophir_value(clock, line, expected):
    assert make(RadiometerOphir, clock, [(0.1, line)]).read_power() == expected


def test_ophir_errors_are_nan_not_strings(clock):
    # old code returned the raw string (e.g. '' on timeout)
    r = make(RadiometerOphir, clock, [(0.1, b"?ERR\r")])
    assert math.isnan(r.read_power())


def test_flush_drops_stale_reading_and_partial_line(clock):
    r = make(Radiometer3700, clock, [(0.0, b"9.9\r")])
    r._rx = b"7."                               # partial line from an aborted read
    r.flush_buffers()
    r.serial.items = [(0.2, b"1.0\r")]
    assert r.read_power() == 1.0


def test_discard_pending_drops_readings_already_received(clock):
    # last reading of the previous run still in the port; this shot's value comes later
    r = make(Radiometer3700, clock, [(-60.0, b"9.990\r"), (1.55, b"1.000\r")])
    assert r.discard_pending() == ["9.990"]
    assert any("dropped 1 reading" in m for m in r.messages)
    clock.t = 1.5                               # shot
    assert r.read_power() == 1.000


def test_discard_pending_also_drops_a_partial_line(clock):
    r = make(Radiometer3700, clock, [])
    r._rx = b"1.2"                              # kept by a read_power() timed out mid-line
    assert r.discard_pending() == ["1.2"]
    assert r._rx == b""


def test_discard_pending_nothing_pending_is_silent(clock):
    r = make(Radiometer3700, clock, [(1.55, b"1.000\r")])
    assert r.discard_pending() == []
    assert r.messages == []


def test_slow_reading_is_logged(clock):
    r = make(Radiometer3700, clock, [(0.7, b"1.000\r")])
    assert r.read_power() == 1.000
    assert any("slow reading, 0.70s" in m for m in r.messages)


# --- two radiometers of the same shot (calibration run: Rad3 + Rad1) ---------------------

def test_read_powers_both_values(clock):
    rad3 = make(RadiometerOphir, clock, [(0.3, b"*2.0E-3\r")])
    rad1 = make(Radiometer3700, clock, [(0.5, b"1.000\r")])
    assert rad_module.read_powers([rad3, rad1]) == [2.0e-3, 1.0]


def test_read_powers_one_deadline_for_all(clock):
    # Rad3 never answers: Rad1's value, already received, is still taken, and the
    # whole read ends within READ_TIMEOUT_S (before the next shot), not after 2 x
    rad3 = make(RadiometerOphir, clock, [])
    rad1 = make(Radiometer3700, clock, [(0.2, b"1.000\r")])
    p3, p1 = rad_module.read_powers([rad3, rad1])
    assert math.isnan(p3) and p1 == 1.0
    assert clock.t == pytest.approx(Radiometer3700.READ_TIMEOUT_S)


def test_read_powers_second_missing(clock):
    rad3 = make(RadiometerOphir, clock, [(0.3, b"*2.0E-3\r")])
    rad1 = make(Radiometer3700, clock, [(1.2, b"9.000\r")])     # next shot's value: not taken
    p3, p1 = rad_module.read_powers([rad3, rad1])
    assert p3 == 2.0e-3 and math.isnan(p1)
    assert clock.t == pytest.approx(Radiometer3700.READ_TIMEOUT_S)
