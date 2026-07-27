"""Движок проверок контент-плана.

Каждая проверка — отдельная функция, возвращающая список Issue.
Источник требований: вкладка «4. Трекинг» + доп. правила вкладок 2 и 3.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from .deadlines import (
    STAGE_LABELS,
    deadline_diff,
    is_distributor_campaign,
    required_lead_time,
)
from .loader import PlanData

P1, P2, P3 = "P1", "P2", "P3"  # блокер / риск / дыра в покрытии

PERFORMANCE_TYPES = {"Промо-запуск", "Always-on", "Маркетплейс"}
MEDIA_TYPES = {"Медийка"}


@dataclass
class Issue:
    code: str
    priority: str
    title: str
    detail: str
    campaign_ids: list[str] = field(default_factory=list)
    action: str = ""

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "priority": self.priority,
            "title": self.title,
            "detail": self.detail,
            "campaigns": self.campaign_ids,
            "action": self.action,
        }


def _fmt(d: date | None) -> str:
    return d.strftime("%d.%m") if d else "—"


# --- 1. Расхождения с исходным файлом ---------------------------------------

def check_rule_mismatch(plan: PlanData, today: date) -> list[Issue]:
    issues = []
    for c in plan.campaigns:
        diffs = deadline_diff(c)
        if not diffs:
            continue
        moved_earlier = [d for d in diffs if d["delta_days"] < 0]
        parts = [
            f"{d['label']}: было {_fmt(d['was'])} → стало {_fmt(d['now'])} ({d['delta_days']:+d} дн.)"
            for d in diffs
        ]
        # приоритет выше, если корректный дедлайн уже в прошлом, а работа не готова
        overdue_now = any(
            d["now"] < today for d in moved_earlier
        ) and not c.is_done
        issues.append(
            Issue(
                code="RULE_MISMATCH",
                priority=P1 if overdue_now else P2,
                title=f"{c.id} · дедлайны посчитаны не по правилам типа «{c.campaign_type}»",
                detail="; ".join(parts),
                campaign_ids=[c.id],
                action=(
                    "Пересчитанный дедлайн уже прошёл — переносить старт или ускорять продакшен"
                    if overdue_now
                    else "Обновить дедлайны в мастер-плане"
                ),
            )
        )
    return issues


# --- 2. Просроченные дедлайны -----------------------------------------------

def check_overdue(plan: PlanData, today: date) -> list[Issue]:
    issues = []
    for c in plan.campaigns:
        if c.is_done:
            continue
        overdue = [
            (stage, d) for stage, d in c.corrected.items() if d < today and stage != "upload"
        ]
        if not overdue:
            continue
        worst = min(overdue, key=lambda x: x[1])
        days = (today - worst[1]).days
        issues.append(
            Issue(
                code="OVERDUE",
                priority=P1,
                title=f"{c.id} · просрочен дедлайн «{STAGE_LABELS[worst[0]]}» на {days} дн.",
                detail=(
                    f"{c.model} · {c.channel} → {c.destination} · старт {_fmt(c.start)} · "
                    f"статус «{c.status}» · просрочено этапов: {len(overdue)}"
                ),
                campaign_ids=[c.id],
                action="Эскалация: подтвердить готовность или сдвинуть старт",
            )
        )
    return issues


# --- 3. Физически не успеть к старту ----------------------------------------

def check_infeasible(plan: PlanData, today: date) -> list[Issue]:
    issues = []
    for c in plan.campaigns:
        if c.is_done or c.start < today:
            continue
        days_left = (c.start - today).days
        need = required_lead_time(c, plan)
        if days_left < need:
            issues.append(
                Issue(
                    code="INFEASIBLE",
                    priority=P1,
                    title=f"{c.id} · не успеть к старту: осталось {days_left} дн., нужно {need}",
                    detail=(
                        f"{c.model} · тип «{c.campaign_type}» · старт {_fmt(c.start)} · "
                        f"статус «{c.status}»"
                    ),
                    campaign_ids=[c.id],
                    action=f"Сдвинуть старт минимум на {need - days_left} дн. или сократить объём креативов",
                )
            )
    return issues


# --- 4. Кампании без креатива при близком старте ----------------------------

def check_no_creative(plan: PlanData, today: date) -> list[Issue]:
    limit = plan.thresholds.creative_ready_days
    issues = []
    for c in plan.campaigns:
        if c.is_done:
            continue
        days_left = (c.start - today).days
        if 0 <= days_left < limit:
            issues.append(
                Issue(
                    code="NO_CREATIVE",
                    priority=P1,
                    title=f"{c.id} · старт через {days_left} дн., креатив {c.creative_id} не готов",
                    detail=f"{c.model} · {c.fmt} · статус «{c.status}» · блокирует запуск",
                    campaign_ids=[c.id],
                    action=f"Забрать {c.creative_id} из студии в приоритете",
                )
            )
    return issues


# --- 5. Перегруз недели ------------------------------------------------------

def check_week_overload(plan: PlanData, today: date) -> list[Issue]:
    limit = plan.thresholds.max_launches_per_week
    by_week: dict[str, list] = defaultdict(list)
    for c in plan.campaigns:
        key = c.week or c.start.strftime("W%V")
        by_week[key].append(c)

    issues = []
    for week, items in sorted(by_week.items()):
        if len(items) > limit:
            issues.append(
                Issue(
                    code="WEEK_OVERLOAD",
                    priority=P2,
                    title=f"{week} · перегруз: {len(items)} запусков при лимите {limit}",
                    detail="Кампании: " + ", ".join(c.id for c in items),
                    campaign_ids=[c.id for c in items],
                    action="Перенести часть запусков на соседнюю неделю или заказать креатив раньше",
                )
            )
    return issues


# --- 6. Перегруз по дедлайнам на неделе -------------------------------------

def check_deadline_crunch(plan: PlanData, today: date) -> list[Issue]:
    limit = plan.thresholds.max_deadlines_per_week
    horizon = today + timedelta(days=7)
    hits = [
        (c, stage, d)
        for c in plan.campaigns
        if not c.is_done
        for stage, d in c.corrected.items()
        if today <= d <= horizon
    ]
    if len(hits) > limit:
        return [
            Issue(
                code="DEADLINE_CRUNCH",
                priority=P2,
                title=f"На ближайшие 7 дней приходится {len(hits)} дедлайнов при пороге {limit}",
                detail="; ".join(
                    f"{c.id} {STAGE_LABELS[stage]} {_fmt(d)}" for c, stage, d in sorted(hits, key=lambda x: x[2])
                ),
                campaign_ids=sorted({c.id for c, _, _ in hits}),
                action="Проверить загрузку студии, часть задач вынести за пределы недели",
            )
        ]
    return []


# --- 7. Покрытие моделей ----------------------------------------------------

def check_model_coverage(plan: PlanData, today: date, priority_models: list[str]) -> list[Issue]:
    planned = {c.model for c in plan.campaigns}
    missing = [m for m in priority_models if m not in planned]
    if not missing:
        return []
    return [
        Issue(
            code="MODEL_GAP",
            priority=P2,
            title=f"Приоритетные модели без кампаний в месяце: {len(missing)}",
            detail=", ".join(missing) + " — есть в креативном брифе (Задание №1), но нет в плане",
            action="Поставить в план хотя бы 1 перформанс-кампанию на модель",
        )
    ]


# --- 8. Покрытие дистрибьюторов и каналов -----------------------------------

def check_destination_coverage(plan: PlanData, today: date) -> list[Issue]:
    used = {c.destination for c in plan.campaigns}
    missing = sorted(plan.distributors - used)
    issues = []
    if missing:
        issues.append(
            Issue(
                code="DISTRIBUTOR_GAP",
                priority=P3,
                title=f"Дистрибьюторы без поддержки в месяце: {', '.join(missing)}",
                detail="По матрице «Каналы и назначения» на них можно вести трафик, но плана нет",
                action="Заложить Retail support или снять дистрибьютора с матрицы",
            )
        )

    channels_used = {c.channel for c in plan.campaigns}
    matrix_channels = {row.channel for row in plan.matrix}
    unknown = sorted(
        ch for ch in channels_used
        if not any(ch.lower().startswith(m.split()[0].lower()) for m in matrix_channels)
    )
    if unknown:
        issues.append(
            Issue(
                code="CHANNEL_UNKNOWN",
                priority=P3,
                title=f"Каналы вне матрицы: {', '.join(unknown)}",
                detail="Для них не определены допустимые форматы креативов",
                action="Добавить канал в матрицу или переименовать по справочнику",
            )
        )
    return issues


# --- 9. Медийка без перформанс-поддержки ------------------------------------

def check_media_support(plan: PlanData, today: date) -> list[Issue]:
    by_model: dict[str, list] = defaultdict(list)
    for c in plan.campaigns:
        by_model[c.model].append(c)

    issues = []
    for model, items in by_model.items():
        media = [c for c in items if c.campaign_type in MEDIA_TYPES]
        perf = [c for c in items if c.campaign_type in PERFORMANCE_TYPES]
        if media and not perf:
            issues.append(
                Issue(
                    code="MEDIA_NO_PERF",
                    priority=P2,
                    title=f"{model} · медийка без перформанс-поддержки",
                    detail=(
                        "Медийные кампании: "
                        + ", ".join(f"{c.id} ({c.channel}, {c.budget:,.0f} ₸)".replace(",", " ") for c in media)
                        + ". По правилу вкладки «Каналы» охват не сконвертируется."
                    ),
                    campaign_ids=[c.id for c in media],
                    action="Добавить Google Search / PMax на эту модель или снять медийку",
                )
            )
    return issues


# --- 10. Баланс бюджета -----------------------------------------------------

def check_budget_balance(plan: PlanData, today: date) -> list[Issue]:
    total = sum(c.budget for c in plan.campaigns)
    if not total:
        return []
    media = sum(c.budget for c in plan.campaigns if c.campaign_type in MEDIA_TYPES)
    share = media / total
    if share > plan.thresholds.media_budget_share:
        return [
            Issue(
                code="BUDGET_BALANCE",
                priority=P3,
                title=f"Доля медийки {share:.0%} при пороге {plan.thresholds.media_budget_share:.0%}",
                detail=f"Медийка {media:,.0f} ₸ из {total:,.0f} ₸".replace(",", " "),
                action="Проверить, что весь охват поддержан перформансом",
            )
        ]
    return []


# --- 11. Точка продаж по модели ---------------------------------------------

def check_sales_point(plan: PlanData, today: date) -> list[Issue]:
    """Правило вкладки 3: модель = 1 перформанс-канал + 1 точка продаж."""
    by_model: dict[str, list] = defaultdict(list)
    for c in plan.campaigns:
        by_model[c.model].append(c)

    sales_points = plan.marketplaces | plan.distributors
    issues = []
    for model, items in by_model.items():
        has_perf = any(c.campaign_type in PERFORMANCE_TYPES for c in items)
        has_sales = any(c.destination in sales_points for c in items)
        if has_perf and not has_sales:
            issues.append(
                Issue(
                    code="NO_SALES_POINT",
                    priority=P3,
                    title=f"{model} · нет точки продаж (маркетплейс или дистрибьютор)",
                    detail="Весь трафик ведём только на samsung.kz",
                    campaign_ids=[c.id for c in items],
                    action="Добавить Kaspi/Ozon или Retail support",
                )
            )
    return issues


ALL_CHECKS = [
    check_rule_mismatch,
    check_overdue,
    check_infeasible,
    check_no_creative,
    check_week_overload,
    check_deadline_crunch,
    check_destination_coverage,
    check_media_support,
    check_budget_balance,
    check_sales_point,
]


def run_checks(plan: PlanData, today: date, priority_models: list[str] | None = None) -> list[Issue]:
    issues: list[Issue] = []
    for check in ALL_CHECKS:
        issues.extend(check(plan, today))
    if priority_models:
        issues.extend(check_model_coverage(plan, today, priority_models))

    # Просрочка и «не успеть к старту» — одна и та же проблема с разных сторон.
    # Оставляем более информативную INFEASIBLE, чтобы не раздувать дайджест.
    infeasible = {cid for i in issues if i.code == "INFEASIBLE" for cid in i.campaign_ids}
    issues = [
        i for i in issues
        if not (i.code == "OVERDUE" and set(i.campaign_ids) <= infeasible)
    ]

    order = {P1: 0, P2: 1, P3: 2}
    return sorted(issues, key=lambda i: (order[i.priority], i.code, i.title))
