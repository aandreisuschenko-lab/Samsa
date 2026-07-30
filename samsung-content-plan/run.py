#!/usr/bin/env python3
"""AI Content Plan Agent — пересчёт дедлайнов, проверки, календарь, дайджест.

Запуск:
    python3 run.py data/samsung-digital-content-plan-template.xlsx
    python3 run.py <plan.xlsx> --today 2026-07-01 --models data/samsung-creative-brief-template.xlsx
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from contentplan.calendar_html import build_calendar
from contentplan.checks import run_checks
from contentplan.deadlines import apply_deadlines
from contentplan.excel_out import write_corrected_plan
from contentplan.loader import load_plan, load_priority_models
from contentplan.report import build_checks_report, build_weekly_digest
from contentplan.report_docx import DOCX_AVAILABLE, build_checks_docx, build_digest_docx


def main() -> None:
    ap = argparse.ArgumentParser(description="Ведение мастер контент-плана Digital")
    ap.add_argument("plan", help="Excel с мастер контент-планом")
    ap.add_argument("--models", help="Excel креативного брифа (Задание №1) — источник приоритетных моделей")
    ap.add_argument("--today", help="Дата расчёта YYYY-MM-DD (по умолчанию — сегодня)")
    ap.add_argument("--out", default="out", help="Папка результатов")
    args = ap.parse_args()

    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    plan = apply_deadlines(load_plan(args.plan))
    priority_models = load_priority_models(args.models) if args.models else []
    issues = run_checks(plan, today, priority_models)

    xlsx = write_corrected_plan(plan, issues, today, out / "content_plan_corrected.xlsx")

    if DOCX_AVAILABLE:
        checks_path = build_checks_docx(plan, issues, today, out / "checks_report.docx")
        digest_path = build_digest_docx(plan, issues, today, out / "weekly_digest.docx")
    else:
        checks_path = out / "checks_report.md"
        checks_path.write_text(build_checks_report(plan, issues, today), encoding="utf-8")
        digest_path = out / "weekly_digest.md"
        digest_path.write_text(build_weekly_digest(plan, issues, today), encoding="utf-8")
        print("Word недоступен — отчёты сохранены в markdown. "
              "Установите: pip3 install python-docx")
    html = build_calendar(plan, issues, today, out / "calendar.html")
    (out / "plan.json").write_text(
        json.dumps(
            {
                "today": today.isoformat(),
                "campaigns": [
                    {
                        "id": c.id, "model": c.model, "type": c.campaign_type,
                        "owner": c.owner, "budget": c.budget, "week": c.week, "format": c.fmt,
                        "channel": c.channel, "destination": c.destination,
                        "creative_id": c.creative_id, "status": c.status,
                        "start": c.start.isoformat(),
                        "deadlines": {k: v.isoformat() for k, v in c.corrected.items()},
                        "original": {k: v.isoformat() for k, v in c.original.items() if v},
                    }
                    for c in plan.campaigns
                ],
                "issues": [i.as_dict() for i in issues],
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    p1 = sum(1 for i in issues if i.priority == "P1")
    p2 = sum(1 for i in issues if i.priority == "P2")
    p3 = sum(1 for i in issues if i.priority == "P3")
    print(f"Дата расчёта: {today:%d.%m.%Y} · кампаний: {len(plan.campaigns)}")
    print(f"Проблем найдено: {len(issues)}  (P1 блокеры: {p1}, P2 риски: {p2}, P3 дыры: {p3})")
    print(f"Результаты: {xlsx}, {checks_path}, {digest_path}, {html}")


if __name__ == "__main__":
    main()
