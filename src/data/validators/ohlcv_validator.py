"""ohlcv_validator.py
--------------------
Validates the quality of OHLCV DataFrames before storage or analysis.

Returns a ValidationResult containing a list of ValidationIssues
classified as WARNING or ERROR. The caller decides what to do with them.

Usage
-----
    from src.data.validators import validate_ohlcv

    result = validate_ohlcv(df, symbol="RELIANCE")
    if result.has_errors:
        raise DataValidationError(str(result), result.issues)
    for w in result.warnings:
        log.warning(w.message)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

import pandas as pd

from src.core.constants import OHLCV_COLUMNS


class Severity(str, Enum):
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class ValidationIssue:
    severity: Severity
    code: str
    message: str


@dataclass
class ValidationResult:
    symbol: str
    issues: list[ValidationIssue] = field(default_factory=list)

    def add(self, severity: Severity, code: str, message: str) -> None:
        self.issues.append(ValidationIssue(severity, code, message))

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def is_clean(self) -> bool:
        return not self.issues

    def __str__(self) -> str:
        if self.is_clean:
            return f"{self.symbol}: OK"
        lines = [f"{self.symbol}: {len(self.errors)} errors, {len(self.warnings)} warnings"]
        for issue in self.issues:
            lines.append(f"  [{issue.severity.value}] {issue.code}: {issue.message}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------

def validate_ohlcv(
    df: pd.DataFrame,
    symbol: str = "UNKNOWN",
    min_rows: int = 20,
    max_future_days: int = 1,
) -> ValidationResult:
    """Run all OHLCV quality checks and return a ValidationResult.

    Checks performed:
    - DataFrame not empty
    - Required columns present
    - Index is DatetimeIndex
    - No future dates
    - No duplicate dates
    - No missing bars > 10 consecutive trading days
    - Open, High, Low, Close all positive
    - High >= Low, High >= Open, High >= Close
    - Low <= Open, Low <= Close
    - Volume >= 0
    - No all-zero rows
    """
    result = ValidationResult(symbol=symbol)

    # ── Empty check ────────────────────────────────────────────────────────
    if df is None or df.empty:
        result.add(Severity.ERROR, "EMPTY", "DataFrame is empty")
        return result

    if len(df) < min_rows:
        result.add(
            Severity.WARNING,
            "INSUFFICIENT_ROWS",
            f"Only {len(df)} rows; minimum expected is {min_rows}",
        )

    # ── Column presence ────────────────────────────────────────────────────
    missing_cols = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing_cols:
        result.add(
            Severity.ERROR,
            "MISSING_COLUMNS",
            f"Required columns missing: {missing_cols}",
        )
        return result  # can't proceed without columns

    price_df = df[["Open", "High", "Low", "Close"]].copy()
    vol_series = df["Volume"] if "Volume" in df.columns else None

    # ── Index type ─────────────────────────────────────────────────────────
    if not isinstance(df.index, pd.DatetimeIndex):
        result.add(Severity.ERROR, "BAD_INDEX", "Index is not a DatetimeIndex")
        return result

    # ── Future dates ───────────────────────────────────────────────────────
    today = pd.Timestamp(date.today())
    future_mask = df.index > today + pd.Timedelta(days=max_future_days)
    if future_mask.any():
        result.add(
            Severity.ERROR,
            "FUTURE_DATES",
            f"{future_mask.sum()} rows have future dates",
        )

    # ── Duplicate dates ────────────────────────────────────────────────────
    dupes = df.index.duplicated().sum()
    if dupes:
        result.add(
            Severity.ERROR,
            "DUPLICATE_DATES",
            f"{dupes} duplicate date(s) found",
        )

    # ── Missing bars (gaps > 10 trading days) ──────────────────────────────
    if len(df) > 1:
        gaps = df.index.to_series().diff().dt.days.dropna()
        large_gaps = gaps[gaps > 14]  # >14 calendar days ≈ >10 trading days
        if not large_gaps.empty:
            result.add(
                Severity.WARNING,
                "DATA_GAPS",
                f"{len(large_gaps)} gap(s) larger than 14 calendar days detected",
            )

    # ── Negative / zero prices ─────────────────────────────────────────────
    non_positive = (price_df <= 0).any(axis=1).sum()
    if non_positive:
        result.add(
            Severity.ERROR,
            "NON_POSITIVE_PRICE",
            f"{non_positive} rows with non-positive price values",
        )

    # ── OHLCV consistency ──────────────────────────────────────────────────
    violations = (
        (df["High"] < df["Low"]) |
        (df["High"] < df["Open"]) |
        (df["High"] < df["Close"]) |
        (df["Low"] > df["Open"]) |
        (df["Low"] > df["Close"])
    ).sum()
    if violations:
        result.add(
            Severity.ERROR,
            "OHLC_INCONSISTENCY",
            f"{violations} rows violate OHLC ordering (High < Low etc.)",
        )

    # ── Volume ─────────────────────────────────────────────────────────────
    if vol_series is not None:
        neg_vol = (vol_series < 0).sum()
        if neg_vol:
            result.add(
                Severity.ERROR,
                "NEGATIVE_VOLUME",
                f"{neg_vol} rows with negative volume",
            )
        zero_vol_pct = (vol_series == 0).mean() * 100
        if zero_vol_pct > 5:
            result.add(
                Severity.WARNING,
                "HIGH_ZERO_VOLUME",
                f"{zero_vol_pct:.1f}% of rows have zero volume",
            )

    # ── NaN check ──────────────────────────────────────────────────────────
    nan_counts = price_df.isna().sum()
    total_nans = nan_counts.sum()
    if total_nans:
        result.add(
            Severity.WARNING,
            "NAN_VALUES",
            f"{total_nans} NaN values across OHLC columns: {nan_counts.to_dict()}",
        )

    return result
