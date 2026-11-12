"""Runtime configuration for the PDF processing pipeline.

All values can be overridden through environment variables so the service can
be tuned (page-level parallelism, PaddleOCR engine pool, render DPI, ...)
without code changes.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        logger.warning("Invalid integer for %s=%r - using %s", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except ValueError:
        logger.warning("Invalid float for %s=%r - using %s", name, raw, default)
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def default_workers() -> int:
    """Sensible page-level parallelism for the current machine."""
    return max(1, min(8, os.cpu_count() or 4))


@dataclass(frozen=True)
class PipelineConfig:
    # Number of pages processed concurrently per document (text extraction,
    # page rendering, image extraction, OCR result post-processing).
    max_workers: int = field(default_factory=default_workers)

    # Number of PPStructureV3 engine instances kept alive. Paddle predictors
    # are expensive to build, so they are pooled and reused. 1 = safe default,
    # raise it (together with PDF_OCR_PADDLE_THREADS) on large CPU/GPU boxes.
    paddle_engine_pool: int = 1

    # Threads handed to each Paddle predictor (paddle ``cpu_threads``).
    # 0 = let Paddle/PaddleX choose (their own default).
    paddle_cpu_threads: int = 0

    # Render scale used when rasterising pages for OCR (2.0 == 144 dpi).
    render_scale: float = 2.0

    # Run pymupdf4llm page extraction across the thread pool.
    parallel_text: bool = True

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        return cls(
            max_workers=max(1, _env_int("PDF_OCR_MAX_WORKERS", default_workers())),
            paddle_engine_pool=max(1, _env_int("PDF_OCR_ENGINE_POOL", 1)),
            paddle_cpu_threads=max(0, _env_int("PDF_OCR_PADDLE_THREADS", 0)),
            render_scale=_env_float("PDF_OCR_RENDER_SCALE", 2.0),
            parallel_text=_env_bool("PDF_OCR_PARALLEL_TEXT", True),
        )


def load_config() -> PipelineConfig:
    return PipelineConfig.from_env()
