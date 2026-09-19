"""Worker lifecycle: keep the authorized terminal session, isolate cancellation.

Do not use setsid/start_new_session for the exporter: sudo's per-terminal
credential timestamp belongs to the controlling terminal/session. A process
GROUP is enough to target the worker and its children without signaling the UI.
The child initializes its group before doing any work (also on Python 3.10).
"""
from __future__ import annotations
import os
import signal


def prepare_worker() -> None:
    """Called only by the internal CLI worker, never by in-process diagnostics."""
    if os.getpgrp() != os.getpid():
        os.setpgid(0, 0)


def signal_worker(worker, sig: int = signal.SIGTERM) -> None:
    """Never signal the UI group, including cancellation during child startup."""
    if worker.returncode is not None:
        return
    try:
        group = os.getpgid(worker.pid)
        if group == worker.pid and group != os.getpgrp():
            os.killpg(group, sig)
        else:
            # The child has not run prepare_worker yet. It cannot have spawned
            # export children; signaling this PID alone cannot hit the parent.
            os.kill(worker.pid, sig)
    except ProcessLookupError:
        pass  # It finished between returncode/getpgid/kill.
