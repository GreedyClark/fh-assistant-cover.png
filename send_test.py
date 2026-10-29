import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import Settings
from app.db import Database
from app.messages import TOP_MARKER_SCORE, format_project, project_keyboard
from app.models import parse_project
from app.prefs import PrefsStore
from app.scoring import score_project

LOOKBACK_HOURS = 72
TEST_HEADER = "<i>Тестове повідомлення</i>\n\n"


def sample(project_id: int, name: str, description: str, skills: list[tuple[int, str]], bids: int) -> dict:
    return {
        "id": project_id,
        "attributes": {
            "name": name,
            "description": description,
            "budget": {"amount": 2000, "currency": "UAH"},
            "safe_type": "employer",
            "skills": [{"id": sid, "name": sname} for sid, sname in skills],
            "status": {"id": 11},
            "bid_count": bids,
            "published_at": (datetime.now(UTC) - timedelta(minutes=20)).isoformat(),
            "employer": {"id": 0, "login": "test", "rating": 0, "positive_reviews": 0,
                         "negative_reviews": 0, "completed_projects": 0},
        },
        "links": {"self": {"web": "https://freelancehunt.com/projects"}},
    }


SAMPLES = {
    "high": sample(
        -1, "Telegram-бот для запису клієнтів на aiogram",
        "Потрібен Telegram-бот для салону: запис клієнтів, нагадування, адмінка з розкладом. "
        "Дані зберігати в SQLite, інтеграція з Google Calendar через API. "
        "Готові надати доступи і детальне ТЗ, відповідаю швидко.",
        [(180, "Розробка ботів"), (22, "Python")], 1,
    ),
    "medium": sample(
        -2, "Парсер цін конкурентів у Google Sheets",
        "Треба скрипт, який раз на добу збирає ціни з трьох сайтів і записує в таблицю. "
        "Сайти без захисту від ботів, приклади сторінок дам. Бажано з інструкцією запуску.",
        [(169, "Парсинг даних")], 9,
    ),
    "low": sample(
        -3, "Доробити мобільний додаток", "Потрібно доробити мобільний додаток, деталі в особистих.",
        [(22, "Python")], 18,
    ),
}


def tier(value: int, loud_threshold: int) -> str:
    if value >= max(TOP_MARKER_SCORE, loud_threshold):
        return "high"
    if value >= loud_threshold:
        return "medium"
    return "low"


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    settings = Settings()
    db = Database(settings.db_path)
    await db.connect()
    prefs_store = PrefsStore(db, settings)
    await prefs_store.load()
    threshold = prefs_store.prefs.loud_threshold

    picked: dict[str, tuple] = {}
    for raw, budget_uah, first_seen_at, cross in await db.recent_matched(LOOKBACK_HOURS):
        project = parse_project(json.loads(raw))
        seen_at = datetime.fromisoformat(first_seen_at)
        score = score_project(project, budget_uah, seen_at, bool(cross))
        key = tier(score.value, threshold)
        if key not in picked or score.value > picked[key][2].value:
            picked[key] = (project, budget_uah, score, bool(cross), seen_at)

    bot = Bot(
        settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    try:
        for key in ("high", "medium", "low"):
            if key in picked:
                project, budget_uah, score, cross, seen_at = picked[key]
                source = "з бази"
            else:
                project = parse_project(SAMPLES[key])
                budget_uah = project.budget_amount
                score = score_project(project, budget_uah, datetime.now(UTC))
                cross, seen_at, source = False, None, "зразок"
            text = TEST_HEADER + format_project(project, budget_uah, score, cross, seen_at, threshold)
            await bot.send_message(
                settings.allowed_user_id,
                text,
                reply_markup=project_keyboard(project),
                disable_notification=score.value < threshold,
            )
            print(f"{key}: {score.value} ({source}) {project.name[:60]}")
            await asyncio.sleep(0.5)
    finally:
        await bot.session.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
