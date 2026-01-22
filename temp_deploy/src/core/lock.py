"""Distributed Lock with Firestore and Heartbeat.

Provides idempotency guarantees for document processing using
Firestore-backed distributed locking with automatic heartbeat extension.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, TypeVar

_F = TypeVar("_F", bound=Callable)

if TYPE_CHECKING:
    from google.cloud import firestore
else:
    try:
        from google.cloud import firestore
    except ImportError:
        # Allow tests to run without google-cloud-firestore installed
        # Create a mock module with transactional decorator
        from types import SimpleNamespace

        def _mock_transactional(func: _F) -> _F:
            """Mock transactional decorator for testing."""
            return func

        firestore = SimpleNamespace(transactional=_mock_transactional)  # type: ignore[assignment]


# Constants
LOCK_TTL_SECONDS = 600  # 10 minutes
HEARTBEAT_INTERVAL_SECONDS = 120  # 2 minutes


class LockNotAcquiredError(Exception):
    """Raised when lock cannot be acquired."""


class DistributedLock:
    """Distributed lock with automatic heartbeat extension.

    Provides idempotency guarantees using Firestore as the lock store.
    Automatically extends lock TTL via heartbeat to prevent zombie locks.

    Examples:
        >>> lock = DistributedLock(firestore_client)
        >>> with lock.acquire("sha256:abc123") as doc_ref:
        ...     # Process document
        ...     doc_ref.update({"status": "COMPLETED"})
    """

    def __init__(
        self,
        firestore_client: firestore.Client,
        ttl_seconds: int = LOCK_TTL_SECONDS,
        heartbeat_interval: int = HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        """Initialize distributed lock manager.

        Args:
            firestore_client: Firestore client instance
            ttl_seconds: Lock time-to-live in seconds
            heartbeat_interval: Heartbeat extension interval in seconds
        """
        self.db = firestore_client
        self.ttl_seconds = ttl_seconds
        self.heartbeat_interval = heartbeat_interval
        self._heartbeat_thread: threading.Thread | None = None
        self._stop_heartbeat = threading.Event()

    @staticmethod
    def compute_file_hash(content: bytes) -> str:
        """Compute SHA-256 hash of file content.

        Args:
            content: File content bytes

        Returns:
            Hash string in format "sha256:hexdigest"

        Examples:
            >>> content = b"test content"
            >>> hash_val = DistributedLock.compute_file_hash(content)
            >>> hash_val.startswith("sha256:")
            True
        """
        return f"sha256:{hashlib.sha256(content).hexdigest()}"

    @contextmanager
    def acquire(self, doc_hash: str) -> Iterator[firestore.DocumentReference]:
        """Acquire distributed lock with automatic heartbeat.

        Args:
            doc_hash: Document hash (typically SHA-256)

        Yields:
            Firestore document reference for the locked document

        Raises:
            LockNotAcquiredError: If lock cannot be acquired

        Examples:
            >>> with lock.acquire("sha256:abc123") as doc_ref:
            ...     doc_ref.update({"gcs_source_path": "gs://..."})
            ...     # Long processing operation
            ...     doc_ref.update({"status": "COMPLETED"})
        """
        doc_ref = self.db.collection("processed_documents").document(doc_hash)

        try:
            # Acquire lock
            if not self._acquire_lock(doc_ref, doc_hash):
                raise LockNotAcquiredError(
                    f"Document {doc_hash} is already being processed or completed"
                )

            # Start heartbeat
            self._start_heartbeat(doc_ref)

            yield doc_ref

        finally:
            # Stop heartbeat
            self._stop_heartbeat_thread()

    def _acquire_lock(self, doc_ref: firestore.DocumentReference, doc_hash: str) -> bool:
        """Atomically acquire processing lock.

        Args:
            doc_ref: Firestore document reference
            doc_hash: Document hash

        Returns:
            True if lock acquired, False if already processed/processing

        Notes:
            Uses Firestore transaction to ensure atomicity.
            Handles lock expiry and takeover for zombie locks.
        """
        transaction = self.db.transaction()

        @firestore.transactional
        def _acquire(trans: firestore.Transaction) -> bool:
            snapshot = doc_ref.get(transaction=trans)
            now = datetime.now(UTC)

            if snapshot.exists:
                data = snapshot.to_dict()

                # Already completed — skip
                if data.get("status") == "COMPLETED":
                    return False

                # Lock held by another instance — check expiry
                if data.get("status") == "PENDING":
                    expires_at = data.get("lock_expires_at")
                    if expires_at and expires_at.replace(tzinfo=UTC) > now:
                        return False  # Lock still valid

                    # Lock expired — take over

            # Acquire lock
            trans.set(
                doc_ref,
                {
                    "hash": doc_hash,
                    "status": "PENDING",
                    "lock_expires_at": now + timedelta(seconds=self.ttl_seconds),
                    "created_at": (now if not snapshot.exists else data.get("created_at", now)),
                    "updated_at": now,
                },
                merge=True,
            )
            return True

        return _acquire(transaction)

    def _start_heartbeat(self, doc_ref: firestore.DocumentReference) -> None:
        """Start heartbeat thread to extend lock TTL.

        Args:
            doc_ref: Firestore document reference
        """
        self._stop_heartbeat.clear()

        def _heartbeat_worker() -> None:
            """Worker function for heartbeat thread."""
            while not self._stop_heartbeat.is_set():
                # Wait for interval or stop signal
                if self._stop_heartbeat.wait(timeout=self.heartbeat_interval):
                    break

                # Extend lock TTL
                # Log but don't crash — lock will eventually expire
                # In production, use structlog here
                with suppress(Exception):
                    doc_ref.update(
                        {
                            "lock_expires_at": datetime.now(UTC)
                            + timedelta(seconds=self.ttl_seconds),
                            "updated_at": datetime.now(UTC),
                        }
                    )

        self._heartbeat_thread = threading.Thread(target=_heartbeat_worker, daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat_thread(self) -> None:
        """Stop heartbeat thread gracefully."""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._stop_heartbeat.set()
            self._heartbeat_thread.join(timeout=2.0)
            self._heartbeat_thread = None

    def release(
        self, doc_ref: firestore.DocumentReference, status: str, error_message: str | None = None
    ) -> None:
        """Release lock and update final status.

        Args:
            doc_ref: Firestore document reference
            status: Final status ("COMPLETED" or "FAILED")
            error_message: Optional error message for FAILED status

        Examples:
            >>> lock.release(doc_ref, "COMPLETED")
            >>> lock.release(doc_ref, "FAILED", "Extraction failed")
        """
        update_data = {
            "status": status,
            "updated_at": datetime.now(UTC),
            "lock_expires_at": None,  # Clear expiry on completion
        }

        if error_message:
            update_data["error_message"] = error_message

        doc_ref.update(update_data)
