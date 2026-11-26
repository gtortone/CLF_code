#!/usr/bin/env python3
"""
Bench test of the RPC_Auger board through lib/RPC_Auger.py (the same code the runs use),
before enabling it in conf/<site>/ports.yml.

    python3 spikes/rpc_auger_test.py --ip 172.32.0.93 status
    python3 spikes/rpc_auger_test.py --ip 172.32.0.93 on 1
    python3 spikes/rpc_auger_test.py --ip 172.32.0.93 off 1
    python3 spikes/rpc_auger_test.py --ip 172.32.0.93 cycle 1 --times 5
    python3 spikes/rpc_auger_test.py --conf clf status      # address from conf/clf/ports.yml

status       state of OUT1..OUT6, 'enable', time of the request
on N / off N switch one output, check it with a new status, print the time taken
cycle N      on/off N times on one output (--times, --pause), counts the failures

Only the output given is switched: with real instruments connected, choose it on purpose.
Run from the CLF_code directory.
"""

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import yaml                                                   # noqa: E402
from lib.RPC_Auger import RPCAugerDevice, RPCError            # noqa: E402


def from_conf(site):
    with open(os.path.join(ROOT, "conf", site, "ports.yml")) as f:
        ports = {k: v for doc in yaml.safe_load_all(f) for k, v in doc.items()}
    p = dict(ports["RPC"])
    if str(p.pop("type", "serial")).lower() != "rpc_auger":
        sys.exit(f"conf/{site}/ports.yml: RPC is not type RPC_Auger (still the serial one?), use --ip")
    return p


def show_status(rpc):
    t0 = time.monotonic()
    answer = rpc._get("/status")
    dt = time.monotonic() - t0
    outputs = answer.get("outputs", {})
    print("  ".join(f"{k}={'ON' if v else 'off'}" for k, v in sorted(outputs.items())),
          f"| enable={answer.get('enable')} | {dt * 1000:.0f} ms")


def switch(rpc, n, state):
    outlet = rpc.add_outlet(n, f"OUT{n}")
    t0 = time.monotonic()
    ok = outlet.set(state)
    dt = time.monotonic() - t0
    print(f"OUT{n} {'on' if state else 'off'}: {'OK' if ok else 'FAILED'} ({dt * 1000:.0f} ms, with check)")
    return ok


def main():
    ap = argparse.ArgumentParser(description="RPC_Auger bench test")
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--ip", help="board address")
    where.add_argument("--conf", choices=["clf", "xlf"], help="take address and credentials from conf/<site>/ports.yml")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin")
    ap.add_argument("--timeout", type=float, default=3)
    ap.add_argument("command", choices=["status", "on", "off", "cycle"])
    ap.add_argument("output", nargs="?", type=int, choices=range(1, 7), metavar="N", help="output 1..6")
    ap.add_argument("--times", type=int, default=5, help="cycle: number of on/off")
    ap.add_argument("--pause", type=float, default=2, help="cycle: seconds between commands")
    args = ap.parse_args()

    if args.command != "status" and args.output is None:
        ap.error(f"'{args.command}' needs the output number (1..6)")

    params = from_conf(args.conf) if args.conf else dict(
        ip=args.ip, port=args.port, user=args.user, password=args.password, timeout=args.timeout)
    rpc = RPCAugerDevice(**params)
    print(f"RPC_Auger at {rpc.url}")

    try:
        if args.command == "status":
            show_status(rpc)
        elif args.command in ("on", "off"):
            ok = switch(rpc, args.output, args.command == "on")
            show_status(rpc)
            return 0 if ok else 1
        else:
            failures = 0
            for i in range(args.times):
                for state in (1, 0):
                    failures += not switch(rpc, args.output, state)
                    time.sleep(args.pause)
            print(f"{args.times} cycles, {failures} failure(s)")
            show_status(rpc)
            return 0 if failures == 0 else 1
    except RPCError as e:
        print(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
