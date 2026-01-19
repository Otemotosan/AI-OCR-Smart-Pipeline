"""Unit tests for Distributed Lock."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from core.lock import (
    HEARTBEAT_INTERVAL_SECONDS,
    LOCK_TTL_SECONDS,
    DistributedLock,
    LockNotAcquiredError,
)

# ============================================================
# File Hash Tests
# ============================================================


class TestFileHash:
    """Test SHA-256 file hashing."""

    def test_compute_file_hash(self) -> None:
        """Test that file hash is computed correctly."""
        content = b"test content"
        hash_val = DistributedLock.compute_file_hash(content)

        assert hash_val.startswith("sha256:")
        assert len(hash_val) == 71  # "sha256:" + 64 hex chars

    def test_hash_consistency(self) -> None:
        """Test that same content produces same hash."""
        content = b"consistent content"
        hash1 = DistributedLock.compute_file_hash(content)
        hash2 = DistributedLock.compute_file_hash(content)

        assert hash1 == hash2

    def test_different_content_different_hash(self) -> None:
        """Test that different content produces different hash."""
        content1 = b"content1"
        content2 = b"content2"
        hash1 = DistributedLock.compute_file_hash(content1)
        hash2 = DistributedLock.compute_file_hash(content2)

        assert hash1 != hash2

    def test_empty_content(self) -> None:
        """Test hashing empty content."""
        content = b""
        hash_val = DistributedLock.compute_file_hash(content)

        assert hash_val.startswith("sha256:")


# ============================================================
# Lock Acquisition Tests
# ============================================================


class TestLockAcquisition:
    """Test lock acquisition logic."""

    def test_acquire_new_lock(self) -> None:
        """Test acquiring lock for new document."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock transaction
        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_snapshot

        lock = DistributedLock(mock_db, ttl_seconds=60, heartbeat_interval=10)

        with (
            patch.object(lock, "_start_heartbeat"),
            patch.object(lock, "_stop_heartbeat_thread"),
            lock.acquire("sha256:test123") as doc_ref,
        ):
            assert doc_ref == mock_doc_ref

    def test_acquire_completed_document_fails(self) -> None:
        """Test that acquiring lock for completed document fails."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        lock = DistributedLock(mock_db)

        # Mock _acquire_lock to return False (already completed)
        with (
            patch.object(lock, "_acquire_lock", return_value=False),
            pytest.raises(LockNotAcquiredError) as exc_info,
            lock.acquire("sha256:test123"),
        ):
            pass

        assert "already being processed or completed" in str(exc_info.value)

    def test_acquire_active_lock_fails(self) -> None:
        """Test that acquiring active lock fails."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        lock = DistributedLock(mock_db)

        # Mock _acquire_lock to return False (active lock held by another)
        with (
            patch.object(lock, "_acquire_lock", return_value=False),
            pytest.raises(LockNotAcquiredError),
            lock.acquire("sha256:test123"),
        ):
            pass

    def test_acquire_expired_lock_succeeds(self) -> None:
        """Test that acquiring expired lock succeeds (takeover)."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock expired lock
        now = datetime.now(UTC)
        past = now - timedelta(minutes=5)
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "status": "PENDING",
            "lock_expires_at": past,
        }
        mock_doc_ref.get.return_value = mock_snapshot

        lock = DistributedLock(mock_db, ttl_seconds=60, heartbeat_interval=10)

        with (
            patch.object(lock, "_start_heartbeat"),
            patch.object(lock, "_stop_heartbeat_thread"),
            lock.acquire("sha256:test123") as doc_ref,
        ):
            assert doc_ref == mock_doc_ref


# ============================================================
# Heartbeat Tests
# ============================================================


class TestHeartbeat:
    """Test heartbeat mechanism."""

    def test_heartbeat_starts(self) -> None:
        """Test that heartbeat thread starts."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock new document
        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_snapshot

        lock = DistributedLock(mock_db, ttl_seconds=60, heartbeat_interval=1)

        with lock.acquire("sha256:test123"):
            # Heartbeat should be running
            assert lock._heartbeat_thread is not None
            assert lock._heartbeat_thread.is_alive()

    def test_heartbeat_stops_on_exit(self) -> None:
        """Test that heartbeat stops when context exits."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock new document
        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_snapshot

        lock = DistributedLock(mock_db, ttl_seconds=60, heartbeat_interval=1)

        with lock.acquire("sha256:test123"):
            pass

        # Heartbeat should be stopped
        time.sleep(0.1)  # Give thread time to clean up
        assert lock._heartbeat_thread is None or not lock._heartbeat_thread.is_alive()

    def test_heartbeat_extends_lock(self) -> None:
        """Test that heartbeat extends lock TTL."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock new document
        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_snapshot

        lock = DistributedLock(mock_db, ttl_seconds=60, heartbeat_interval=0.1)

        with lock.acquire("sha256:test123"):
            # Wait for at least one heartbeat
            time.sleep(0.3)

        # Verify update was called at least once
        assert mock_doc_ref.update.call_count >= 1
        call_args = mock_doc_ref.update.call_args_list[0][0][0]
        assert "lock_expires_at" in call_args
        assert "updated_at" in call_args

    def test_heartbeat_handles_exceptions(self) -> None:
        """Test that heartbeat handles exceptions gracefully."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock new document
        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_snapshot

        # Make update raise exception
        mock_doc_ref.update.side_effect = Exception("Network error")

        lock = DistributedLock(mock_db, ttl_seconds=60, heartbeat_interval=0.1)

        # Should not raise exception despite update failures
        with lock.acquire("sha256:test123"):
            time.sleep(0.3)


# ============================================================
# Context Manager Tests
# ============================================================


class TestContextManager:
    """Test context manager behavior."""

    def test_context_manager_yields_doc_ref(self) -> None:
        """Test that context manager yields document reference."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock new document
        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_snapshot

        lock = DistributedLock(mock_db, ttl_seconds=60, heartbeat_interval=10)

        with (
            patch.object(lock, "_start_heartbeat"),
            patch.object(lock, "_stop_heartbeat_thread"),
            lock.acquire("sha256:test123") as doc_ref,
        ):
            assert doc_ref is not None
            assert doc_ref == mock_doc_ref

    def test_context_manager_cleans_up_on_exception(self) -> None:
        """Test that context manager cleans up even on exception."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock new document
        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_snapshot

        lock = DistributedLock(mock_db, ttl_seconds=60, heartbeat_interval=10)

        with (
            patch.object(lock, "_start_heartbeat"),
            patch.object(lock, "_stop_heartbeat_thread") as mock_stop,
        ):
            try:
                with lock.acquire("sha256:test123"):
                    raise ValueError("Test error")
            except ValueError:
                pass

            # Verify cleanup was called
            mock_stop.assert_called_once()


# ============================================================
# Release Tests
# ============================================================


class TestRelease:
    """Test lock release."""

    def test_release_completed(self) -> None:
        """Test releasing lock with COMPLETED status."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()

        lock = DistributedLock(mock_db)
        lock.release(mock_doc_ref, "COMPLETED")

        mock_doc_ref.update.assert_called_once()
        call_args = mock_doc_ref.update.call_args[0][0]
        assert call_args["status"] == "COMPLETED"
        assert call_args["lock_expires_at"] is None
        assert "updated_at" in call_args

    def test_release_failed_with_error(self) -> None:
        """Test releasing lock with FAILED status and error message."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()

        lock = DistributedLock(mock_db)
        lock.release(mock_doc_ref, "FAILED", "Extraction failed")

        mock_doc_ref.update.assert_called_once()
        call_args = mock_doc_ref.update.call_args[0][0]
        assert call_args["status"] == "FAILED"
        assert call_args["error_message"] == "Extraction failed"
        assert call_args["lock_expires_at"] is None


# ============================================================
# Integration Tests
# ============================================================


class TestIntegration:
    """Test end-to-end scenarios."""

    def test_full_lock_lifecycle(self) -> None:
        """Test complete lock acquisition, processing, and release."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock new document
        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_snapshot

        lock = DistributedLock(mock_db, ttl_seconds=60, heartbeat_interval=10)

        # Acquire lock
        with (
            patch.object(lock, "_start_heartbeat") as mock_start,
            patch.object(lock, "_stop_heartbeat_thread") as mock_stop,
        ):
            with lock.acquire("sha256:test123") as doc_ref:
                # Verify heartbeat started
                mock_start.assert_called_once()

                # Simulate processing
                doc_ref.update({"gcs_source_path": "gs://bucket/file.pdf"})

            # Verify heartbeat stopped
            mock_stop.assert_called_once()

        # Release lock
        lock.release(mock_doc_ref, "COMPLETED")

        # Verify updates
        assert mock_doc_ref.update.call_count >= 2

    def test_concurrent_lock_attempts(self) -> None:
        """Test that concurrent lock attempts are handled correctly."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        lock1 = DistributedLock(mock_db, ttl_seconds=60, heartbeat_interval=10)
        lock2 = DistributedLock(mock_db, ttl_seconds=60, heartbeat_interval=10)

        # First lock succeeds (new document)
        with (
            patch.object(lock1, "_acquire_lock", return_value=True),
            patch.object(lock1, "_start_heartbeat"),
            patch.object(lock1, "_stop_heartbeat_thread"),
            lock1.acquire("sha256:test123"),
        ):
            pass

        # Second lock fails (already locked by first)
        with (
            patch.object(lock2, "_acquire_lock", return_value=False),
            pytest.raises(LockNotAcquiredError),
            lock2.acquire("sha256:test123"),
        ):
            pass


# ============================================================
# Constants Tests
# ============================================================


class TestConstants:
    """Test module constants."""

    def test_lock_ttl_constant(self) -> None:
        """Test LOCK_TTL_SECONDS constant."""
        assert LOCK_TTL_SECONDS == 600

    def test_heartbeat_interval_constant(self) -> None:
        """Test HEARTBEAT_INTERVAL_SECONDS constant."""
        assert HEARTBEAT_INTERVAL_SECONDS == 120

    def test_custom_ttl(self) -> None:
        """Test creating lock with custom TTL."""
        mock_db = MagicMock()
        lock = DistributedLock(mock_db, ttl_seconds=300)

        assert lock.ttl_seconds == 300

    def test_custom_heartbeat_interval(self) -> None:
        """Test creating lock with custom heartbeat interval."""
        mock_db = MagicMock()
        lock = DistributedLock(mock_db, heartbeat_interval=60)

        assert lock.heartbeat_interval == 60


# ============================================================
# Stop Heartbeat Tests
# ============================================================


class TestStopHeartbeat:
    """Test _stop_heartbeat_thread method."""

    def test_stop_heartbeat_when_no_thread(self) -> None:
        """Test _stop_heartbeat_thread when thread doesn't exist."""
        mock_db = MagicMock()
        lock = DistributedLock(mock_db)

        # Should not raise
        lock._stop_heartbeat_thread()
        assert lock._heartbeat_thread is None

    def test_stop_heartbeat_when_thread_not_alive(self) -> None:
        """Test _stop_heartbeat_thread when thread is not alive."""
        mock_db = MagicMock()
        lock = DistributedLock(mock_db)

        # Create a mock thread that is not alive
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False
        lock._heartbeat_thread = mock_thread

        # Should not call join
        lock._stop_heartbeat_thread()
        mock_thread.join.assert_not_called()

    def test_stop_heartbeat_when_thread_alive(self) -> None:
        """Test _stop_heartbeat_thread when thread is alive."""
        mock_db = MagicMock()
        lock = DistributedLock(mock_db)

        # Create a mock thread that is alive
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        lock._heartbeat_thread = mock_thread

        lock._stop_heartbeat_thread()

        # Should set stop event, join thread, and clear reference
        mock_thread.join.assert_called_once_with(timeout=2.0)
        assert lock._heartbeat_thread is None


# ============================================================
# Start Heartbeat Tests
# ============================================================


class TestStartHeartbeat:
    """Test _start_heartbeat method."""

    def test_start_heartbeat_creates_thread(self) -> None:
        """Test _start_heartbeat creates and starts a thread."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()

        lock = DistributedLock(mock_db, heartbeat_interval=0.1)

        lock._start_heartbeat(mock_doc_ref)

        # Thread should be created and running
        assert lock._heartbeat_thread is not None
        assert lock._heartbeat_thread.is_alive()

        # Clean up
        lock._stop_heartbeat.set()
        lock._heartbeat_thread.join(timeout=1.0)

    def test_start_heartbeat_clears_stop_event(self) -> None:
        """Test _start_heartbeat clears the stop event."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()

        lock = DistributedLock(mock_db, heartbeat_interval=100)  # Long interval

        # Set the stop event first
        lock._stop_heartbeat.set()

        lock._start_heartbeat(mock_doc_ref)

        # Stop event should be cleared
        assert not lock._stop_heartbeat.is_set()

        # Clean up
        lock._stop_heartbeat.set()
        lock._heartbeat_thread.join(timeout=1.0)
