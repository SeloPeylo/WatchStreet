"""Worker process: heartbeat, scheduled scans and ticket execution.

Run with ``python -m watchstreet.worker`` (loop) or ``--once`` (scan + drain the queue, exit).
"""

import argparse
import logging
import signal
import threading

from watchstreet.config import load_settings
from watchstreet.constants import WORKER_HEARTBEAT_KEY
from watchstreet.container import Container, build_container
from watchstreet.db import session_scope
from watchstreet.harness.executor import execute_ticket
from watchstreet.harness.scan import run_scan, scan_due
from watchstreet.services.state import touch
from watchstreet.services.tickets import claim_next, requeue_stuck

logger = logging.getLogger("watchstreet.worker")


def drain_queue(container: Container) -> int:
    """Execute queued tickets until none are left; returns how many ran."""
    ran = 0
    while True:
        with session_scope(container.session_factory) as session:
            ticket = claim_next(session)
            ticket_id = ticket.id if ticket else None
        if ticket_id is None:
            return ran
        status = execute_ticket(container, ticket_id)
        logger.info("Ticket %s -> %s", ticket_id, status)
        ran += 1


def tick(container: Container, *, force_scan: bool = False) -> int:
    """One worker iteration."""
    with session_scope(container.session_factory) as session:
        touch(session, WORKER_HEARTBEAT_KEY)
    if force_scan or scan_due(container):
        logger.info("Scan: %s", run_scan(container))
    return drain_queue(container)


def run_forever(container: Container, stop: threading.Event) -> None:
    with session_scope(container.session_factory) as session:
        logger.info("Requeued %s stuck ticket(s)", requeue_stuck(session))
    logger.info(
        "Worker started (market=%s, runner=%s)",
        container.market.name,
        container.runner.name,
    )
    while not stop.is_set():
        try:
            tick(container)
        except Exception:  # a broken database or source must not end the worker
            logger.exception("Worker iteration failed; retrying")
        stop.wait(container.settings.worker_poll_s)


def main() -> None:
    parser = argparse.ArgumentParser(description="WatchStreet worker")
    parser.add_argument("--once", action="store_true", help="scan, drain the queue, then exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    container = build_container(load_settings())
    if args.once:
        tick(container, force_scan=True)
        return
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    run_forever(container, stop)


if __name__ == "__main__":
    main()
