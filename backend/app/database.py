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
    from sqlalchemy import inspect as sa_inspect, text

    async with engine.begin() as conn:
        def _migrate(connection):
            inspector = sa_inspect(connection)
            tables = inspector.get_table_names()

            # Existing migration retained from the project.
            if "test_runs" in tables:
                fks = inspector.get_foreign_keys("test_runs")
                task_fk = [
                    fk
                    for fk in fks
                    if "tasks" in (fk.get("referred_table") or "")
                ]
                if task_fk:
                    connection.execute(text("DROP TABLE test_runs"))

            # Day 1 - Requirement Intelligence migration.
            if "user_stories" in tables:
                existing_columns = {
                    column["name"]
                    for column in inspector.get_columns("user_stories")
                }
                if "requirement_analysis" not in existing_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE user_stories "
                            "ADD COLUMN requirement_analysis TEXT DEFAULT ''"
                        )
                    )
                if "requirement_analysis_status" not in existing_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE user_stories "
                            "ADD COLUMN requirement_analysis_status "
                            "VARCHAR(20) DEFAULT 'not_analyzed'"
                        )
                    )
                if "requirement_analysis_approved_at" not in existing_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE user_stories "
                            "ADD COLUMN requirement_analysis_approved_at DATETIME"
                        )
                    )

        await conn.run_sync(_migrate)
        await conn.run_sync(Base.metadata.create_all)
