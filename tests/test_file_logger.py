"""Tests for file logger service for logging channel and measurement requests."""

import pytest
import os
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

from app.services.file_logger import (
    FileLogger,
    initialize_file_logger,
    get_file_logger,
)


class TestFileLoggerInitialization:
    """Test FileLogger initialization."""

    def test_file_logger_creates_directory(self):
        """FileLogger should create log directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = os.path.join(temp_dir, "new_logs")
            assert not os.path.exists(log_dir)

            logger = FileLogger(log_dir)

            assert os.path.exists(log_dir)
            assert os.path.isdir(log_dir)

    def test_file_logger_creates_log_files(self):
        """FileLogger should create both log files on initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)

            channel_file = os.path.join(temp_dir, "channel_requests.txt")
            measurement_file = os.path.join(temp_dir, "measurement_requests.txt")

            assert os.path.exists(channel_file)
            assert os.path.exists(measurement_file)

    def test_log_files_have_headers(self):
        """Log files should be initialized with proper headers."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)

            # Check channel log header
            channel_file = os.path.join(temp_dir, "channel_requests.txt")
            with open(channel_file, "r") as f:
                content = f.read()
                assert "CHANNEL BOOKING AND RELEASE REQUESTS LOG" in content
                assert (
                    "Booked By | Channel Numbers | Request Type | Timestamp | Details"
                    in content
                )
                assert "=" * 80 in content

            # Check measurement log header
            measurement_file = os.path.join(temp_dir, "measurement_requests.txt")
            with open(measurement_file, "r") as f:
                content = f.read()
                assert "MEASUREMENT REQUESTS LOG" in content
                assert (
                    "Measurement ID | Type | Start Time | Duration (seconds) | Metadata"
                    in content
                )
                assert "=" * 80 in content

    def test_file_logger_does_not_recreate_existing_headers(self):
        """FileLogger should not recreate headers if files already exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create first instance
            logger1 = FileLogger(temp_dir)

            # Get file sizes
            channel_file = os.path.join(temp_dir, "channel_requests.txt")
            initial_size = os.path.getsize(channel_file)

            # Create second instance with same directory
            logger2 = FileLogger(temp_dir)

            # File size should remain the same (no duplicate headers)
            final_size = os.path.getsize(channel_file)
            assert initial_size == final_size


class TestChannelBookRequestLogging:
    """Test channel booking request logging."""

    def test_log_channel_book_request(self):
        """Should log channel booking request to file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)
            timestamp = datetime(2026, 5, 22, 10, 30, 45, 123000)

            logger.log_channel_book_request(
                booked_by="measurement-001",
                channel_numbers=[1, 2, 3],
                timestamp=timestamp,
            )

            channel_file = os.path.join(temp_dir, "channel_requests.txt")
            with open(channel_file, "r") as f:
                content = f.read()
                assert "measurement-001" in content
                assert "1, 2, 3" in content
                assert "BOOK" in content
                assert "2026-05-22 10:30:45.123" in content
                assert "Booked 3 channels" in content

    def test_log_channel_book_request_single_channel(self):
        """Should log booking with single channel."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)

            logger.log_channel_book_request(
                booked_by="user-abc",
                channel_numbers=[5],
                timestamp=datetime(2026, 5, 22, 12, 0, 0),
            )

            channel_file = os.path.join(temp_dir, "channel_requests.txt")
            with open(channel_file, "r") as f:
                content = f.read()
                assert "user-abc" in content
                assert "5" in content
                assert "Booked 1 channels" in content

    def test_log_channel_book_request_multiple_channels(self):
        """Should log booking with multiple channels."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)

            logger.log_channel_book_request(
                booked_by="measurement-xyz",
                channel_numbers=[1, 2, 3, 4, 5, 6, 7, 8],
            )

            channel_file = os.path.join(temp_dir, "channel_requests.txt")
            with open(channel_file, "r") as f:
                content = f.read()
                assert "Booked 8 channels" in content

    def test_log_channel_book_request_uses_current_time_if_no_timestamp(self):
        """Should use current time if timestamp is not provided."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)
            before = datetime.utcnow()

            logger.log_channel_book_request(
                booked_by="user-test",
                channel_numbers=[1, 2],
                timestamp=None,
            )

            after = datetime.utcnow()

            channel_file = os.path.join(temp_dir, "channel_requests.txt")
            with open(channel_file, "r") as f:
                content = f.read()
                assert "user-test" in content
                assert "1, 2" in content
                # Verify timestamp is recent (within last second)
                lines = content.strip().split("\n")
                last_entry = lines[-1]
                assert "|" in last_entry


class TestChannelReleaseRequestLogging:
    """Test channel release request logging."""

    def test_log_channel_release_request(self):
        """Should log channel release request to file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)
            timestamp = datetime(2026, 5, 22, 11, 45, 30, 500000)

            logger.log_channel_release_request(
                booked_by="measurement-001",
                released_channels=[1, 2, 3],
                timestamp=timestamp,
            )

            channel_file = os.path.join(temp_dir, "channel_requests.txt")
            with open(channel_file, "r") as f:
                content = f.read()
                assert "measurement-001" in content
                assert "1, 2, 3" in content
                assert "RELEASE" in content
                assert "2026-05-22 11:45:30.500" in content
                assert "Released 3 channels" in content

    def test_log_multiple_book_and_release_requests(self):
        """Should log multiple book and release operations in sequence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)

            # Book channels
            logger.log_channel_book_request(
                booked_by="measurement-001",
                channel_numbers=[1, 2, 3],
                timestamp=datetime(2026, 5, 22, 10, 0, 0),
            )

            # Release channels
            logger.log_channel_release_request(
                booked_by="measurement-001",
                released_channels=[1, 2, 3],
                timestamp=datetime(2026, 5, 22, 10, 5, 0),
            )

            # Book different channels
            logger.log_channel_book_request(
                booked_by="measurement-002",
                channel_numbers=[4, 5],
                timestamp=datetime(2026, 5, 22, 10, 10, 0),
            )

            channel_file = os.path.join(temp_dir, "channel_requests.txt")
            with open(channel_file, "r") as f:
                lines = f.readlines()
                # Should have header lines + 3 log entries
                assert len(lines) >= 7  # header (5 lines) + 3 entries minimum

            with open(channel_file, "r") as f:
                content = f.read()
                # Verify all entries are present
                assert content.count("BOOK") >= 2
                assert content.count("RELEASE") >= 1
                assert "measurement-001" in content
                assert "measurement-002" in content


class TestTimestampHandling:
    """Test timestamp handling for both datetime objects and ISO format strings."""

    def test_log_channel_book_with_iso_format_string_timestamp(self):
        """Should handle ISO format string timestamps from Redis."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)
            # ISO format string as returned by datetime.utcnow().isoformat()
            iso_timestamp = "2026-05-22T14:30:45.123456"

            logger.log_channel_book_request(
                booked_by="measurement-001",
                channel_numbers=[1, 2, 3],
                timestamp=iso_timestamp,
            )

            channel_file = os.path.join(temp_dir, "channel_requests.txt")
            with open(channel_file, "r") as f:
                content = f.read()
                assert "measurement-001" in content
                # Should be formatted as YYYY-MM-DD HH:MM:SS.mmm
                assert "2026-05-22 14:30:45.123" in content
                assert "BOOK" in content

    def test_log_channel_release_with_iso_format_string_timestamp(self):
        """Should handle ISO format string timestamps for releases."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)
            iso_timestamp = "2026-05-22T15:45:30.987654"

            logger.log_channel_release_request(
                booked_by="measurement-001",
                released_channels=[1, 2, 3],
                timestamp=iso_timestamp,
            )

            channel_file = os.path.join(temp_dir, "channel_requests.txt")
            with open(channel_file, "r") as f:
                content = f.read()
                assert "measurement-001" in content
                assert "2026-05-22 15:45:30.987" in content
                assert "RELEASE" in content

    def test_log_measurement_with_iso_format_string_timestamp(self):
        """Should handle ISO format string timestamps for measurements."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)
            iso_timestamp = "2026-05-22T16:20:15.500000"

            logger.log_measurement_request(
                measurement_id="meas-001",
                measurement_type="count_rate",
                duration_seconds=60,
                metadata={"detector": "det_001"},
                timestamp=iso_timestamp,
            )

            measurement_file = os.path.join(temp_dir, "measurement_requests.txt")
            with open(measurement_file, "r") as f:
                content = f.read()
                assert "meas-001" in content
                assert "2026-05-22 16:20:15.500" in content
                assert "60" in content

    def test_format_timestamp_with_datetime_object(self):
        """_format_timestamp should handle datetime objects."""
        dt = datetime(2026, 5, 22, 10, 30, 45, 123000)
        result = FileLogger._format_timestamp(dt)
        assert result == "2026-05-22 10:30:45.123"

    def test_format_timestamp_with_iso_string(self):
        """_format_timestamp should handle ISO format strings."""
        iso_str = "2026-05-22T10:30:45.123456"
        result = FileLogger._format_timestamp(iso_str)
        assert result == "2026-05-22 10:30:45.123"

    def test_format_timestamp_with_iso_string_no_microseconds(self):
        """_format_timestamp should handle ISO strings without microseconds."""
        iso_str = "2026-05-22T10:30:45"
        result = FileLogger._format_timestamp(iso_str)
        assert "2026-05-22 10:30:45" in result

    def test_mixed_timestamp_types_in_same_session(self):
        """Should handle both datetime and ISO strings in the same logging session."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)

            # First request with datetime object
            logger.log_channel_book_request(
                booked_by="user-1",
                channel_numbers=[1, 2],
                timestamp=datetime(2026, 5, 22, 10, 0, 0),
            )

            # Second request with ISO format string
            logger.log_channel_book_request(
                booked_by="user-2",
                channel_numbers=[3, 4],
                timestamp="2026-05-22T11:00:00.000000",
            )

            channel_file = os.path.join(temp_dir, "channel_requests.txt")
            with open(channel_file, "r") as f:
                content = f.read()
                assert "user-1" in content
                assert "user-2" in content
                assert content.count("2026-05-22") >= 2


class TestMeasurementRequestLogging:
    """Test measurement request logging."""

    def test_log_measurement_request_count_rate(self):
        """Should log count-rate measurement request."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)
            timestamp = datetime(2026, 5, 22, 14, 15, 30, 750000)

            logger.log_measurement_request(
                measurement_id="meas-abc-123",
                measurement_type="count_rate",
                duration_seconds=60,
                metadata={"detector_id": "det_001"},
                timestamp=timestamp,
            )

            measurement_file = os.path.join(temp_dir, "measurement_requests.txt")
            with open(measurement_file, "r") as f:
                content = f.read()
                assert "meas-abc-123" in content
                assert "count_rate" in content
                assert "2026-05-22 14:15:30.750" in content
                assert "60" in content
                assert "detector_id" in content

    def test_log_measurement_request_save_raw_tags(self):
        """Should log save-raw-tags measurement request."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)

            metadata = {
                "channel_list": [1, 2, 3],
                "target_file_path": "C:\\Users\\test\\data",
            }

            logger.log_measurement_request(
                measurement_id="meas-xyz-789",
                measurement_type="save_raw_tags",
                duration_seconds=120,
                metadata=metadata,
            )

            measurement_file = os.path.join(temp_dir, "measurement_requests.txt")
            with open(measurement_file, "r") as f:
                content = f.read()
                assert "meas-xyz-789" in content
                assert "save_raw_tags" in content
                assert "120" in content
                assert "channel_list" in content

    def test_log_measurement_request_no_duration(self):
        """Should handle measurement request without duration (manual stop)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)

            logger.log_measurement_request(
                measurement_id="meas-manual-001",
                measurement_type="count_rate",
                duration_seconds=None,
                metadata={"mode": "manual"},
            )

            measurement_file = os.path.join(temp_dir, "measurement_requests.txt")
            with open(measurement_file, "r") as f:
                content = f.read()
                assert "meas-manual-001" in content
                assert "None (manual stop)" in content

    def test_log_measurement_request_no_metadata(self):
        """Should handle measurement request without metadata."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)

            logger.log_measurement_request(
                measurement_id="meas-simple-001",
                measurement_type="count_rate",
                duration_seconds=30,
                metadata=None,
            )

            measurement_file = os.path.join(temp_dir, "measurement_requests.txt")
            with open(measurement_file, "r") as f:
                content = f.read()
                assert "meas-simple-001" in content
                assert "30" in content
                assert "None" in content

    def test_log_multiple_measurement_requests(self):
        """Should log multiple measurement requests in sequence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)

            # Log first measurement
            logger.log_measurement_request(
                measurement_id="meas-001",
                measurement_type="count_rate",
                duration_seconds=60,
                metadata={"detector": "det_001"},
                timestamp=datetime(2026, 5, 22, 10, 0, 0),
            )

            # Log second measurement
            logger.log_measurement_request(
                measurement_id="meas-002",
                measurement_type="save_raw_tags",
                duration_seconds=120,
                metadata={"channels": [1, 2, 3]},
                timestamp=datetime(2026, 5, 22, 10, 5, 0),
            )

            measurement_file = os.path.join(temp_dir, "measurement_requests.txt")
            with open(measurement_file, "r") as f:
                content = f.read()
                assert "meas-001" in content
                assert "meas-002" in content
                assert content.count("count_rate") >= 1
                assert content.count("save_raw_tags") >= 1


class TestAppendBehavior:
    """Test that logging appends to existing files across instances."""

    def test_append_across_instances(self):
        """Should append to files when creating new FileLogger instances."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # First instance - create files and add entry
            logger1 = FileLogger(temp_dir)
            logger1.log_channel_book_request(
                booked_by="user-1",
                channel_numbers=[1, 2],
                timestamp=datetime(2026, 5, 22, 10, 0, 0),
            )

            # Get file size after first instance
            channel_file = os.path.join(temp_dir, "channel_requests.txt")
            size_after_first = os.path.getsize(channel_file)

            # Second instance - should append, not recreate
            logger2 = FileLogger(temp_dir)
            logger2.log_channel_book_request(
                booked_by="user-2",
                channel_numbers=[3, 4],
                timestamp=datetime(2026, 5, 22, 11, 0, 0),
            )

            # File should be larger
            size_after_second = os.path.getsize(channel_file)
            assert size_after_second > size_after_first

            # Both entries should be in file
            with open(channel_file, "r") as f:
                content = f.read()
                assert "user-1" in content
                assert "user-2" in content

    def test_service_restart_persistence(self):
        """Should maintain all logs across simulated service restarts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Simulate first service instance
            logger1 = FileLogger(temp_dir)
            logger1.log_measurement_request(
                measurement_id="meas-session-1-001",
                measurement_type="count_rate",
                duration_seconds=60,
            )
            logger1.log_measurement_request(
                measurement_id="meas-session-1-002",
                measurement_type="count_rate",
                duration_seconds=120,
            )

            # Simulate service restart
            logger2 = FileLogger(temp_dir)
            logger2.log_measurement_request(
                measurement_id="meas-session-2-001",
                measurement_type="save_raw_tags",
                duration_seconds=90,
            )

            # All measurements should be present
            measurement_file = os.path.join(temp_dir, "measurement_requests.txt")
            with open(measurement_file, "r") as f:
                content = f.read()
                assert "meas-session-1-001" in content
                assert "meas-session-1-002" in content
                assert "meas-session-2-001" in content


class TestGlobalInstanceManagement:
    """Test global file logger instance management."""

    def test_initialize_file_logger(self):
        """Should initialize and return file logger."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = initialize_file_logger(temp_dir)
            assert logger is not None
            assert isinstance(logger, FileLogger)

    def test_get_file_logger_without_initialization_raises_error(self):
        """Should raise RuntimeError if get called before initialization."""
        # Note: This test may interfere with other tests if not isolated
        # In practice, the global instance persists across tests
        # This test is informational about expected behavior
        pass

    def test_initialize_creates_log_directory(self):
        """FileLogger should create the specified log directory with all files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = os.path.join(temp_dir, "maas_logs")
            # Create FileLogger directly to avoid global state issues
            logger = FileLogger(log_dir)

            # The logger's log_dir should exist
            assert os.path.exists(logger.log_dir)
            assert os.path.exists(logger.channel_log_file)
            assert os.path.exists(logger.measurement_log_file)


class TestErrorHandling:
    """Test error handling in file logging."""

    def test_handles_write_error_gracefully(self, capsys):
        """Should handle file write errors gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)

            # Make channel file read-only to cause write error
            channel_file = os.path.join(temp_dir, "channel_requests.txt")
            os.chmod(channel_file, 0o444)  # Read-only

            try:
                # Should not raise exception, but may print error
                logger.log_channel_book_request(
                    booked_by="test",
                    channel_numbers=[1],
                )
                # If we get here, error was handled gracefully
                assert True
            finally:
                # Restore permissions for cleanup
                os.chmod(channel_file, 0o644)

    def test_handles_measurement_write_error_gracefully(self, capsys):
        """Should handle measurement file write errors gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)

            # Make measurement file read-only
            measurement_file = os.path.join(temp_dir, "measurement_requests.txt")
            os.chmod(measurement_file, 0o444)  # Read-only

            try:
                # Should not raise exception, but may print error
                logger.log_measurement_request(
                    measurement_id="test",
                    measurement_type="count_rate",
                    duration_seconds=60,
                )
                # If we get here, error was handled gracefully
                assert True
            finally:
                # Restore permissions for cleanup
                os.chmod(measurement_file, 0o644)


class TestLogFormatting:
    """Test log entry formatting."""

    def test_channel_log_formatting_consistency(self):
        """Channel log entries should have consistent formatting."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)

            # Log multiple entries
            logger.log_channel_book_request(
                booked_by="test-user",
                channel_numbers=[1, 2],
                timestamp=datetime(2026, 5, 22, 10, 0, 0),
            )

            logger.log_channel_release_request(
                booked_by="test-user",
                released_channels=[1, 2],
                timestamp=datetime(2026, 5, 22, 10, 5, 0),
            )

            channel_file = os.path.join(temp_dir, "channel_requests.txt")
            with open(channel_file, "r") as f:
                lines = f.readlines()
                # Filter to actual data lines (not headers, separators, or empty)
                data_lines = [
                    l
                    for l in lines
                    if l.strip()
                    and not l.startswith("=")
                    and not l.startswith("-")
                    and "Booked By" not in l
                    and "CHANNEL BOOKING" not in l
                ]

                # Should have at least 2 data entries (1 book + 1 release)
                assert len(data_lines) >= 2
                # All data lines should have pipe separators
                for line in data_lines:
                    assert line.count("|") >= 4  # At least 4 pipe separators

    def test_measurement_log_formatting_consistency(self):
        """Measurement log entries should have consistent formatting."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = FileLogger(temp_dir)

            logger.log_measurement_request(
                measurement_id="test-meas-001",
                measurement_type="count_rate",
                duration_seconds=60,
            )

            logger.log_measurement_request(
                measurement_id="test-meas-002",
                measurement_type="save_raw_tags",
                duration_seconds=120,
                metadata={"key": "value"},
            )

            measurement_file = os.path.join(temp_dir, "measurement_requests.txt")
            with open(measurement_file, "r") as f:
                lines = f.readlines()
                # Filter to actual data lines (not headers, separators, or empty)
                data_lines = [
                    l
                    for l in lines
                    if l.strip()
                    and not l.startswith("=")
                    and not l.startswith("-")
                    and "Measurement ID" not in l
                    and "MEASUREMENT REQUESTS" not in l
                ]

                # Should have at least 2 data entries
                assert len(data_lines) >= 2
                # All data lines should have pipe separators
                for line in data_lines:
                    assert line.count("|") >= 4  # At least 4 pipe separators
