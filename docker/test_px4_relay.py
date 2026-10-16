"""Host-only UDP byte relay tests; no firmware, Docker or pymavlink needed."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest


class RelayTests(unittest.TestCase):
    def test_bidirectional_reconnect_and_multiple_clients(self):
        with tempfile.TemporaryDirectory() as temp, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as native:
            native.bind(("127.0.0.1", 0))
            native.settimeout(2)
            ready = Path(temp) / "ready.json"
            process = subprocess.Popen([
                sys.executable, str(Path(__file__).with_name("px4-gcs-relay.py")),
                "--listen-address", "127.0.0.1", "--listen-port", "0", "--vehicle-port", "0",
                "--native-port", str(native.getsockname()[1]), "--ready-file", str(ready)])
            try:
                deadline = time.monotonic() + 3
                while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(.01)
                ports = json.loads(ready.read_text())
                endpoint = ("127.0.0.1", ports["listen_port"])
                def client():
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.bind(("127.0.0.1", 0))
                    sock.settimeout(2)
                    return sock
                with client() as first:
                    first.sendto(b"first", endpoint)
                    data, peer = native.recvfrom(65535)
                    self.assertEqual(data, b"first")
                    self.assertEqual(peer[1], ports["vehicle_port"])
                    native.sendto(b"telemetry", peer)
                    self.assertEqual(first.recvfrom(65535)[0], b"telemetry")
                with client() as second, client() as third:
                    second.sendto(b"reconnect", endpoint)
                    self.assertEqual(native.recvfrom(65535)[0], b"reconnect")
                    native.sendto(b"reply", peer)
                    self.assertEqual(second.recvfrom(65535)[0], b"reply")
                    third.sendto(b"another-client", endpoint)
                    self.assertEqual(native.recvfrom(65535)[0], b"another-client")
                    native.sendto(b"both", peer)
                    self.assertEqual(second.recvfrom(65535)[0], b"both")
                    self.assertEqual(third.recvfrom(65535)[0], b"both")
            finally:
                process.terminate()
                process.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
