from __future__ import annotations

from enum import Enum


class IngestionRunStatus(str, Enum):
    running = "running"
    complete = "complete"
    failed = "failed"


class DocumentSourceType(str, Enum):
    procurement_ocds = "procurement_ocds"


PROCUREMENT_SOURCE_LABEL = "seed_data/procurement"
