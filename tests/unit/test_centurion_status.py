"""Centurion status (State Byte + Happy Bytes): READY, standby checked, parameter names."""

import logging

import pytest

import lib.Centurion as cent_module
from lib.Centurion import Centurion, LaserStatus

from test_centurion_protocol import Clock, LaserSerial


@pytest.fixture
def laser(monkeypatch):
    clock = Clock()
    ser = LaserSerial(clock)
    monkeypatch.setattr(cent_module.serial, "Serial", lambda **kw: ser)
    monkeypatch.setattr(cent_module, "_now", clock.now)
    monkeypatch.setattr(cent_module, "_sleep", clock.sleep)
    monkeypatch.setattr(cent_module.time, "sleep", clock.sleep)
    c = Centurion("/dev/null")
    c.clock, c.ser = clock, ser
    c.messages = []
    c.log = lambda level, msg, **kw: c.messages.append((level, msg))
    return c


# --- decoding (manual p. 33-35) -----------------------------------------------------------

def test_not_ready_seen_in_the_site_logs():
    # device.log 2025-11-17: State Byte 7E, but pump head temperature WARNING + NOT-READY
    st = LaserStatus.parse("$STATUS 7e 03 01 01 00")
    assert st.state == 0x7E and st.standby and st.configured and not st.fire
    assert st.not_ready and not st.ready
    assert st.describe() == ("SB 7E HB 03 01 01 00: STANDBY, NOT-READY (pump head temperature), "
                             "WARNING (pump head temperature)")


@pytest.mark.parametrize("answer,ready", [
    ("$STATUS 7E 00 00 00 00", True),      # standby, configured, all happy
    ("$STATUS 7E 01 01 00 00", True),      # WARNING only: the laser keeps working
    ("$STATUS BE 00 00 00 00", True),      # already in FIRE, configured
    ("$STATUS 7E 02 00 03 00", False),     # NOT-READY: interface plate temperature
    ("$STATUS 7E 04 00 00 10", False),     # INTERLOCK: E-stop open
    ("$STATUS 3E 00 00 00 00", False),     # SLEEP (neither STANDBY nor FIRE)
    ("$STATUS 7A 00 00 00 00", False),     # diodes not enabled
])
def test_ready(answer, ready):
    assert LaserStatus.parse(answer).ready is ready


@pytest.mark.parametrize("answer", ["", "$STATUS 7E 00 00 00", "$STATUS 7E 00 00 00 zz", "$TEMPS 1 2 3"])
def test_malformed_status(answer):
    assert LaserStatus.parse(answer) is None


def test_describe_interlock_and_config():
    st = LaserStatus.parse("$STATUS 7A 04 00 00 18")
    assert st.describe() == ("SB 7A HB 04 00 00 18: STANDBY, configuration 0x3a (runs need 0x3e), "
                             "INTERLOCK (E-stop open, controller cover open)")


# --- fire_auth: wait for READY, not only for State Byte 7E ---------------------------------

def test_fire_auth_waits_for_ready(laser):
    laser.ser.answer("$STATUS", "$STATUS 7e 03 01 01 00")
    assert laser.fire_auth() is False                   # old code: True (State Byte 7E)
    laser.ser.answer("$STATUS", "$STATUS 7e 00 00 00 00")
    assert laser.fire_auth() is True


def test_status_logged_only_when_it_changes(laser):
    laser.ser.answer("$STATUS", "$STATUS 7e 03 01 01 00")
    for _ in range(5):
        laser.fire_auth()                               # 1 s polls while waiting
    laser.ser.answer("$STATUS", "$STATUS 7e 00 00 00 00")
    laser.fire_auth()
    status_lines = [(lvl, m) for lvl, m in laser.messages if m.startswith("CENT:STATUS:")]
    assert [lvl for lvl, _ in status_lines] == [logging.WARNING, logging.INFO]
    assert "NOT-READY" in status_lines[0][1] and status_lines[1][1].endswith(": STANDBY")


def test_fire_auth_no_answer(laser):
    assert laser.fire_auth() is False


# --- standby is checked --------------------------------------------------------------------

def test_standby_ok(laser):
    laser.ser.answer("$STANDBY", "$STANDBY")
    laser.ser.answer("$STATUS", "$STATUS 7E 00 00 00 00")
    assert laser.standby() == 0


def test_standby_still_in_fire_is_an_error(laser):
    laser.ser.answer("$STANDBY", "$STANDBY")
    laser.ser.answer("$STATUS", "$STATUS BE 00 00 00 00")       # D7 still set
    assert laser.standby() == -1
    assert laser.ser.written.count("$STANDBY") == cent_module.STANDBY_RETRIES
    assert any(lvl == logging.ERROR and "out of FIRE" in m for lvl, m in laser.messages)


def test_standby_silent_laser_does_not_retry(laser):
    t0 = laser.clock.t
    assert laser.standby() == -1
    assert laser.ser.written.count("$STANDBY") == 1
    assert laser.clock.t - t0 <= 2 * cent_module.RESPONSE_TIMEOUT_S + 1


# --- parameters ----------------------------------------------------------------------------

def test_check_parameter_long_name(laser):
    laser.ser.answer("$QSDELAY", "$QSDEL 145")          # the laser answers with 5 characters
    assert laser.check_qs_delay() == "145"              # old code: -1 (compared with $QSDELAY)


def test_set_pwdth_result(laser):
    laser.ser.answer("$DPW", "$DPW 140")
    assert laser.set_pwdth(140) == 0
    laser.ser.answer("$DPW", "$Bad Value")
    assert laser.set_pwdth(9999) == -1


def test_warmup_reports_unacknowledged_commands(laser):
    laser.ser.answer("$STANDBY", "$STANDBY")
    laser.ser.answer("$QSON", "$QSON 1")
    laser.ser.answer("$STATUS", "$STATUS 7E 00 00 00 00")   # no answer to $DIODE 1
    assert laser.warmup() == -1
    laser.ser.answer("$DIODE", "$DIODE 1")
    assert laser.warmup() == 0


# --- fire: the warning carries the full status ---------------------------------------------

def test_fire_bit_not_set_logs_why(laser):
    laser.ser.answer("$TEMPS", "$TEMPS 300 200 200")
    laser.ser.answer("$FIRE", "$FIRE")
    laser.ser.answer("$STATUS", "$STATUS 7e 03 01 01 00")
    assert laser.fire() == 0                            # still logged only (to confirm on site)
    warn = [m for lvl, m in laser.messages if lvl == logging.WARNING and m.startswith("CENT:FIRE")]
    assert warn and "NOT-READY (pump head temperature)" in warn[0]


def test_fire_bit_set(laser):
    laser.ser.answer("$TEMPS", "$TEMPS 300 200 200")
    laser.ser.answer("$FIRE", "$FIRE")
    laser.ser.answer("$STATUS", "$STATUS BE 00 00 00 00")
    assert laser.fire() == 0
    assert not any(m.startswith("CENT:FIRE") for _, m in laser.messages)
