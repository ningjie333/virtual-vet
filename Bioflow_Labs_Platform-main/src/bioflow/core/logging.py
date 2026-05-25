import json
import logging
import time
log = logging.getLogger("bioflow")


def setup_logging(level="INFO"):
    logging.basicConfig(level=getattr(logging, level))


def event(code: str, **fields):
    payload = {"ts": time.time(), "code": code, **fields}
    log.info(json.dumps(payload, separators=(",", ":")))
