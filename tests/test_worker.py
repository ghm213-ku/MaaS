"""Tests for the backend worker's run flags and TimeTagger test-signal setup."""

from unittest.mock import MagicMock, call, patch

import pytest

import worker
from worker import BackendWorker, TEST_SIGNAL_CHANNELS, configure_test_signals, parse_args


@pytest.fixture
def tagger():
    mock = MagicMock()
    mock.getChannelList.return_value = list(range(1, 17))
    return mock


class TestConfigureTestSignals:
    def test_normal_run_disables_test_signal_on_all_channels(self, tagger):
        configure_test_signals(tagger, testing=False)

        tagger.setTestSignal.assert_called_once_with(list(range(1, 17)), False)

    def test_testing_run_enables_test_signal_on_first_five_channels_only(self, tagger):
        configure_test_signals(tagger, testing=True)

        assert TEST_SIGNAL_CHANNELS == [1, 2, 3, 4, 5]
        assert tagger.setTestSignal.call_args_list == [
            call(list(range(1, 17)), False),
            call([1, 2, 3, 4, 5], True),
        ]

    def test_queries_rising_edge_channels(self, tagger):
        configure_test_signals(tagger, testing=False)

        tagger.getChannelList.assert_called_once_with(worker.TimeTagger.ChannelEdge.Rising)


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.testing is False
        assert args.no_hardware is False

    def test_testing_flag(self):
        assert parse_args(["--testing"]).testing is True

    def test_no_hardware_flag(self):
        assert parse_args(["--no-hardware"]).no_hardware is True


class TestBackendWorkerInit:
    @pytest.fixture
    def patched(self, tagger):
        status_manager = MagicMock()
        status_manager.health_check.return_value = True
        with patch.object(worker, "StatusManager", return_value=status_manager), \
             patch.object(worker, "FileLogger"), \
             patch.object(worker, "JobProcessor") as job_processor, \
             patch.object(worker.TimeTagger, "createTimeTagger", return_value=tagger):
            yield job_processor

    def test_normal_run_turns_test_signal_off(self, patched, tagger):
        BackendWorker()

        tagger.setTestSignal.assert_called_once_with(list(range(1, 17)), False)
        assert patched.call_args.kwargs["tagger"] is tagger

    def test_testing_run_turns_test_signal_on_for_channels_1_to_5(self, patched, tagger):
        BackendWorker(testing=True)

        tagger.setTestSignal.assert_any_call([1, 2, 3, 4, 5], True)

    def test_no_hardware_skips_timetagger(self, patched, tagger):
        with patch.object(worker.TimeTagger, "createTimeTagger") as create:
            BackendWorker(no_hardware=True)

        create.assert_not_called()
        assert patched.call_args.kwargs["tagger"] is None
