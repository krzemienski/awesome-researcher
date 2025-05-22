"""Unified JSON‑lines logger capturing prompts, completions, tokens, latency, and cost."""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict

_LOGGER = logging.getLogger("research")
_HANDLER: logging.Handler | None = None

class CostTimer:
    """Track elapsed seconds, tokens, and incremental cost."""
    def __init__(self):
        self.start = time.perf_counter()
        self.tokens = 0

    def add_tokens(self, n: int):
        self.tokens += n

    @property
    def seconds(self) -> float:
        return time.perf_counter() - self.start

    @property
    def cost_usd(self) -> float:
        return round(self.tokens * 1e-5, 5)  # simple heuristic


def _ensure_handler(run_dir: Path):
    global _HANDLER
    if _HANDLER is None:
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = run_dir / "agent.log"
        _HANDLER = logging.FileHandler(log_path)
        _HANDLER.setFormatter(logging.Formatter("%(message)s"))
        _LOGGER.addHandler(_HANDLER)
        _LOGGER.setLevel(logging.INFO)


@contextmanager
def log_phase(name: str, run_dir: Path, timer: CostTimer, extra: Dict[str, Any] | None = None):
    """Context‑manager writing start/end events with timing & cost."""
    _ensure_handler(run_dir)
    start_payload = {"phase": name, "event": "start", "ts": time.time(), **(extra or {})}
    _LOGGER.info(json.dumps(start_payload))
    t0 = timer.seconds
    yield
    elapsed = timer.seconds - t0
    end_payload = {
        "phase": name,
        "event": "end",
        "elapsed_s": round(elapsed, 3),
        "tokens": timer.tokens,
        "cost_usd": timer.cost_usd
    }
    _LOGGER.info(json.dumps(end_payload))
