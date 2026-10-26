"""Storage port interface."""

from abc import ABC, abstractmethod
import datetime as dt
from typing import Optional
from trading_agent.domain.models import DataQualityIssue, Score


class StoragePort(ABC):
    """Abstract port for persisting and retrieving scores, signals, and anomalies."""

    @abstractmethod
    def save_score(self, score: Score) -> None:
        """Persist a score. Rerunning must be idempotent (upsert).

        Args:
            score: The calculated Score model to persist.

        Raises:
            Exception: If storage operation fails.
        """
        pass

    @abstractmethod
    def get_score(self, symbol: str, date: dt.date) -> Optional[Score]:
        """Retrieve a persisted score for a symbol on a specific date.

        Args:
            symbol: Ticker symbol.
            date: Evaluation date.

        Returns:
            The Score if found, otherwise None.
        """
        pass

    @abstractmethod
    def get_all_scores_for_symbol(self, symbol: str) -> list[Score]:
        """Retrieve all persisted scores for a symbol ordered by date.

        Args:
            symbol: Ticker symbol.

        Returns:
            List of Score records.
        """
        pass

    @abstractmethod
    def get_score_counts_by_symbol(self) -> dict[str, int]:
        """Return the count of stored score records grouped by symbol.

        Returns:
            Dictionary mapping symbol -> total count of scores.
        """
        pass

    @abstractmethod
    def save_data_quality_issue(self, issue: DataQualityIssue) -> None:
        """Persist a data anomaly record.

        Args:
            issue: DataQualityIssue instance.
        """
        pass

    @abstractmethod
    def get_data_quality_issues(
        self, symbol: Optional[str] = None
    ) -> list[DataQualityIssue]:
        """Retrieve data quality issues, optionally filtered by symbol.

        Args:
            symbol: Optional symbol filter.

        Returns:
            List of DataQualityIssue instances.
        """
        pass

    @abstractmethod
    def get_latest_scores(self) -> list[Score]:
        """Retrieve the most recent Score record for every symbol in storage.

        Returns:
            List of latest Score instances, sorted by total_points descending.
        """
        pass

    @abstractmethod
    def get_scores_for_symbol_in_range(
        self, symbol: str, start_date: dt.date, end_date: dt.date
    ) -> list[Score]:
        """Retrieve scores for a specific symbol within a date window.

        Args:
            symbol: Ticker symbol.
            start_date: Start date (inclusive).
            end_date: End date (inclusive).

        Returns:
            List of Score records ordered chronologically.
        """
        pass
