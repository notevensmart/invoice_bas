from __future__ import annotations

import sqlite3
from pathlib import Path

from app.persistence import models


DEFAULT_DB_PATH = Path("data/invoice_poc.sqlite3")


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.execute(models.DOCUMENTS_TABLE)
    connection.execute(models.INVOICE_RESULTS_TABLE)
    connection.execute(models.CORRECTIONS_TABLE)
    connection.execute(models.BATCHES_TABLE)
    connection.commit()
