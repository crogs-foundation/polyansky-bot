from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from database.models import Base


class DatabaseManager:
    """
    Manages database lifecycle and session creation.

    Follows singleton pattern to ensure single engine instance.
    """

    def __init__(self, db_path: Path, echo: bool = False):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file.
            echo: If True, log all SQL statements.
        """
        self.db_path = db_path
        self.echo = echo
        self._engine: AsyncEngine | None = None
        self._session_maker: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        """Get or create database engine."""
        if self._engine is None:
            # Ensure parent directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Create async engine for SQLite
            self._engine = create_async_engine(
                f"sqlite+aiosqlite:///{self.db_path}",
                echo=self.echo,
                # SQLite-specific optimizations
                connect_args={"check_same_thread": False},
            )
        return self._engine

    @property
    def session_maker(self) -> async_sessionmaker[AsyncSession]:
        """Get or create session maker."""
        if self._session_maker is None:
            self._session_maker = async_sessionmaker(
                self.engine, class_=AsyncSession, expire_on_commit=False
            )
        return self._session_maker

    async def init_database(self) -> None:
        """
        Initialize database schema.

        Creates all tables defined in models if they don't exist.
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        """Close database connection and cleanup resources."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_maker = None

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Provide transactional scope for database operations.

        Usage:
            async with db_manager.session() as session:
                result = await session.execute(query)

        Yields:
            AsyncSession: Database session with automatic commit/rollback.
        """
        async with self.session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
