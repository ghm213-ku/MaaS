"""Service for logging channel bookings and measurements to text files."""

import os
from datetime import datetime
from typing import Optional, List, Union
from pathlib import Path


class FileLogger:
    """Logs channel booking requests and measurement requests to text files."""

    def __init__(self, log_dir: str = "request_logs"):
        """
        Initialize the file logger.

        Args:
            log_dir: Directory to store log files (default: 'request_logs')
        """
        self.log_dir = log_dir
        self.channel_log_file = os.path.join(log_dir, "channel_requests.txt")
        self.measurement_log_file = os.path.join(log_dir, "measurement_requests.txt")

        # Create directory if it doesn't exist
        Path(log_dir).mkdir(parents=True, exist_ok=True)

        # Initialize log files with headers if they don't exist
        self._initialize_log_files()

    @staticmethod
    def _format_timestamp(timestamp: Union[datetime, str]) -> str:
        """
        Format timestamp to human-readable string.

        Args:
            timestamp: Either a datetime object or ISO format string

        Returns:
            Formatted timestamp string (YYYY-MM-DD HH:MM:SS.mmm)
        """
        if isinstance(timestamp, str):
            # If it's an ISO format string, parse it to datetime
            try:
                dt = datetime.fromisoformat(timestamp)
                return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            except (ValueError, AttributeError):
                # If parsing fails, return as-is (truncate if needed)
                return timestamp[:23]
        elif isinstance(timestamp, datetime):
            # If it's a datetime object, format it
            return timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        else:
            # Fallback for any other type
            return str(timestamp)

    def _initialize_log_files(self) -> None:
        """Initialize log files with headers if they don't exist."""
        # Channel requests log file header
        if not os.path.exists(self.channel_log_file):
            with open(self.channel_log_file, "w") as f:
                f.write("=" * 80 + "\n")
                f.write("CHANNEL BOOKING AND RELEASE REQUESTS LOG\n")
                f.write("=" * 80 + "\n")
                f.write(
                    "Booked By | Channel Numbers | Request Type | Timestamp | Details\n"
                )
                f.write("-" * 80 + "\n")

        # Measurement requests log file header
        if not os.path.exists(self.measurement_log_file):
            with open(self.measurement_log_file, "w") as f:
                f.write("=" * 80 + "\n")
                f.write("MEASUREMENT REQUESTS LOG\n")
                f.write("=" * 80 + "\n")
                f.write(
                    "Measurement ID | Type | Start Time | Duration (seconds) | Metadata\n"
                )
                f.write("-" * 80 + "\n")

    def log_channel_book_request(
        self,
        booked_by: str,
        channel_numbers: List[int],
        timestamp: Optional[Union[datetime, str]] = None,
    ) -> None:
        """
        Log a channel booking request to file.

        Args:
            booked_by: Identifier of who booked the channels
            channel_numbers: List of channel numbers booked
            timestamp: Request timestamp - can be datetime object or ISO format string (uses current time if None)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        channels_str = ", ".join(map(str, channel_numbers))
        timestamp_str = self._format_timestamp(timestamp)

        log_entry = (
            f"{booked_by:<20} | {channels_str:<20} | "
            f"{'BOOK':<15} | {timestamp_str:<25} | "
            f"Booked {len(channel_numbers)} channels\n"
        )

        try:
            with open(self.channel_log_file, "a") as f:
                f.write(log_entry)
        except IOError as e:
            print(f"Error writing to channel log file: {e}")

    def log_channel_release_request(
        self,
        booked_by: str,
        released_channels: List[int],
        timestamp: Optional[Union[datetime, str]] = None,
    ) -> None:
        """
        Log a channel release request to file.

        Args:
            booked_by: Identifier of who released the channels
            released_channels: List of channel numbers released
            timestamp: Request timestamp - can be datetime object or ISO format string (uses current time if None)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        channels_str = ", ".join(map(str, released_channels))
        timestamp_str = self._format_timestamp(timestamp)

        log_entry = (
            f"{booked_by:<20} | {channels_str:<20} | "
            f"{'RELEASE':<15} | {timestamp_str:<25} | "
            f"Released {len(released_channels)} channels\n"
        )

        try:
            with open(self.channel_log_file, "a") as f:
                f.write(log_entry)
        except IOError as e:
            print(f"Error writing to channel log file: {e}")

    def log_measurement_request(
        self,
        measurement_id: str,
        measurement_type: str,
        duration_seconds: Optional[int],
        metadata: Optional[dict] = None,
        timestamp: Optional[Union[datetime, str]] = None,
    ) -> None:
        """
        Log a measurement request to file.

        Args:
            measurement_id: Unique identifier for the measurement
            measurement_type: Type of measurement (e.g., 'count_rate', 'save_raw_tags')
            duration_seconds: Duration of measurement in seconds
            metadata: Optional metadata for the measurement
            timestamp: Request timestamp - can be datetime object or ISO format string (uses current time if None)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        timestamp_str = self._format_timestamp(timestamp)
        duration_str = (
            str(duration_seconds) if duration_seconds else "None (manual stop)"
        )
        metadata_str = str(metadata) if metadata else "None"

        log_entry = (
            f"{measurement_id:<40} | {measurement_type:<20} | "
            f"{timestamp_str:<25} | {duration_str:<20} | {metadata_str}\n"
        )

        try:
            with open(self.measurement_log_file, "a") as f:
                f.write(log_entry)
        except IOError as e:
            print(f"Error writing to measurement log file: {e}")


# Global instance of FileLogger
_file_logger: Optional[FileLogger] = None


def initialize_file_logger(log_dir: str = "request_logs") -> FileLogger:
    """
    Initialize the global file logger instance.

    Args:
        log_dir: Directory to store log files

    Returns:
        FileLogger instance
    """
    global _file_logger
    if _file_logger is None:
        _file_logger = FileLogger(log_dir)
    return _file_logger


def get_file_logger() -> FileLogger:
    """
    Get the global file logger instance.

    Raises:
        RuntimeError: If file logger has not been initialized

    Returns:
        FileLogger instance
    """
    global _file_logger
    if _file_logger is None:
        raise RuntimeError(
            "FileLogger not initialized. Call initialize_file_logger first."
        )
    return _file_logger
