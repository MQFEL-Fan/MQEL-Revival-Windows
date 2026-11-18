"""Schutz gegen Missbrauch, gemeinsam für Spiel- und Chat-Server:
gleichzeitige Verbindungen je IP, Fehlversuche je Schlüssel (Login), Loggröße.
"""

import os
import threading
import time

# Gleichzeitige TCP-Verbindungen je IP (Client: wenige Keep-Alive-
# Verbindungen zum Spielserver, eine zum Chat; Launcher und Shop dazu)
MAX_CONNECTIONS_PER_IP = 32
# Fehlgeschlagene Anmeldungen je Name bzw. IP in FAIL_WINDOW_S Sekunden
MAX_FAILURES = 5
FAIL_WINDOW_S = 60.0


class ConnectionLimit:
    def __init__(self, limit=MAX_CONNECTIONS_PER_IP):
        self.limit = limit
        self.lock = threading.Lock()
        self.counts = {}

    def acquire(self, ip):
        """True, wenn die Verbindung angenommen wird (dann release aufrufen)."""
        with self.lock:
            n = self.counts.get(ip, 0)
            if n >= self.limit:
                return False
            self.counts[ip] = n + 1
            return True

    def release(self, ip):
        with self.lock:
            n = self.counts.get(ip, 0) - 1
            if n > 0:
                self.counts[ip] = n
            else:
                self.counts.pop(ip, None)


class FailureThrottle:
    """Höchstens MAX_FAILURES Fehlversuche je Schlüssel im Zeitfenster."""

    def __init__(self, limit=MAX_FAILURES, window=FAIL_WINDOW_S):
        self.limit, self.window = limit, window
        self.lock = threading.Lock()
        self.fails = {}  # Schlüssel -> Zeitpunkte (monotonic)

    def _recent(self, key, now):
        times = [t for t in self.fails.get(key, ()) if now - t < self.window]
        if times:
            self.fails[key] = times
        else:
            self.fails.pop(key, None)
        return times

    def blocked(self, *keys):
        now = time.monotonic()
        with self.lock:
            return any(len(self._recent(k, now)) >= self.limit for k in keys if k)

    def fail(self, *keys):
        now = time.monotonic()
        with self.lock:
            for k in keys:
                if k:
                    self._recent(k, now)
                    self.fails.setdefault(k, []).append(now)


# Logdateien: ab dieser Größe nach <datei>.1 verschieben (eine alte Datei)
MAX_LOG_BYTES = 100_000_000


def rotate_log(path):
    """Vor dem Anhängen aufrufen (unter dem Log-Lock des Aufrufers)."""
    try:
        if os.path.getsize(path) > MAX_LOG_BYTES:
            os.replace(path, path + ".1")
    except OSError:
        pass
