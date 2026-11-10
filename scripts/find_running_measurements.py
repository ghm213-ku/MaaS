"""List measurements the worker is still running, even if their status says stopped.

A running live measurement publishes to ``measurement:data:<id>`` several times
per second. PUBSUB CHANNELS can't be used to find it, because Redis only lists
channels that have a subscriber (and the GUI may have disconnected). Instead
this script pattern-subscribes to
``measurement:data:*`` for a few seconds and reports every id that publishes,
together with its stored status and metadata.

Run it on the MaaS host (or set REDIS_HOST / REDIS_PORT):

    python scripts/find_running_measurements.py            # list only
    python scripts/find_running_measurements.py --stop     # also re-send stop

``--stop`` re-publishes the stop event the API sends. It only works if the
worker's stop listener is still alive and the job's handler is registered;
otherwise restart the worker.
"""

import argparse
import json
import os
import time

import redis


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default=os.getenv("REDIS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("REDIS_PORT", "6379")))
    parser.add_argument("--db", type=int, default=int(os.getenv("REDIS_DB", "0")))
    parser.add_argument("--seconds", type=float, default=5.0, help="how long to listen")
    parser.add_argument("--stop", action="store_true", help="re-send a stop event for each one found")
    args = parser.parse_args()

    r = redis.Redis(host=args.host, port=args.port, db=args.db, decode_responses=True)
    r.ping()

    pubsub = r.pubsub()
    pubsub.psubscribe("measurement:data:*")
    seen: dict[str, str] = {}
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        msg = pubsub.get_message(timeout=0.2)
        if msg and msg["type"] == "pmessage":
            status_id = msg["channel"].split(":", 2)[2]
            try:
                seen.setdefault(status_id, json.loads(msg["data"]).get("type", "?"))
            except (ValueError, AttributeError):
                seen.setdefault(status_id, "?")
    pubsub.close()

    running = r.hgetall("measurement:running")  # written by workers with stop acks
    if running:
        print("Worker's running-jobs list (measurement:running):")
        for status_id, info in running.items():
            print(f"  {status_id}: {info}")
        print()

    stop_listeners = r.pubsub_numsub("measurement:stop_channel")[0][1]
    print(f"Worker stop listeners on measurement:stop_channel: {stop_listeners}")
    if stop_listeners == 0:
        print(
            "  -> no worker is subscribed to stop events (worker down, or its listener died).\n"
            "     Workers with the stop-flag fix still stop their jobs within a second;\n"
            "     older workers can't be reached until they are restarted."
        )

    if not seen:
        print(f"No measurement published data in the last {args.seconds:.0f}s.")
        return

    print(f"\n{len(seen)} measurement(s) still streaming data:")
    for status_id, data_type in seen.items():
        raw = r.get(f"measurement:status:{status_id}")
        status = json.loads(raw) if raw else {}
        meta_raw = r.get(f"measurement:metadata:{status_id}")
        meta = json.loads(meta_raw) if meta_raw else {}
        print(f"\n  id:       {status_id}")
        print(f"  type:     {status.get('measurement_type', data_type)}")
        print(f"  status:   {status.get('status', '<expired: status key gone after 1h TTL>')}")
        print(f"  message:  {status.get('message', '')}")
        print(f"  started:  {status.get('started_at', '')}   stopped/completed: {status.get('completed_at', '-')}")
        print(f"  metadata: {meta}")
        if args.stop:
            n = r.publish("measurement:stop_channel", status_id)
            print(f"  re-sent stop event ({n} listener(s) received it)")


if __name__ == "__main__":
    main()
