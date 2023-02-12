import pdb
import time
import begin
import logging
import numpy as np
from pathlib import Path
from threading import Timer
from contextlib import contextmanager
from pythonjsonlogger import jsonlogger

from taccjm import tacc_ssh_api as tsa
from taccjm.utils import parse_allocations_string, init_logger, get_log_level
from taccjm.constants import TACCJM_DIR

global stats
stats = np.array([])
_logger = None


def get_stats():
    global stats
    num_calls = len(stats)
    avg_time = stats.mean()
    std_dev = stats.std()
    msg = f"HEARTBEAT STATS\n\rNum calls = {num_calls}\n\t"
    msg += f"Average time per call= {avg_time}s\n\tStd Dev time = {std_dev}s\n"
    _logger.info(
        msg, extra={"num_calls": num_calls, "avg_time": avg_time, "std_dev": std_dev}
    )


@contextmanager
def timing(label: str):
    t0 = time.perf_counter()
    yield lambda: (label, t1 - t0)
    t1 = time.perf_counter()


class RepeatingTimer(Timer):
    def run(self):
        while not self.finished.is_set():
            self.function(*self.args, **self.kwargs)
            self.finished.wait(self.interval)


def heartbeat():
    try:
        global stats
        _logger.info("Starting heartbeat list_sessions() call")
        with timing("list_sessions()") as api_time:
            res = tsa.list_sessions()
            for c in res:
                _logger.info(f"Checking connection {c['id']}'s allocations.",
                             extra={'connection_config': c})
                try:
                    allocs = parse_allocations_string(
                        tsa.exec(c['id'], "/usr/local/etc/taccinfo")['stdout'])
                    for a in allocs:
                        _logger.info(
                            f"Found allocation {a['name']}",
                            extra={
                                "SUs": a["service_units"],
                                "expiration": a["exp_date"],
                            },
                        )
                except Exception as e:
                    _logger.info(f"Error checking allocations {e}")
        stats = np.append(stats, api_time()[1])
        _logger.info(
            "%s Done in %.6f s" % api_time(),
            extra={"api_time": api_time()[1], "connections": res},
        )
        get_stats()
    except Exception as e:
        msg = f"Heartbeat failed to make list_session call {e}"
        _logger.error(msg)


@begin.start(auto_convert=True)
def run(
    host: "Host where server is running" = "localhost",
    port: "Port on which server is listening on" = "8221",
    heartbeat_interval: "Time in minutes between heartbeats" = 0.5,
    loglevel: "Level for logging" = "info",
):
    """
    Run

    Main entry-point for heart-beat script. Note begin decorator makes function
    arguments command line arguments accepted to run this as a main entry point.
    Note function does not return, but runs continuously until terminated.

    Parameters
    ----------
    host : str, default='localhost'
        Host where taccjm server is running.
    port : int, default=8221
        Port that taccjm server is listening on.

    Returns
    -------

    """
    global _logger

    LOGFILE = f"{TACCJM_DIR}/ssh_server_hb_{host}_{port}_log.json"
    _, _logger = init_logger('tacc_ssh_hb',
                             log_config={'output': LOGFILE,
                                         'fmt': 'json',
                                         'level': get_log_level(loglevel)})

    # Set endpoint for taccjm server
    _logger.info(
        f"Setting host and port to ({host}, {port})",
        extra={"host": host, "port": port}
    )
    tsa.set_host(host=host, port=port)

    # Start heartbeat timer
    h_int = heartbeat_interval * 60.0
    _logger.info(
        f"Starting heartbeat every {h_int}s = {heartbeat_interval}m",
        extra={"host": host, "port": port},
    )
    t = RepeatingTimer(h_int, heartbeat)
    t.start()
