"""
Event store implementations for demonstrating resumability functionality.
Includes both in-memory and SQLite-based implementations.
"""

import logging
import os
import sqlite3
from collections import deque
from dataclasses import dataclass
from uuid import uuid4
import json
import asyncio
import time
from datetime import datetime, timedelta

from mcp.server.streamable_http import (
    EventCallback,
    EventId,
    EventMessage,
    EventStore,
    StreamId,
)
from mcp.types import JSONRPCMessage

logger = logging.getLogger(__name__)


@dataclass
class EventEntry:
    """
    Represents an event entry in the event store.
    """

    event_id: EventId
    stream_id: StreamId
    message: JSONRPCMessage | None


class InMemoryEventStore(EventStore):
    """
    Simple in-memory implementation of the EventStore interface for resumability.
    This is primarily intended for examples and testing, not for production use
    where a persistent storage solution would be more appropriate.

    This implementation keeps only the last N events per stream for memory efficiency.
    """

    def __init__(self, max_events_per_stream: int = 100):
        """Initialize the event store.

        Args:
            max_events_per_stream: Maximum number of events to keep per stream
        """
        self.max_events_per_stream = max_events_per_stream
        # for maintaining last N events per stream
        self.streams: dict[StreamId, deque[EventEntry]] = {}
        # event_id -> EventEntry for quick lookup
        self.event_index: dict[EventId, EventEntry] = {}

    async def store_event(
        self, stream_id: StreamId, message: JSONRPCMessage | None
    ) -> EventId:
        """Stores an event with a generated event ID."""
        event_id = str(uuid4())
        event_entry = EventEntry(
            event_id=event_id, stream_id=stream_id, message=message
        )

        # Get or create deque for this stream
        if stream_id not in self.streams:
            self.streams[stream_id] = deque(maxlen=self.max_events_per_stream)

        # If deque is full, the oldest event will be automatically removed
        # We need to remove it from the event_index as well
        if len(self.streams[stream_id]) == self.max_events_per_stream:
            oldest_event = self.streams[stream_id][0]
            self.event_index.pop(oldest_event.event_id, None)

        # Add new event
        self.streams[stream_id].append(event_entry)
        self.event_index[event_id] = event_entry

        return event_id

    async def replay_events_after(
        self,
        last_event_id: EventId,
        send_callback: EventCallback,
    ) -> StreamId | None:
        """Replays events that occurred after the specified event ID."""
        if last_event_id not in self.event_index:
            logger.warning(f"Event ID {last_event_id} not found in store")
            return None

        # Get the stream and find events after the last one
        last_event = self.event_index[last_event_id]
        stream_id = last_event.stream_id
        stream_events = self.streams.get(last_event.stream_id, deque())

        # Events in deque are already in chronological order
        found_last = False
        for event in stream_events:
            if found_last:
                if event.message is not None:
                    await send_callback(EventMessage(event.message, event.event_id))
            elif event.event_id == last_event_id:
                found_last = True

        return stream_id


class SQLiteEventStore(EventStore):
    """
    SQLite-based implementation of the EventStore interface for resumability.
    Provides persistent storage suitable for personal cloud environments with low concurrency.

    This implementation maintains a SQLite database with events and provides the same
    interface as the InMemoryEventStore but with persistence.
    """

    def __init__(
        self,
        db_path: str = "events.db",
        max_events_per_stream: int = 100,
        max_event_age_days: int = 30,
        auto_cleanup_interval_hours: int = 24,
        max_db_size_mb: int = 100
    ):
        """Initialize the SQLite event store.

        Args:
            db_path: Path to the SQLite database file
            max_events_per_stream: Maximum number of events to keep per stream
            max_event_age_days: Maximum age of events in days before cleanup
            auto_cleanup_interval_hours: How often to run automatic cleanup (in hours)
            max_db_size_mb: Maximum size of the database in MB
        """
        self.db_path = db_path
        self.max_events_per_stream = max_events_per_stream
        self.max_event_age_days = max_event_age_days
        self.auto_cleanup_interval_hours = auto_cleanup_interval_hours
        self.max_db_size_mb = max_db_size_mb
        self._init_db()
        self._cleanup_task = None

    def _init_db(self):
        """Initialize the database schema if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    stream_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Create index for faster queries
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_stream_id ON events(stream_id)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_created_at ON events(created_at)")
            conn.commit()

    async def start_cleanup(self):
        """启动清理任务。必须在事件循环运行后调用。"""
        if self._cleanup_task is not None:
            return  # 防止多次启动任务

        async def cleanup_task():
            logger.info(
                f"Started automatic cleanup task (interval: {self.auto_cleanup_interval_hours}h)")
            while True:
                try:
                    # Wait for the specified interval
                    await asyncio.sleep(self.auto_cleanup_interval_hours * 3600)
                    # Run cleanup
                    await self.cleanup_old_events()
                    await self.vacuum_database()
                except asyncio.CancelledError:
                    # Task was cancelled, exit gracefully
                    break
                except Exception as e:
                    logger.error(f"Error in cleanup task: {e}")
                    # Wait a bit before retrying after an error
                    await asyncio.sleep(60)

        # Start the task in the background
        self._cleanup_task = asyncio.create_task(cleanup_task())

    async def stop_cleanup(self):
        """停止清理任务"""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Cleanup task stopped")

    def _serialize_message(self, message: JSONRPCMessage | None) -> str:
        """Serialize a JSONRPCMessage, or a priming event with no payload, for storage."""
        if message is None:
            return json.dumps(None)
        # Extract the root value from the JSONRPCMessage (a RootModel)
        message_dict = message.root.model_dump()
        return json.dumps(message_dict)

    def _deserialize_message(self, message_str: str) -> JSONRPCMessage | None:
        """Deserialize a string to a JSONRPCMessage, or None for priming events."""
        message_dict = json.loads(message_str)
        if message_dict is None:
            return None
        return JSONRPCMessage.model_validate(message_dict)

    async def cleanup_old_events(self):
        """删除超过最大保留时间的事件。"""
        # 计算截止日期
        cutoff_date = datetime.now() - timedelta(days=self.max_event_age_days)
        cutoff_str = cutoff_date.strftime('%Y-%m-%d %H:%M:%S')

        logger.info(f"Cleaning up events older than {cutoff_str}")

        def db_cleanup():
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 获取要删除的事件数量
                cursor.execute(
                    "SELECT COUNT(*) FROM events WHERE created_at < ?",
                    (cutoff_str,)
                )
                count = cursor.fetchone()[0]

                # 删除旧事件
                cursor.execute(
                    "DELETE FROM events WHERE created_at < ?",
                    (cutoff_str,)
                )
                conn.commit()
                return count

        # 在线程池中执行数据库操作
        count = await asyncio.get_event_loop().run_in_executor(None, db_cleanup)
        if count > 0:
            logger.info(f"Cleaned up {count} old events")
        return count

    async def vacuum_database(self):
        """执行VACUUM操作以回收空间并优化数据库。"""
        logger.info("Running database VACUUM operation")

        def db_vacuum():
            with sqlite3.connect(self.db_path) as conn:
                # 获取当前数据库大小
                db_size_bytes = os.path.getsize(self.db_path)
                db_size_mb = db_size_bytes / (1024 * 1024)

                # 执行VACUUM操作
                conn.execute("VACUUM")
                conn.commit()

                # 获取VACUUM后的大小
                new_size_bytes = os.path.getsize(self.db_path)
                new_size_mb = new_size_bytes / (1024 * 1024)

                return db_size_mb, new_size_mb

        # 在线程池中执行数据库操作
        before_mb, after_mb = await asyncio.get_event_loop().run_in_executor(None, db_vacuum)
        logger.info(
            f"Database size: {before_mb:.2f}MB → {after_mb:.2f}MB (saved {before_mb - after_mb:.2f}MB)")
        return before_mb, after_mb

    async def check_db_size(self):
        """检查数据库大小，如果超过限制则触发清理。"""
        def get_db_size():
            if os.path.exists(self.db_path):
                return os.path.getsize(self.db_path) / (1024 * 1024)
            return 0

        db_size_mb = await asyncio.get_event_loop().run_in_executor(None, get_db_size)

        if db_size_mb > self.max_db_size_mb:
            logger.warning(
                f"Database size ({db_size_mb:.2f}MB) exceeds limit ({self.max_db_size_mb}MB), triggering cleanup")
            # 先尝试基于时间的清理
            cleaned = await self.cleanup_old_events()
            if cleaned == 0:
                # 如果没有清理到旧事件，则删除最旧的一些事件，直到大小合适
                def emergency_cleanup():
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        # 计算需要删除的事件数量（估计值）
                        target_percent = 0.8  # 目标是将数据库缩小到最大大小的80%
                        target_size = self.max_db_size_mb * target_percent
                        percent_to_delete = 1 - (target_size / db_size_mb)

                        # 获取总事件数
                        cursor.execute("SELECT COUNT(*) FROM events")
                        total_events = cursor.fetchone()[0]

                        # 计算要删除的事件数
                        events_to_delete = int(
                            total_events * percent_to_delete)

                        if events_to_delete > 0:
                            # 删除最旧的事件
                            cursor.execute(
                                """DELETE FROM events WHERE event_id IN (
                                    SELECT event_id FROM events 
                                    ORDER BY created_at 
                                    LIMIT ?
                                )""",
                                (events_to_delete,)
                            )
                            conn.commit()
                            return events_to_delete
                        return 0

                deleted = await asyncio.get_event_loop().run_in_executor(None, emergency_cleanup)
                if deleted > 0:
                    logger.info(
                        f"Emergency cleanup: deleted {deleted} oldest events")

            # 执行VACUUM操作回收空间
            await self.vacuum_database()

    async def store_event(
        self, stream_id: StreamId, message: JSONRPCMessage | None
    ) -> EventId:
        """Stores an event with a generated event ID in SQLite database."""
        event_id = str(uuid4())
        message_str = self._serialize_message(message)

        # Run database operations in a thread pool to avoid blocking
        def db_store():
            with sqlite3.connect(self.db_path) as conn:
                # Insert the new event
                conn.execute(
                    "INSERT INTO events (event_id, stream_id, message) VALUES (?, ?, ?)",
                    (event_id, stream_id, message_str)
                )

                # Check if we need to prune old events
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM events WHERE stream_id = ?",
                    (stream_id,)
                )
                count = cursor.fetchone()[0]

                if count > self.max_events_per_stream:
                    # Delete oldest events beyond the limit
                    cursor.execute(
                        """DELETE FROM events WHERE event_id IN (
                            SELECT event_id FROM events 
                            WHERE stream_id = ? 
                            ORDER BY created_at 
                            LIMIT ?
                        )""",
                        (stream_id, count - self.max_events_per_stream)
                    )
                conn.commit()

        # Run in thread pool
        await asyncio.get_event_loop().run_in_executor(None, db_store)

        # 每次存储事件时检查数据库大小
        await self.check_db_size()

        return event_id

    async def replay_events_after(
        self,
        last_event_id: EventId,
        send_callback: EventCallback,
    ) -> StreamId | None:
        """Replays events that occurred after the specified event ID from SQLite database."""
        # Run database query in a thread pool
        def get_last_event():
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT stream_id, created_at FROM events WHERE event_id = ?",
                    (last_event_id,)
                )
                result = cursor.fetchone()
                return result

        result = await asyncio.get_event_loop().run_in_executor(None, get_last_event)
        if not result:
            logger.warning(f"Event ID {last_event_id} not found in store")
            return None

        stream_id, last_timestamp = result

        # Get events after the last one
        def get_newer_events():
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT event_id, message FROM events 
                       WHERE stream_id = ? AND created_at > ? 
                       ORDER BY created_at""",
                    (stream_id, last_timestamp)
                )
                return cursor.fetchall()

        events = await asyncio.get_event_loop().run_in_executor(None, get_newer_events)

        # Send each event through the callback. Priming events have no JSON-RPC
        # payload and are only used to reserve an SSE event id, so they should
        # not be replayed as application messages.
        for event_id, message_str in events:
            message = self._deserialize_message(message_str)
            if message is not None:
                await send_callback(EventMessage(message, event_id))

        return stream_id
