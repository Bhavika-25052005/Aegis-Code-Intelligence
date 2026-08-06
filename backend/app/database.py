from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    from sqlalchemy import text, inspect as sa_inspect

    async with engine.begin() as conn:
        def _migrate(connection):
            inspector = sa_inspect(connection)
            if "test_runs" in inspector.get_table_names():
                fks = inspector.get_foreign_keys("test_runs")
                task_fk = [fk for fk in fks if "tasks" in (fk.get("referred_table") or "")]
                if task_fk:
                    connection.execute(text("DROP TABLE test_runs"))

        await conn.run_sync(_migrate)
        await conn.run_sync(Base.metadata.create_all)
