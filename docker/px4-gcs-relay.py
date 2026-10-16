#!/usr/bin/env python3
"""Bridge UDP GCS clients to PX4's fixed loopback peer without parsing MAVLink."""
import argparse
from contextlib import ExitStack
from pathlib import Path
import select
import socket
import time

from run_state import atomic_json


def serve(listen_address, listen_port, vehicle_port, native_port, ready_file):
    with ExitStack() as stack:
        public = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
        vehicle = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
        public.bind((listen_address, listen_port))
        vehicle.bind(("127.0.0.1", vehicle_port))
        native = ("127.0.0.1", native_port)
        peers = {}
        atomic_json(ready_file, {"listen_port": public.getsockname()[1],
                                 "vehicle_port": vehicle.getsockname()[1]})
        while True:
            readable, _, _ = select.select([public, vehicle], [], [], .5)
            for sock in readable:
                try:
                    data, sender = sock.recvfrom(65535)
                except ConnectionRefusedError:
                    continue  # a UDP peer can disappear between datagrams
                now = time.monotonic()
                if sock is public:
                    if sender not in peers and len(peers) >= 64:
                        del peers[min(peers, key=peers.get)]
                    peers[sender] = now
                    try:
                        vehicle.sendto(data, native)
                    except ConnectionRefusedError:
                        pass  # PX4 may still be booting; clients send heartbeats
                elif sender == native:
                    for peer, last_seen in list(peers.items()):
                        if now - last_seen > 120:
                            del peers[peer]
                            continue
                        try:
                            public.sendto(data, peer)
                        except OSError:
                            peers.pop(peer, None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-address", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--vehicle-port", type=int, default=14550)
    parser.add_argument("--native-port", type=int, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    args = parser.parse_args()
    for port in (args.listen_port, args.vehicle_port, args.native_port):
        if not 0 <= port <= 65535:
            parser.error("ports must be between 0 and 65535")
    serve(args.listen_address, args.listen_port, args.vehicle_port, args.native_port, args.ready_file)


if __name__ == "__main__":
    main()
