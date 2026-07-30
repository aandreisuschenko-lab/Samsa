#!/usr/bin/env python3
"""Построение мастер контент-плана из вводных менеджера.

Шаг 1 сценария из задания: менеджер загружает список моделей, промо и дат
старта — агент строит полный план и разносит кампании по каналам и назначениям.

Запуск:
    python3 build_plan.py data/plan-input.xlsx --run
    python3 build_plan.py --template          # создать пустой файл вводных

Флаг --run сразу прогоняет построенный план через основной пайплайн
(дедлайны, проверки, календарь, дайджест).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from contentplan.planbuilder import (
    assign_ids,
    build_campaigns,
    level_weeks,
    load_input,
    load_matrix,
    make_input_template,
    write_plan,
)

TEMPLATE = "data/samsung-digital-content-plan-template.xlsx"


def main() -> None:
    ap = argparse.ArgumentParser(description="Построение контент-плана из вводных")
    ap.add_argument("input", nargs="?", help="Excel с вводными (вкладка «Вводные»)")
    ap.add_argument("--template-out", default="data/plan-input-template.xlsx",
                    help="куда сохранить пустой шаблон вводных")
    ap.add_argument("--template", action="store_true", help="создать шаблон вводных и выйти")
    ap.add_argument("--rules", default=TEMPLATE, help="файл-шаблон с правилами и матрицей")
    ap.add_argument("--out", default="out/generated_plan.xlsx", help="куда сохранить план")
    ap.add_argument("--run", action="store_true", help="сразу прогнать пайплайн по плану")
    ap.add_argument("--out-dir", default="out", help="папка результатов пайплайна")
    ap.add_argument("--today", help="дата расчёта для пайплайна, YYYY-MM-DD")
    args = ap.parse_args()

    if args.template:
        path = make_input_template(args.rules, args.template_out)
        print(f"Шаблон вводных: {path}")
        return

    if not args.input:
        ap.error("укажите файл вводных или используйте --template")

    rows = load_input(args.input)
    matrix = load_matrix(args.rules)

    campaigns = build_campaigns(rows, matrix)
    notes = level_weeks(campaigns)
    assign_ids(campaigns)

    month = min(c.start for c in campaigns)
    title = f"Мастер контент-план Digital — {month:%m.%Y} (построен агентом)"
    plan_path = write_plan(campaigns, args.rules, args.out, title=title)

    print(f"Моделей на входе: {len(rows)} → кампаний построено: {len(campaigns)}")
    by_type: dict[str, int] = {}
    for c in campaigns:
        by_type[c.campaign_type] = by_type.get(c.campaign_type, 0) + 1
    print("По типам: " + ", ".join(f"{k} — {v}" for k, v in sorted(by_type.items())))

    weeks: dict[str, int] = {}
    for c in campaigns:
        weeks[c.week] = weeks.get(c.week, 0) + 1
    print("По неделям: " + " · ".join(f"{w}: {n}" for w, n in sorted(weeks.items())))

    if notes:
        print("\nВыравнивание недель (лимит 4 запуска):")
        for n in notes:
            print("  • " + n)

    dests = sorted({c.destination for c in campaigns})
    print(f"\nНазначения задействованы: {', '.join(dests)}")
    print(f"План: {plan_path}")

    if args.run:
        cmd = [sys.executable, "run.py", str(plan_path), "--out", args.out_dir]
        if args.today:
            cmd += ["--today", args.today]
        print("\n--- прогон пайплайна ---")
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
