"""Отчёт проверок и недельный дайджест (детерминированные шаблоны).

Работает без обращения к LLM. Claude Code поверх этих же данных может
переписать дайджест «человеческим» языком — см. prompts/digest.md.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from .checks import P1, P2, P3, Issue
from .deadlines import STAGE_LABELS, deadline_diff
from .loader import PlanData

PRIORITY_LABEL = {
    P1: "P1 · блокер",
    P2: "P2 · риск",
    P3: "P3 · дыра в покрытии",
}


def _fmt(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "—"


def _short(d: date | None) -> str:
    return d.strftime("%d.%m") if d else "—"


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        word = one
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = few
    else:
        word = many
    return f"{n} {word}"


def build_checks_report(plan: PlanData, issues: list[Issue], today: date) -> str:
    lines = [
        f"# Отчёт проверок — {plan.title}",
        "",
        f"Дата расчёта: **{_fmt(today)}** · кампаний в плане: **{len(plan.campaigns)}** · "
        f"найдено проблем: **{len(issues)}**",
        "",
        "## Сводка по приоритетам",
        "",
        "| Приоритет | Кол-во | Что это значит |",
        "|---|---|---|",
    ]
    meaning = {
        P1: "запуск под угрозой срыва, нужна реакция сегодня",
        P2: "риск не успеть или потерять эффективность",
        P3: "недоработка плана: дыры в покрытии, дисбаланс",
    }
    for p in (P1, P2, P3):
        n = sum(1 for i in issues if i.priority == p)
        lines.append(f"| {PRIORITY_LABEL[p]} | {n} | {meaning[p]} |")

    for p in (P1, P2, P3):
        block = [i for i in issues if i.priority == p]
        if not block:
            continue
        lines += ["", f"## {PRIORITY_LABEL[p]}", ""]
        for i in block:
            lines.append(f"### {i.title}")
            lines.append(f"- {i.detail}")
            if i.action:
                lines.append(f"- **Что делать:** {i.action}")
            lines.append("")

    lines += ["", "## Пересчёт дедлайнов: было / стало", ""]
    lines.append(
        "В исходном файле дедлайны посчитаны единым правилом −14 / −7 / −3 для всех "
        "кампаний. Ниже — расчёт по правилам вкладки «2. Правила дедлайнов» "
        "с переносом выходных на предыдущий рабочий день."
    )
    lines += [
        "",
        "| ID | Тип кампании | Старт | Бриф было → стало | Креатив было → стало | Согл. было → стало |",
        "|---|---|---|---|---|---|",
    ]
    for c in plan.campaigns:
        diffs = {d["stage"]: d for d in deadline_diff(c)}
        cells = []
        for stage in ("brief", "creative", "approval"):
            if stage in diffs:
                d = diffs[stage]
                cells.append(f"**{_short(d['was'])} → {_short(d['now'])}** ({d['delta_days']:+d})")
            else:
                cells.append(f"{_short(c.corrected.get(stage))} =")
        lines.append(
            f"| {c.id} | {c.campaign_type} | {_short(c.start)} | " + " | ".join(cells) + " |"
        )
    lines += [
        "",
        "`=` означает, что исходный дедлайн совпал с корректным. "
        "Жирным выделены расхождения, которые агент исправил.",
        "",
    ]
    return "\n".join(lines)


def build_weekly_digest(plan: PlanData, issues: list[Issue], today: date) -> str:
    horizon = today + timedelta(days=7)
    burning = [i for i in issues if i.priority == P1]
    gaps = [i for i in issues if i.priority == P3]

    tasks = []
    for c in plan.campaigns:
        if c.is_done:
            continue
        for stage, d in sorted(c.corrected.items(), key=lambda x: x[1]):
            if stage == "upload":
                continue
            if d < today:
                tasks.append((d, c, stage, "просрочено"))
            elif d <= horizon:
                tasks.append((d, c, stage, "на этой неделе"))
    tasks.sort(key=lambda x: x[0])

    week_no = today.isocalendar().week
    lines = [
        f"# Недельный дайджест · W{week_no} ({_fmt(today)})",
        "",
        f"**{_plural(len(burning), 'блокер', 'блокера', 'блокеров')} · "
        f"{_plural(len(tasks), 'задача', 'задачи', 'задач')} на неделю · "
        f"{_plural(len(gaps), 'дыра', 'дыры', 'дыр')} в плане**",
        "",
        "## 🔴 Что горит",
        "",
    ]
    if burning:
        for i in burning[:8]:
            lines.append(f"- **{i.title}** — {i.action or i.detail}")
        if len(burning) > 8:
            lines.append(f"- …и ещё {len(burning) - 8} — полный список в отчёте проверок")
    else:
        lines.append("- Блокеров нет, план идёт по графику.")

    lines += ["", "## 📋 Что сделать на этой неделе", ""]
    if tasks:
        lines += ["| Дедлайн | Кампания | Этап | Модель | Статус |", "|---|---|---|---|---|"]
        for d, c, stage, mark in tasks[:15]:
            flag = "⚠️ " if mark == "просрочено" else ""
            lines.append(
                f"| {flag}{_short(d)} | {c.id} | {STAGE_LABELS[stage]} | {c.model} | {c.status} |"
            )
        if len(tasks) > 15:
            lines.append(f"| … | ещё {len(tasks) - 15} задач | | | |")
    else:
        lines.append("Дедлайнов в ближайшие 7 дней нет.")

    lines += ["", "## 🕳 Где дыры", ""]
    if gaps:
        for i in gaps:
            lines.append(f"- **{i.title}** — {i.action or i.detail}")
    else:
        lines.append("- Покрытие моделей, каналов и дистрибьюторов закрыто.")

    # загрузка по неделям
    by_week: dict[str, int] = defaultdict(int)
    for c in plan.campaigns:
        by_week[c.week or c.start.strftime("W%V")] += 1
    load = " · ".join(
        f"{w}: {n}{'⚠️' if n > plan.thresholds.max_launches_per_week else ''}"
        for w, n in sorted(by_week.items())
    )
    lines += ["", "## 📊 Загрузка по неделям", "", load, ""]
    return "\n".join(lines)
