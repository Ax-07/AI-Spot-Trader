from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai_spot_trader.persistence.models import Base


class Database:
    """Own the async SQLAlchemy engine and session factory lifecycle."""

    def __init__(self, url: str, *, echo: bool = False) -> None:
        if not url.strip():
            raise ValueError("database url cannot be empty")
        self.engine: AsyncEngine = create_async_engine(url, echo=echo, pool_pre_ping=True)
        self.sessions = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def close(self) -> None:
        """Dispose pooled connections owned by this database instance."""

        await self.engine.dispose()

    async def create_schema_for_tests(self) -> None:
        """Create tables directly for isolated tests; production uses Alembic migrations."""

        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
