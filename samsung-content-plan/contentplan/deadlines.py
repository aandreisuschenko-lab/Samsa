"""Расчёт дедлайнов обратным отсчётом по типам кампаний."""
from __future__ import annotations

from datetime import date, timedelta

from .loader import Campaign, PlanData

STAGES = ("brief", "creative", "approval", "upload")
STAGE_LABELS = {
    "brief": "Бриф",
    "creative": "Креатив",
    "approval": "Согласование",
    "upload": "Загрузка",
}


def prev_business_day(d: date) -> date:
    """Если дата выпала на выходной — сдвигаем на предыдущий рабочий день."""
    while d.weekday() >= 5:  # 5 = суббота, 6 = воскресенье
        d -= timedelta(days=1)
    return d


def is_distributor_campaign(c: Campaign, plan: PlanData) -> bool:
    return c.destination in plan.distributors


def compute_deadlines(c: Campaign, plan: PlanData) -> dict[str, date]:
    """Дедлайны по правилам своего типа кампании.

    Допущение (задокументировано в README): правило «дистрибьюторские кампании
    требуют +1 день на согласование» уже зашито в тип Retail support (−4 против
    −3 у промо). Для кампаний ДРУГИХ типов, ведущих на дистрибьютора, мы
    добавляем этот день сами — иначе правило со вкладки «Правила» не работает.
    """
    rule = plan.rule_for(c)
    offsets = {
        "brief": rule.brief,
        "creative": rule.creative,
        "approval": rule.approval,
        "upload": rule.upload,
    }
    if is_distributor_campaign(c, plan) and c.campaign_type.strip() != "Retail support":
        offsets["approval"] += 1

    return {
        stage: prev_business_day(c.start - timedelta(days=days))
        for stage, days in offsets.items()
    }


def apply_deadlines(plan: PlanData) -> PlanData:
    for c in plan.campaigns:
        c.corrected = compute_deadlines(c, plan)
    return plan


def deadline_diff(c: Campaign) -> list[dict]:
    """Расхождения между исходным файлом и корректным расчётом."""
    out = []
    for stage in ("brief", "creative", "approval"):
        was = c.original.get(stage)
        now = c.corrected.get(stage)
        if was is None or now is None or was == now:
            continue
        out.append(
            {
                "stage": stage,
                "label": STAGE_LABELS[stage],
                "was": was,
                "now": now,
                "delta_days": (now - was).days,
            }
        )
    return out


def required_lead_time(c: Campaign, plan: PlanData) -> int:
    return plan.rule_for(c).lead_time
