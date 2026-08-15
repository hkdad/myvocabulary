"""Seed family accounts and optional list assignments."""

import asyncio

from sqlalchemy import select

from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models.learner import Learner
from app.models.user import User
from app.models.word_list import WordList
from app.services import word_list_service

SEED_USERS = [
    {
        "username": "parent",
        "password": "parent123",
        "role": "parent",
        "learner": None,
    },
    {
        "username": "mia",
        "password": "mia",
        "role": "learner",
        "learner": {
            "display_name": "Mia",
            "age": 13,
            "english_level": "B1",
            "ui_mode": "teen",
            "emoji": "🌸",
            "daily_review_goal": 10,
            "daily_new_word_goal": 8,
            "daily_learning_retention_mix": 1,
            "daily_mastered_retention_mix": 1,
        },
    },
    {
        "username": "leo",
        "password": "leo",
        "role": "learner",
        "learner": {
            "display_name": "Leo",
            "age": 9,
            "english_level": "A2",
            "ui_mode": "kid",
            "emoji": "🚀",
            "daily_review_goal": 7,
            "daily_new_word_goal": 5,
            "daily_learning_retention_mix": 1,
            "daily_mastered_retention_mix": 1,
        },
    },
    {
        "username": "max",
        "password": "max",
        "role": "learner",
        "learner": {
            "display_name": "Max",
            "age": 5,
            "english_level": "PRE-A1",
            "ui_mode": "kid",
            "emoji": "🐶",
            "daily_review_goal": 5,
            "daily_new_word_goal": 3,
            "daily_learning_retention_mix": 1,
            "daily_mastered_retention_mix": 1,
        },
    },
]


async def seed_users(db) -> tuple[User, Learner, Learner]:
    await db.flush()

    parent: User | None = None
    mia_learner: Learner | None = None
    leo_learner: Learner | None = None

    for entry in SEED_USERS:
        result = await db.execute(select(User).where(User.username == entry["username"]))
        existing = result.scalar_one_or_none()
        if existing is not None:
            # Keep demo logins predictable across re-seeds (username == password for kids).
            existing.password_hash = hash_password(entry["password"])
            print(f"Reset demo password: {entry['username']}")
            if entry["username"] == "parent":
                parent = existing
            elif entry["username"] == "mia":
                mia_learner = (
                    await db.execute(select(Learner).where(Learner.user_id == existing.id))
                ).scalar_one()
            elif entry["username"] == "leo":
                leo_learner = (
                    await db.execute(select(Learner).where(Learner.user_id == existing.id))
                ).scalar_one()
            continue

        user = User(
            username=entry["username"],
            password_hash=hash_password(entry["password"]),
            role=entry["role"],
            parent_id=parent.id if entry["role"] == "learner" and parent else None,
            is_active=True,
        )
        db.add(user)
        await db.flush()

        if entry["role"] == "parent":
            parent = user

        if entry["learner"]:
            learner = Learner(
                user_id=user.id,
                display_name=entry["learner"]["display_name"],
                age=entry["learner"]["age"],
                english_level=entry["learner"]["english_level"],
                ui_mode=entry["learner"]["ui_mode"],
                emoji=entry["learner"].get("emoji"),
                daily_review_goal=entry["learner"]["daily_review_goal"],
                daily_new_word_goal=entry["learner"].get("daily_new_word_goal", 5),
                daily_learning_retention_mix=entry["learner"].get(
                    "daily_learning_retention_mix", 1
                ),
                daily_mastered_retention_mix=entry["learner"].get(
                    "daily_mastered_retention_mix", 1
                ),
            )
            db.add(learner)
            await db.flush()
            if entry["username"] == "mia":
                mia_learner = learner
            elif entry["username"] == "leo":
                leo_learner = learner
        print(f"Created user: {entry['username']}")

    await db.commit()
    if parent is None or mia_learner is None or leo_learner is None:
        parent = (await db.execute(select(User).where(User.username == "parent"))).scalar_one()
        mia_learner = (
            await db.execute(select(Learner).join(User).where(User.username == "mia"))
        ).scalar_one()
        leo_learner = (
            await db.execute(select(Learner).join(User).where(User.username == "leo"))
        ).scalar_one()
    return parent, mia_learner, leo_learner


async def seed_assignments(
    db,
    parent: User,
    mia_learner: Learner,
    leo_learner: Learner,
) -> None:
    curated = await db.execute(
        select(WordList)
        .where(WordList.source == "curated")
        .order_by(WordList.level_tag, WordList.name)
    )
    lists = curated.scalars().all()
    a2_lists = [word_list for word_list in lists if word_list.level_tag == "A2"]
    b1_lists = [word_list for word_list in lists if word_list.level_tag == "B1"]

    if a2_lists:
        await word_list_service.assign_word_list(
            db,
            a2_lists[0],
            parent_id=parent.id,
            learner_ids=[leo_learner.id],
        )
        print(f"Assigned {a2_lists[0].name} to Leo")

    for word_list in b1_lists[:2]:
        await word_list_service.assign_word_list(
            db,
            word_list,
            parent_id=parent.id,
            learner_ids=[mia_learner.id],
        )
        print(f"Assigned {word_list.name} to Mia")


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        await seed_users(db)

    async with AsyncSessionLocal() as db:
        parent = (await db.execute(select(User).where(User.username == "parent"))).scalar_one()
        mia_learner = (
            await db.execute(select(Learner).join(User).where(User.username == "mia"))
        ).scalar_one()
        leo_learner = (
            await db.execute(select(Learner).join(User).where(User.username == "leo"))
        ).scalar_one()
        await seed_assignments(db, parent, mia_learner, leo_learner)

    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
