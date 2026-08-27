"""Forschungshypothesen-Register (Research Knowledge Base).

Jede gepruefte Hypothese erhaelt eine eindeutige ID (z.B. HYP-000123) und wird
unveraenderlich in SQLite protokolliert - inklusive:
- Vollstaendiger maschinenlesbarer Bedingungs-Konfiguration
- Git-Commit-Hash & Config-Hash
- Datensatz-Name, Zeitfenster und Datensatz-Hash (SHA-256)
- In-Sample, Validation & OOS Stichprobengroessen
- Unkorrigierte und Bonferroni-korrigierte p-Werte
- Metriken (Erwartungswert, Sharpe, MAE/MFE, Trefferquote)
- Verdikt ("CONFIRMED", "REJECTED", "DISCOVERY_ONLY", "INCONCLUSIVE")
- Begruendung & Negativ-Befund-Dokumentation
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import pandas as pd

VerdictType = Literal["CONFIRMED", "REJECTED", "DISCOVERY_ONLY", "INCONCLUSIVE"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS hypotheses (
    hypothesis_id       TEXT PRIMARY KEY,
    created_at_utc      TEXT NOT NULL,
    title               TEXT NOT NULL,
    description         TEXT NOT NULL,
    verdict             TEXT NOT NULL,
    timeframe           TEXT NOT NULL,
    dataset_name        TEXT NOT NULL,
    dataset_hash        TEXT NOT NULL,
    git_commit          TEXT NOT NULL,
    config_hash         TEXT NOT NULL,
    sample_size_train   INTEGER NOT NULL,
    sample_size_val     INTEGER DEFAULT 0,
    sample_size_oos     INTEGER DEFAULT 0,
    p_value_raw         REAL NOT NULL,
    p_value_corrected   REAL,
    bonferroni_passed   INTEGER DEFAULT 0,
    conditions_json     TEXT NOT NULL,
    metrics_json        TEXT NOT NULL,
    notes               TEXT
);

CREATE INDEX IF NOT EXISTS idx_hyp_verdict ON hypotheses(verdict);
CREATE INDEX IF NOT EXISTS idx_hyp_timeframe ON hypotheses(timeframe);
"""


@dataclass(frozen=True)
class RegisteredHypothesis:
    """Ein unveraenderlicher Eintrag im Forschungsregister."""

    hypothesis_id: str
    created_at_utc: datetime
    title: str
    description: str
    verdict: VerdictType
    timeframe: str
    dataset_name: str
    dataset_hash: str
    git_commit: str
    config_hash: str
    sample_size_train: int
    sample_size_val: int
    sample_size_oos: int
    p_value_raw: float
    p_value_corrected: float | None
    bonferroni_passed: bool
    conditions: dict[str, Any]
    metrics: dict[str, Any]
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "created_at_utc": self.created_at_utc.isoformat(),
            "title": self.title,
            "description": self.description,
            "verdict": self.verdict,
            "timeframe": self.timeframe,
            "dataset_name": self.dataset_name,
            "dataset_hash": self.dataset_hash,
            "git_commit": self.git_commit,
            "config_hash": self.config_hash,
            "sample_size_train": self.sample_size_train,
            "sample_size_val": self.sample_size_val,
            "sample_size_oos": self.sample_size_oos,
            "p_value_raw": round(self.p_value_raw, 6),
            "p_value_corrected": round(self.p_value_corrected, 6) if self.p_value_corrected is not None else None,
            "bonferroni_passed": self.bonferroni_passed,
            "conditions": self.conditions,
            "metrics": self.metrics,
            "notes": self.notes,
        }


class ResearchRegister:
    """Verwaltet das Forschungsregister."""

    def __init__(self, db_path: str | Path = "data/research_register.sqlite3") -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        with self._lock:
            conn = sqlite3.connect(str(self._path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
            conn.commit()
            conn.close()

    def next_hypothesis_id(self) -> str:
        """Erzeugt die naechste fortlaufende ID (z.B. HYP-000001)."""
        with self._lock:
            conn = sqlite3.connect(str(self._path))
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM hypotheses")
            count = cur.fetchone()[0]
            conn.close()
            return f"HYP-{count + 1:06d}"

    def register(
        self,
        *,
        title: str,
        description: str,
        verdict: VerdictType,
        timeframe: str,
        dataset_name: str,
        dataset_hash: str,
        git_commit: str,
        config_hash: str,
        sample_size_train: int,
        p_value_raw: float,
        conditions: dict[str, Any],
        metrics: dict[str, Any],
        sample_size_val: int = 0,
        sample_size_oos: int = 0,
        p_value_corrected: float | None = None,
        bonferroni_passed: bool = False,
        notes: str = "",
        hypothesis_id: str | None = None,
    ) -> RegisteredHypothesis:
        """Speichert eine Hypothese im Register."""
        hyp_id = hypothesis_id or self.next_hypothesis_id()
        now_utc = datetime.now(timezone.utc)

        entry = RegisteredHypothesis(
            hypothesis_id=hyp_id,
            created_at_utc=now_utc,
            title=title,
            description=description,
            verdict=verdict,
            timeframe=timeframe,
            dataset_name=dataset_name,
            dataset_hash=dataset_hash,
            git_commit=git_commit,
            config_hash=config_hash,
            sample_size_train=sample_size_train,
            sample_size_val=sample_size_val,
            sample_size_oos=sample_size_oos,
            p_value_raw=p_value_raw,
            p_value_corrected=p_value_corrected,
            bonferroni_passed=bonferroni_passed,
            conditions=conditions,
            metrics=metrics,
            notes=notes,
        )

        with self._lock:
            conn = sqlite3.connect(str(self._path))
            conn.execute(
                """
                INSERT INTO hypotheses (
                    hypothesis_id, created_at_utc, title, description, verdict,
                    timeframe, dataset_name, dataset_hash, git_commit, config_hash,
                    sample_size_train, sample_size_val, sample_size_oos,
                    p_value_raw, p_value_corrected, bonferroni_passed,
                    conditions_json, metrics_json, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.hypothesis_id,
                    entry.created_at_utc.isoformat(),
                    entry.title,
                    entry.description,
                    entry.verdict,
                    entry.timeframe,
                    entry.dataset_name,
                    entry.dataset_hash,
                    entry.git_commit,
                    entry.config_hash,
                    entry.sample_size_train,
                    entry.sample_size_val,
                    entry.sample_size_oos,
                    entry.p_value_raw,
                    entry.p_value_corrected,
                    1 if entry.bonferroni_passed else 0,
                    json.dumps(entry.conditions, ensure_ascii=False),
                    json.dumps(entry.metrics, ensure_ascii=False),
                    entry.notes,
                ),
            )
            conn.commit()
            conn.close()

        return entry

    def get(self, hypothesis_id: str) -> RegisteredHypothesis | None:
        """Laedt eine einzelne Hypothese."""
        with self._lock:
            conn = sqlite3.connect(str(self._path))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM hypotheses WHERE hypothesis_id = ?", (hypothesis_id,)
            ).fetchone()
            conn.close()

        if not row:
            return None

        return RegisteredHypothesis(
            hypothesis_id=row["hypothesis_id"],
            created_at_utc=datetime.fromisoformat(row["created_at_utc"]),
            title=row["title"],
            description=row["description"],
            verdict=row["verdict"],
            timeframe=row["timeframe"],
            dataset_name=row["dataset_name"],
            dataset_hash=row["dataset_hash"],
            git_commit=row["git_commit"],
            config_hash=row["config_hash"],
            sample_size_train=row["sample_size_train"],
            sample_size_val=row["sample_size_val"],
            sample_size_oos=row["sample_size_oos"],
            p_value_raw=row["p_value_raw"],
            p_value_corrected=row["p_value_corrected"],
            bonferroni_passed=bool(row["bonferroni_passed"]),
            conditions=json.loads(row["conditions_json"]),
            metrics=json.loads(row["metrics_json"]),
            notes=row["notes"] or "",
        )

    def count(self) -> int:
        with self._lock:
            conn = sqlite3.connect(str(self._path))
            count = conn.execute("SELECT count(*) FROM hypotheses").fetchone()[0]
            conn.close()
            return count


def hash_dataframe(df: Any) -> str:
    """Erzeugt einen deterministischen SHA-256 Hash eines DataFrames."""
    if isinstance(df, pd.DataFrame):
        data_bytes = pd.util.hash_pandas_object(df, index=True).values.tobytes()
        return hashlib.sha256(data_bytes).hexdigest()[:16]
    return hashlib.sha256(str(df).encode("utf-8")).hexdigest()[:16]
