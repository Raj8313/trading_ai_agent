"""Domain models for the trading agent.

Contains pure business entities (Stock, Bar, Score, Signal, TradeBand, etc.)
defined using Pydantic. These entities have no dependencies on external
libraries like databases, APIs, or network clients.
"""

import datetime as dt
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class TradeBand(str, Enum):
    """Trading bands determined by total confidence meter score."""

    FULL = "FULL"  # 80 - 100 points
    HALF = "HALF"  # 60 - 79 points
    NONE = "NONE"  # Below 60 points


class Stock(BaseModel):
    """Represents a tradeable stock or market index symbol."""

    symbol: str = Field(..., description="Ticker symbol (e.g., RELIANCE.NS, ^NSEI)")
    name: str = Field(default="", description="Descriptive company or index name")
    exchange: str = Field(default="NSE", description="Exchange name (e.g., NSE)")


class Bar(BaseModel):
    """Represents a single daily OHLCV (Open, High, Low, Close, Volume) candlestick."""

    date: dt.date = Field(..., description="Trading date for the bar")
    open: float = Field(..., gt=0, description="Open price")
    high: float = Field(..., gt=0, description="High price")
    low: float = Field(..., gt=0, description="Low price")
    close: float = Field(..., gt=0, description="Close price")
    volume: int = Field(..., ge=0, description="Trading volume")

    @model_validator(mode="after")
    def validate_price_bounds(self) -> "Bar":
        """Ensure high is at least as high as low, open, and close."""
        if self.high < self.low:
            raise ValueError(f"High ({self.high}) cannot be less than low ({self.low})")
        if self.high < self.open or self.high < self.close:
            raise ValueError("High must be greater than or equal to both open and close")
        if self.low > self.open or self.low > self.close:
            raise ValueError("Low must be less than or equal to both open and close")
        return self


class CheckResult(BaseModel):
    """Result returned by an individual confidence check."""

    check_name: str = Field(..., description="Unique human-readable check name")
    passed: bool = Field(..., description="Whether the check condition was satisfied")
    points_awarded: int = Field(..., ge=0, description="Points earned for this check")
    max_points: int = Field(..., gt=0, description="Maximum points possible for this check")
    rationale: str = Field(..., description="Auditable, human-readable reason for score")


class Score(BaseModel):
    """Aggregate confidence score calculated for a symbol on a specific date."""

    symbol: str = Field(..., description="Stock symbol evaluated")
    date: dt.date = Field(..., description="Evaluation date")
    check_results: list[CheckResult] = Field(
        default_factory=list, description="Breakdown of individual check evaluations"
    )
    total_points: int = Field(..., ge=0, description="Sum of points awarded")
    band: TradeBand = Field(..., description="Trade band corresponding to total points")

    @classmethod
    def calculate_band(cls, total_points: int) -> TradeBand:
        """Classify total score points into standard trade bands.

        Bands:
        - >= 80: FULL (80-100)
        - 60 - 79: HALF (60-79)
        - < 60: NONE (below 60)
        """
        if total_points >= 80:
            return TradeBand.FULL
        if total_points >= 60:
            return TradeBand.HALF
        return TradeBand.NONE


class Signal(BaseModel):
    """Trading action signal derived from an evaluation score."""

    symbol: str = Field(..., description="Stock symbol")
    date: dt.date = Field(..., description="Signal date")
    score: Score = Field(..., description="Associated confidence score")
    band: TradeBand = Field(..., description="Trade band")
    action: str = Field(
        ..., description="Action decision: BUY_FULL, BUY_HALF, or PASS"
    )
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc),
        description="Timestamp when signal was generated",
    )


class DataQualityIssue(BaseModel):
    """Record of a data anomaly (e.g. missing dates, NaN values, empty feed)."""

    symbol: str = Field(..., description="Stock symbol where issue occurred")
    date: Optional[dt.date] = Field(default=None, description="Date of issue if applicable")
    issue: str = Field(..., description="Description of the anomaly")
    recorded_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc),
        description="Timestamp when issue was recorded",
    )
