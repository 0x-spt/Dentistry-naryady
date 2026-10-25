"""Telegram-бот: лаборант присылает фото наряда, бот отвечает статусом и пишет в таблицу.

Доступ — только по списку Telegram id (TELEGRAM_ALLOWED_IDS): каждое фото стоит денег за API
и попадает в таблицу заказчика. Пустой список = доступа нет ни у кого (закрыто по умолчанию).

Каждое фото сохраняется в data/inbox/<дата>/ до распознавания: если упал API или Google,
оригинал не потерян, и его можно догнать командой `naryad process`.
"""

import asyncio
import logging
from datetime import date
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from naryad.evaluation import PHOTO_SUFFIXES
from naryad.pipeline import Pipeline, Processed

log = logging.getLogger(__name__)
MAX_PARALLEL = 3  # одновременных распознаваний; остальные фото ждут в очереди

HELP = ("Пришлите фото заказ-наряда — распознаю и запишу в таблицу.\n"
        "Снимайте весь лист целиком, сверху, при хорошем свете. Можно несколько фото подряд.")


def parse_allowed(raw: str | None) -> set[int]:
    return {int(x) for x in (raw or "").replace(" ", "").split(",") if x}


def money(value: int) -> str:
    return f"{value:,}".replace(",", " ") + " ₽"


def format_reply(r: Processed) -> str:
    n = r.naryad
    title = f"Наряд №{n.number}" if n.number else "Наряд без номера"
    if r.action == "пропущен":
        return f"ℹ️ {title} уже проверен в таблице — не менял."

    lines = [f"⚠️ {title} — на проверку" if r.needs_review else f"✅ {title} — записан"]
    lines += [f"• {p}" for p in r.problems]
    summary = " · ".join(x for x in (n.clinic, n.doctor, n.patient and f"пациент {n.patient}") if x)
    if summary:
        lines.append(summary)
    tail = [money(n.total) if n.total is not None else None,
            f"сдача {n.due_date:%d.%m}" if n.due_date else None]
    if any(tail):
        lines.append(", ".join(x for x in tail if x))
    if not r.cropped:
        lines.append("Лист на фото не нашёлся — в следующий раз снимайте весь бланк на тёмном фоне.")
    return "\n".join(lines)


def build_router(pipeline: Pipeline, inbox: Path, allowed: set[int], sheet_url: str | None = None) -> Router:
    router = Router()
    slots = asyncio.Semaphore(MAX_PARALLEL)

    def denied(m: Message) -> bool:
        return m.from_user is None or m.from_user.id not in allowed

    @router.message(CommandStart())
    async def start(m: Message) -> None:
        if denied(m):
            await m.answer(f"Нет доступа. Передайте администратору ваш id: {m.from_user.id}")
            return
        await m.answer(HELP + (f"\n\nТаблица: {sheet_url}" if sheet_url else ""))

    @router.message(F.photo | F.document)
    async def on_photo(m: Message, bot: Bot) -> None:
        if denied(m):
            await m.answer(f"Нет доступа. Передайте администратору ваш id: {m.from_user.id}")
            return

        if m.photo:
            file, suffix = m.photo[-1], ".jpg"  # последний — самый крупный размер
        else:
            file, suffix = m.document, Path(m.document.file_name or "").suffix.lower()
            if suffix not in PHOTO_SUFFIXES:
                await m.reply("Это не фото. Пришлите JPG или PNG — или просто фото, не файлом.")
                return

        # file_unique_id одинаков у одного и того же файла: повторная пересылка → та же строка в таблице
        path = inbox / date.today().isoformat() / f"{file.file_unique_id}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        await bot.download(file, destination=path)
        status = await m.reply("Принял, распознаю…")
        log.info("фото %s от %s", path.name, m.from_user.id)

        try:
            async with slots:
                result = await asyncio.to_thread(pipeline.process, path)
        except Exception:
            log.exception("%s: не обработан", path)
            await status.edit_text("❌ Не получилось обработать фото. Оно сохранено, разберём вручную.")
            return
        log.info("%s → наряд %s %s; %s", path.name, result.naryad.number, result.action,
                 "; ".join(result.problems) or "ОК")
        await status.edit_text(format_reply(result))

    @router.message()
    async def other(m: Message) -> None:
        await m.answer(HELP)

    return router


async def run(token: str, router: Router) -> None:
    dp = Dispatcher()
    dp.include_router(router)
    bot = Bot(token)
    log.info("бот запущен: @%s", (await bot.get_me()).username)
    await dp.start_polling(bot)
