import asyncio
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.rate_limit import limiter
from app.core.security import hash_password
from app.core.sm2 import DEFAULT_EASE_FACTOR
from app.database import Base, get_db
from app.main import app
from app.models.dictionary import DictionaryEntry
from app.models.learner import Learner
from app.models.srs import SrsCard
from app.models.user import User

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

FTS5_STATEMENTS = [
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS dictionary_entries_fts USING fts5(
        word,
        definition,
        example_sentence,
        content='dictionary_entries',
        content_rowid='id',
        tokenize='porter unicode61'
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS dictionary_entries_ai AFTER INSERT ON dictionary_entries BEGIN
      INSERT INTO dictionary_entries_fts(rowid, word, definition, example_sentence)
      VALUES (new.id, new.word, new.definition, new.example_sentence);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS dictionary_entries_ad AFTER DELETE ON dictionary_entries BEGIN
      INSERT INTO dictionary_entries_fts(
        dictionary_entries_fts, rowid, word, definition, example_sentence
      )
      VALUES ('delete', old.id, old.word, old.definition, old.example_sentence);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS dictionary_entries_au AFTER UPDATE ON dictionary_entries BEGIN
      INSERT INTO dictionary_entries_fts(
        dictionary_entries_fts, rowid, word, definition, example_sentence
      )
      VALUES ('delete', old.id, old.word, old.definition, old.example_sentence);
      INSERT INTO dictionary_entries_fts(rowid, word, definition, example_sentence)
      VALUES (new.id, new.word, new.definition, new.example_sentence);
    END
    """,
]


async def setup_dictionary_fts(conn) -> None:
    for statement in FTS5_STATEMENTS:
        await conn.execute(text(statement))


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await setup_dictionary_fts(conn)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        parent = User(
            username="parent",
            password_hash=hash_password("parent123"),
            role="parent",
            is_active=True,
        )
        session.add(parent)
        await session.flush()

        mia_user = User(
            username="mia",
            password_hash=hash_password("mia"),
            role="learner",
            parent_id=parent.id,
            is_active=True,
        )
        session.add(mia_user)
        await session.flush()
        session.add(
            Learner(
                user_id=mia_user.id,
                display_name="Mia",
                age=13,
                english_level="A1",
                ui_mode="teen",
                emoji="🌸",
                daily_review_goal=10,
                daily_new_word_goal=8,
                daily_learning_retention_mix=1,
                daily_mastered_retention_mix=1,
            )
        )

        leo_user = User(
            username="leo",
            password_hash=hash_password("leo"),
            role="learner",
            parent_id=parent.id,
            is_active=True,
        )
        session.add(leo_user)
        await session.flush()
        session.add(
            Learner(
                user_id=leo_user.id,
                display_name="Leo",
                age=9,
                english_level="A1",
                ui_mode="kid",
                emoji="🚀",
                daily_review_goal=7,
                daily_new_word_goal=5,
                daily_learning_retention_mix=1,
                daily_mastered_retention_mix=1,
            )
        )

        max_user = User(
            username="max",
            password_hash=hash_password("max"),
            role="learner",
            parent_id=parent.id,
            is_active=True,
        )
        session.add(max_user)
        await session.flush()
        session.add(
            Learner(
                user_id=max_user.id,
                display_name="Max",
                age=5,
                english_level="PRE-A1",
                ui_mode="kid",
                emoji="🐶",
                daily_review_goal=5,
                daily_new_word_goal=3,
                daily_learning_retention_mix=1,
                daily_mastered_retention_mix=1,
            )
        )
        await session.flush()

        leo_learner = (
            await session.execute(select(Learner).where(Learner.user_id == leo_user.id))
        ).scalar_one()
        sample_entry = DictionaryEntry(
            word="hello",
            phonetic="/həˈloʊ/",
            part_of_speech="interjection",
            definition='"Hello!" or an equivalent greeting.',
            source="seed",
        )
        session.add(sample_entry)
        await session.flush()
        session.add(
            SrsCard(
                learner_id=leo_learner.id,
                dictionary_entry_id=sample_entry.id,
                ease_factor=DEFAULT_EASE_FACTOR,
                interval_days=0,
                repetitions=0,
                due_at=datetime.now(UTC),
                state="new",
                released_at=datetime.now(UTC),
            )
        )
        await session.commit()
        yield session

    await engine.dispose()


@pytest.fixture(autouse=True)
def reset_rate_limits() -> None:
    limiter.reset()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    app.dependency_overrides.clear()
