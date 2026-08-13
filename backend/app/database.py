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

            # Drop legacy test_runs if it has an invalid FK to tasks
            if "test_runs" in inspector.get_table_names():
                fks = inspector.get_foreign_keys("test_runs")
                task_fk = [fk for fk in fks if "tasks" in (fk.get("referred_table") or "")]
                if task_fk:
                    connection.execute(text("DROP TABLE test_runs"))

            tables = inspector.get_table_names()

            # Requirement Intelligence - user_stories columns
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

                # Day 2 - implementation plan columns
                if "implementation_plan" not in existing_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE user_stories "
                            "ADD COLUMN implementation_plan TEXT DEFAULT ''"
                        )
                    )
                if "implementation_plan_status" not in existing_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE user_stories "
                            "ADD COLUMN implementation_plan_status "
                            "VARCHAR(20) DEFAULT 'not_planned'"
                        )
                    )
                if "implementation_plan_approved_at" not in existing_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE user_stories "
                            "ADD COLUMN implementation_plan_approved_at DATETIME"
                        )
                    )

                # Day 3 - test intelligence columns
                if "test_plan" not in existing_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE user_stories "
                            "ADD COLUMN test_plan TEXT DEFAULT ''"
                        )
                    )
                if "test_status" not in existing_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE user_stories "
                            "ADD COLUMN test_status VARCHAR(30) DEFAULT 'not_started'"
                        )
                    )
                if "test_summary" not in existing_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE user_stories "
                            "ADD COLUMN test_summary TEXT DEFAULT ''"
                        )
                    )
                if "test_updated_at" not in existing_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE user_stories "
                            "ADD COLUMN test_updated_at DATETIME"
                        )
                    )

                # Day 4 - quality snapshot cache
                if "quality_snapshot" not in existing_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE user_stories "
                            "ADD COLUMN quality_snapshot TEXT DEFAULT ''"
                        )
                    )
                if "quality_snapshot_hash" not in existing_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE user_stories "
                            "ADD COLUMN quality_snapshot_hash VARCHAR(64) DEFAULT ''"
                        )
                    )

            # Day 2 - projects columns
            if "projects" in tables:
                project_columns = {
                    column["name"]
                    for column in inspector.get_columns("projects")
                }
                if "repository_index_commit" not in project_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE projects "
                            "ADD COLUMN repository_index_commit "
                            "VARCHAR(64) DEFAULT ''"
                        )
                    )
                if "repository_indexed_at" not in project_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE projects "
                            "ADD COLUMN repository_indexed_at DATETIME"
                        )
                    )

        await conn.run_sync(_migrate)
        await conn.run_sync(Base.metadata.create_all)
