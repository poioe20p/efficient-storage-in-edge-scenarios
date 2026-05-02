"""pymongo CommandListener that accumulates per-request read/write DB time."""
from pymongo import monitoring
from flask import g

_READ_CMDS = {
    "find", "aggregate", "count", "distinct",
    "getMore", "findAndModify",
}
_WRITE_CMDS = {"insert", "update", "delete"}
_IGNORED_CMDS = {
    "hello", "isMaster", "ismaster", "ping", "buildInfo",
    "saslStart", "saslContinue", "endSessions",
    "getParameter", "killCursors", "listDatabases",
    "listCollections", "listIndexes", "connectionStatus",
}


class _DbTimingListener(monitoring.CommandListener):
    def started(self, event):
        pass

    def succeeded(self, event):
        self._record(event.command_name, event.duration_micros)

    def failed(self, event):
        self._record(event.command_name, event.duration_micros)

    @staticmethod
    def _record(cmd: str, dur_us: int) -> None:
        if cmd in _IGNORED_CMDS:
            return
        dur_s = dur_us / 1_000_000.0
        try:
            if cmd in _READ_CMDS:
                g.time_db_read_s = getattr(g, "time_db_read_s", 0.0) + dur_s
            elif cmd in _WRITE_CMDS:
                g.time_db_write_s = getattr(g, "time_db_write_s", 0.0) + dur_s
            g.time_db_cmd_count = getattr(g, "time_db_cmd_count", 0) + 1
        except RuntimeError:
            # Outside Flask request context (driver-internal op) — ignore.
            pass


_listener_registered = False


def register() -> None:
    """Idempotent global registration. Call once at app import time."""
    global _listener_registered
    if _listener_registered:
        return
    monitoring.register(_DbTimingListener())
    _listener_registered = True
