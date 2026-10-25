"""Командная строка.

    naryad eval                          # прогон на эталонах (ANTHROPIC_API_KEY в .env)
    naryad eval --model claude-sonnet-5-5 --fresh
    naryad crop                          # сохранить обрезанные фото в results/crops — проверить глазами
    naryad process фото.jpg ...          # распознать и записать в Google Таблицу (GOOGLE_* в .env)
    naryad bot                           # Telegram-бот (TELEGRAM_* в .env)
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from naryad.clients import load_clients
from naryad.compare import GRADED
from naryad.evaluation import Report, evaluate, find_photos
from naryad.extractors import DEFAULT_MODEL, ApiExtractor, Extractor
from naryad.image import prepare
from naryad.pipeline import Pipeline
from naryad.prompt import build_system_prompt
from naryad.sheets import open_sheets


def print_report(report: Report) -> None:
    for item in report.items:
        status = "НА ПРОВЕРКУ" if item.needs_review else ("ОК, НО С ОШИБКОЙ" if item.silent_error else "ОК")
        crop = "" if item.cropped else "  (лист не найден, кадр целиком)"
        print(f"\n=== {item.name}: {status}{crop}")
        for p in item.problems:
            print(f"    ! {p}")
        if item.truth is None:
            print("    (нет эталона — только проверки)")
            continue
        for f, ok in item.fields.items():
            if not ok:
                print(f"    ✗ {f}: модель {getattr(item.naryad, f)!r}, эталон {getattr(item.truth, f)!r}")

    n = len(report.graded)
    if n:
        print(f"\n=== Точность по полям ({n} нарядов с эталоном)")
        for f in GRADED:
            print(f"    {f:<13} {report.per_field[f]}/{n}")
    print(f"\n    Точность       {report.accuracy:.0%}")
    reviewed = sum(i.needs_review for i in report.items)
    print(f"    На проверку    {reviewed}/{len(report.items)} ({report.review_rate:.0%})")
    print(f"    Тихие ошибки   {report.silent_errors}")
    print("    Стоимость      " + ("неизвестно" if report.cost is None else f"${report.cost:.3f}"))


def make_extractor(args: argparse.Namespace, clients) -> Extractor:
    return ApiExtractor(system=build_system_prompt(clients), model=args.model)


def cmd_eval(args: argparse.Namespace) -> None:
    clients = load_clients(args.data / "clients.json")
    extractor = make_extractor(args, clients)
    print(f"Модель: {args.model}, обрезка: {'да' if args.crop else 'нет'}")
    report = evaluate(extractor, clients, args.data / "photos",
                      args.data / "truth", args.results, crop=args.crop, fresh=args.fresh)
    print_report(report)


def cmd_crop(args: argparse.Namespace) -> None:
    out = args.results / "crops"
    out.mkdir(parents=True, exist_ok=True)
    for photo in find_photos(args.data / "photos"):
        prepared = prepare(photo)
        (out / f"{photo.stem}.jpg").write_bytes(prepared.jpeg)
        print(f"{photo.name}: {'лист найден' if prepared.cropped else 'ЛИСТ НЕ НАЙДЕН'}")
    print(f"→ {out}")


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"нужна переменная {name} в .env (пример — .env.example)")
    return value


def make_pipeline(args: argparse.Namespace) -> Pipeline:
    clients = load_clients(args.data / "clients.json")
    naryady, raboty = open_sheets(env("GOOGLE_CREDENTIALS_FILE"), env("GOOGLE_SHEET_ID"))
    return Pipeline(make_extractor(args, clients), clients, naryady, raboty)


def cmd_process(args: argparse.Namespace) -> None:
    pipeline = make_pipeline(args)
    failed = 0
    for photo in args.photos:
        try:
            r = pipeline.process(photo)
        except Exception:  # одно битое фото не должно останавливать пачку
            logging.exception("%s: не обработан", photo.name)
            failed += 1
            continue
        status = "НА ПРОВЕРКУ: " + "; ".join(r.problems) if r.problems else "ОК"
        print(f"{photo.name}: наряд {r.naryad.number or '?'} {r.action} — {status}")
    if failed:
        sys.exit(f"не обработано фото: {failed}")


def cmd_bot(args: argparse.Namespace) -> None:
    from naryad.bot import build_router, parse_allowed, run  # aiogram нужен только боту

    allowed = parse_allowed(os.environ.get("TELEGRAM_ALLOWED_IDS"))
    if not allowed:
        logging.warning("TELEGRAM_ALLOWED_IDS пуст — бот всем ответит «нет доступа» и покажет их id")
    sheet_url = f"https://docs.google.com/spreadsheets/d/{env('GOOGLE_SHEET_ID')}"
    router = build_router(make_pipeline(args), args.data / "inbox", allowed, sheet_url)
    asyncio.run(run(env("TELEGRAM_BOT_TOKEN"), router))


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):  # кириллица в консоли Windows без PYTHONIOENCODING
        stream.reconfigure(encoding="utf-8")
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(prog="naryad", description="Распознавание заказ-нарядов по фото")
    parser.add_argument("--data", type=Path, default=Path("data"), help="photos/, truth/, clients.json")
    parser.add_argument("--results", type=Path, default=Path("results"), help="кэш ответов и отладка")
    sub = parser.add_subparsers(dest="command", required=True)

    model = argparse.ArgumentParser(add_help=False)
    model.add_argument("--model", default=DEFAULT_MODEL)

    ev = sub.add_parser("eval", parents=[model], help="прогнать фото и сравнить с эталоном")
    ev.add_argument("--fresh", action="store_true", help="игнорировать кэш, распознать заново")
    ev.add_argument("--no-crop", dest="crop", action="store_false", help="не обрезать по листу")
    ev.set_defaults(func=cmd_eval)

    cr = sub.add_parser("crop", help="сохранить обрезанные фото для проверки глазами")
    cr.set_defaults(func=cmd_crop)

    pr = sub.add_parser("process", parents=[model], help="распознать фото и записать в Google Таблицу")
    pr.add_argument("photos", nargs="+", type=Path)
    pr.set_defaults(func=cmd_process)

    bt = sub.add_parser("bot", parents=[model], help="Telegram-бот: фото → таблица")
    bt.set_defaults(func=cmd_bot)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
