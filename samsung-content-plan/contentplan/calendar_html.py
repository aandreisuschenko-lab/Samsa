"""Интерактивный календарь-Гант (self-contained HTML, без внешних зависимостей).

Сценарий «что если» считается прямо в браузере: правила дедлайнов встроены
в страницу, поэтому сдвиг даты старта мгновенно пересчитывает этапы и
пересобирает список конфликтов — без повторного запуска пайплайна.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .checks import Issue
from .deadlines import is_distributor_campaign
from .loader import PlanData

TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {
    --paper:#FBFBFD; --ink:#0B1020; --muted:#5B6478; --line:#E2E5EE;
    --blue:#1428A0; --blue-soft:#E8EBFA;
    --red:#C3271A; --amber:#B26B00; --green:#147A4B;
    --runway:#C9D0E8;
  }
  * { box-sizing:border-box; }
  body {
    margin:0; background:var(--paper); color:var(--ink);
    font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
  }
  .mono { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-variant-numeric:tabular-nums; }
  header { padding:28px 32px 20px; border-bottom:1px solid var(--line); }
  h1 { margin:0 0 6px; font-size:22px; letter-spacing:-.01em; }
  .sub { color:var(--muted); font-size:13px; }
  .counters { display:flex; gap:28px; margin-top:18px; flex-wrap:wrap; }
  .counter b { display:block; font-size:26px; line-height:1.1; font-family:ui-monospace,monospace; }
  .counter span { font-size:11px; text-transform:uppercase; letter-spacing:.09em; color:var(--muted); }
  .c-red b { color:var(--red); } .c-amber b { color:var(--amber); } .c-green b { color:var(--green); }
  .toolbar {
    display:flex; gap:10px; align-items:center; flex-wrap:wrap;
    padding:14px 32px; border-bottom:1px solid var(--line); background:#fff; position:sticky; top:0; z-index:5;
  }
  .chip {
    border:1px solid var(--line); background:#fff; border-radius:999px; padding:5px 13px;
    font-size:12px; cursor:pointer; color:var(--muted);
  }
  .chip[aria-pressed="true"] { background:var(--blue); border-color:var(--blue); color:#fff; }
  .spacer { flex:1; }
  .whatif { display:flex; align-items:center; gap:10px; font-size:12px; color:var(--muted); }
  .whatif select, .whatif input[type=range] { accent-color:var(--blue); }
  .whatif b { color:var(--ink); font-family:ui-monospace,monospace; }
  main { padding:22px 32px 60px; overflow-x:auto; }
  .grid { display:grid; grid-template-columns:260px 1fr; column-gap:14px; min-width:1000px; }
  .scale { position:relative; height:34px; border-bottom:1px solid var(--line); }
  .tick { position:absolute; top:0; font-size:10px; color:var(--muted); }
  .tick i { display:block; width:1px; height:8px; background:var(--line); margin-top:2px; }
  .weekband { position:absolute; top:0; bottom:0; background:#F4F6FB; }
  .row { display:contents; }
  .label { padding:9px 0; border-bottom:1px solid var(--line); }
  .label .id { font-size:11px; color:var(--muted); letter-spacing:.05em; }
  .label .name { font-weight:600; font-size:13px; }
  .label .meta { font-size:11px; color:var(--muted); }
  .track { position:relative; height:auto; border-bottom:1px solid var(--line); }
  .runway { position:absolute; top:20px; height:6px; background:var(--runway); border-radius:3px; }
  .flight { position:absolute; top:17px; height:12px; background:var(--blue-soft); border:1px solid var(--blue);
            border-radius:3px; }
  .flight.media { background:#F1E9FA; border-color:#6B3FA0; }
  .pin { position:absolute; top:11px; width:22px; height:22px; margin-left:-11px; border-radius:50%;
         background:#fff; border:1.5px solid var(--blue); color:var(--blue);
         font-size:10px; font-weight:700; display:flex; align-items:center; justify-content:center; cursor:default; }
  .pin.late { border-color:var(--red); color:#fff; background:var(--red); }
  .pin.soon { border-color:var(--amber); color:var(--amber); }
  .start { position:absolute; top:8px; width:0; height:28px; border-left:2px solid var(--blue); }
  .start::after { content:attr(data-label); position:absolute; left:5px; top:-2px; font-size:10px; color:var(--blue);
                  white-space:nowrap; font-family:ui-monospace,monospace; }
  .today { position:absolute; top:0; bottom:0; width:0; border-left:2px dashed var(--red); z-index:3; }
  .today span { position:absolute; top:-16px; left:4px; font-size:10px; color:var(--red); white-space:nowrap; }
  .status { display:inline-block; font-size:10px; padding:1px 7px; border-radius:999px; border:1px solid var(--line); }
  .st-done { color:var(--green); border-color:#BFE3D0; background:#F1FAF5; }
  .st-wip { color:var(--amber); border-color:#F0DCB8; background:#FDF7EC; }
  .st-todo { color:var(--muted); }
  .issues { margin-top:38px; }
  .issue { border-left:3px solid var(--line); padding:8px 0 8px 14px; margin-bottom:12px; }
  .issue.P1 { border-color:var(--red); } .issue.P2 { border-color:var(--amber); } .issue.P3 { border-color:var(--muted); }
  .issue .t { font-weight:600; font-size:13px; }
  .issue .d { color:var(--muted); font-size:12px; }
  .issue .a { font-size:12px; margin-top:3px; }
  h2 { font-size:13px; text-transform:uppercase; letter-spacing:.1em; color:var(--muted); margin:0 0 14px; }
  .legend { margin-top:26px; font-size:11px; color:var(--muted); display:flex; gap:18px; flex-wrap:wrap; }
  .hidden { display:none !important; }
  @media (prefers-reduced-motion:no-preference) { .pin, .flight, .runway { transition:left .18s, width .18s; } }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <div class="sub mono">Расчёт на __TODAY__ · дедлайны по правилам типа кампании · выходные перенесены на предыдущий рабочий день</div>
  <div class="counters">
    <div class="counter c-red"><b id="cnt-p1">0</b><span>блокеров</span></div>
    <div class="counter c-amber"><b id="cnt-p2">0</b><span>рисков</span></div>
    <div class="counter c-green"><b id="cnt-done">0</b><span>готово из __TOTAL__</span></div>
    <div class="counter"><b id="cnt-budget" class="mono">0</b><span>бюджет, ₸</span></div>
  </div>
</header>

<div class="toolbar">
  <button class="chip" data-filter="all" aria-pressed="true">Все</button>
  <button class="chip" data-filter="risk" aria-pressed="false">Только с проблемами</button>
  <button class="chip" data-filter="perf" aria-pressed="false">Перформанс</button>
  <button class="chip" data-filter="media" aria-pressed="false">Медийка</button>
  <div class="spacer"></div>
  <div class="whatif">
    <span>Что если сдвинуть старт:</span>
    <select id="wi-campaign"></select>
    <input type="range" id="wi-shift" min="-14" max="21" value="0" step="1">
    <b id="wi-value">0 дн.</b>
    <button class="chip" id="wi-reset">Сбросить</button>
  </div>
</div>

<main>
  <div class="grid" id="grid"></div>
  <div class="legend">
    <span>▬ серая линия — окно продакшена (от брифа до старта)</span>
    <span>▮ синий — флайт кампании · фиолетовый — медийка</span>
    <span>Б / К / С — бриф, креатив, согласование</span>
    <span style="color:var(--red)">красный пин — дедлайн прошёл при незакрытом статусе</span>
  </div>
  <div class="issues">
    <h2>Отчёт проверок</h2>
    <div id="issues"></div>
  </div>
</main>

<script>
const DATA = __DATA__;
const DAY = 86400000;
const parse = s => new Date(s + "T00:00:00");
const fmt = d => String(d.getDate()).padStart(2,"0") + "." + String(d.getMonth()+1).padStart(2,"0");
const iso = d => d.toISOString().slice(0,10);
const today = parse(DATA.today);

function prevBusiness(d){ const x = new Date(d); while (x.getDay()===0 || x.getDay()===6) x.setTime(x.getTime()-DAY); return x; }

function deadlines(c, shift){
  const rule = DATA.rules[c.type] || DATA.fallbackRule;
  const start = new Date(parse(c.start).getTime() + shift*DAY);
  const extra = (c.distributor && c.type !== "Retail support") ? 1 : 0;
  return {
    start,
    finish: c.finish ? new Date(parse(c.finish).getTime() + shift*DAY) : null,
    brief: prevBusiness(new Date(start.getTime() - rule.brief*DAY)),
    creative: prevBusiness(new Date(start.getTime() - rule.creative*DAY)),
    approval: prevBusiness(new Date(start.getTime() - (rule.approval+extra)*DAY)),
    leadTime: Math.max(rule.brief, rule.creative, rule.approval, rule.upload)
  };
}

const shifts = {};
const state = { filter:"all" };

function bounds(){
  let min = today.getTime(), max = today.getTime();
  DATA.campaigns.forEach(c => {
    const d = deadlines(c, shifts[c.id]||0);
    min = Math.min(min, d.brief.getTime());
    max = Math.max(max, (d.finish||d.start).getTime());
  });
  return [new Date(min - 2*DAY), new Date(max + 2*DAY)];
}

function render(){
  const [from, to] = bounds();
  const span = (to - from) / DAY;
  const pct = d => ((d - from) / DAY) / span * 100;
  const grid = document.getElementById("grid");
  grid.innerHTML = "";

  // шкала
  grid.insertAdjacentHTML("beforeend", '<div class="label"></div>');
  let scale = '<div class="scale">';
  for (let i = 0; i <= span; i++){
    const d = new Date(from.getTime() + i*DAY);
    if (d.getDay() === 1){
      scale += `<div class="weekband" style="left:${pct(d)}%;width:${(5/span)*100}%"></div>`;
      scale += `<div class="tick mono" style="left:${pct(d)}%">${fmt(d)}<i></i></div>`;
    }
  }
  scale += `<div class="today" style="left:${pct(today)}%"><span class="mono">сегодня ${fmt(today)}</span></div></div>`;
  grid.insertAdjacentHTML("beforeend", scale);

  let doneCount = 0, budget = 0, risky = 0;

  DATA.campaigns.forEach(c => {
    const sh = shifts[c.id] || 0;
    const d = deadlines(c, sh);
    const done = c.status === "Готово";
    if (done) doneCount++;
    budget += c.budget;

    const daysLeft = Math.round((d.start - today)/DAY);
    const late = !done && d.brief < today;
    const infeasible = !done && daysLeft >= 0 && daysLeft < d.leadTime;
    if (late || infeasible) risky++;

    const show =
      state.filter === "all" ||
      (state.filter === "risk" && (late || infeasible)) ||
      (state.filter === "media" && c.media) ||
      (state.filter === "perf" && !c.media);

    const stCls = done ? "st-done" : (c.status === "В работе" ? "st-wip" : "st-todo");
    grid.insertAdjacentHTML("beforeend", `
      <div class="label ${show?"":"hidden"}">
        <div class="id mono">${c.id} · ${c.type}${sh?` <b style="color:var(--blue)">${sh>0?"+":""}${sh}д</b>`:""}</div>
        <div class="name">${c.model}</div>
        <div class="meta">${c.channel} → ${c.destination} · <span class="status ${stCls}">${c.status}</span></div>
      </div>`);

    const pin = (date, letter, title) => {
      const cls = (!done && date < today) ? "late" : ((date - today)/DAY <= 7 && date >= today ? "soon" : "");
      return `<div class="pin ${cls}" style="left:${pct(date)}%" title="${title}: ${fmt(date)}">${letter}</div>`;
    };
    const flightEnd = d.finish || d.start;
    grid.insertAdjacentHTML("beforeend", `
      <div class="track ${show?"":"hidden"}" style="height:44px">
        <div class="runway" style="left:${pct(d.brief)}%;width:${Math.max(pct(d.start)-pct(d.brief),0.3)}%"></div>
        <div class="flight ${c.media?"media":""}" style="left:${pct(d.start)}%;width:${Math.max(pct(flightEnd)-pct(d.start),0.5)}%"></div>
        ${pin(d.brief,"Б","Бриф")}${pin(d.creative,"К","Креатив")}${pin(d.approval,"С","Согласование")}
        <div class="start" style="left:${pct(d.start)}%" data-label="старт ${fmt(d.start)}"></div>
      </div>`);
  });

  document.getElementById("cnt-p1").textContent = DATA.counters.p1;
  document.getElementById("cnt-p2").textContent = DATA.counters.p2;
  document.getElementById("cnt-done").textContent = doneCount;
  document.getElementById("cnt-budget").textContent = budget.toLocaleString("ru-RU");
}

function renderIssues(){
  document.getElementById("issues").innerHTML = DATA.issues.map(i => `
    <div class="issue ${i.priority}">
      <div class="t">${i.priority} · ${i.title}</div>
      <div class="d">${i.detail}</div>
      ${i.action?`<div class="a">→ ${i.action}</div>`:""}
    </div>`).join("");
}

// what-if
const sel = document.getElementById("wi-campaign");
sel.innerHTML = DATA.campaigns.map(c => `<option value="${c.id}">${c.id} · ${c.model}</option>`).join("");
const range = document.getElementById("wi-shift");
range.addEventListener("input", () => {
  shifts[sel.value] = +range.value;
  document.getElementById("wi-value").textContent = (range.value > 0 ? "+" : "") + range.value + " дн.";
  render();
});
sel.addEventListener("change", () => {
  range.value = shifts[sel.value] || 0;
  document.getElementById("wi-value").textContent = (range.value > 0 ? "+" : "") + range.value + " дн.";
});
document.getElementById("wi-reset").addEventListener("click", () => {
  Object.keys(shifts).forEach(k => delete shifts[k]);
  range.value = 0; document.getElementById("wi-value").textContent = "0 дн."; render();
});
document.querySelectorAll("[data-filter]").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("[data-filter]").forEach(b => b.setAttribute("aria-pressed","false"));
    btn.setAttribute("aria-pressed","true");
    state.filter = btn.dataset.filter;
    render();
  });
});

render(); renderIssues();
</script>
</body>
</html>
"""


def build_calendar(plan: PlanData, issues: list[Issue], today: date, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    media_types = {"Медийка"}
    payload = {
        "today": today.isoformat(),
        "rules": {
            name: {"brief": r.brief, "creative": r.creative, "approval": r.approval, "upload": r.upload}
            for name, r in plan.rules.items()
        },
        "fallbackRule": {"brief": 21, "creative": 10, "approval": 5, "upload": 2},
        "campaigns": [
            {
                "id": c.id,
                "model": c.model,
                "type": c.campaign_type,
                "channel": c.channel,
                "destination": c.destination,
                "creative": c.creative_id,
                "format": c.fmt,
                "start": c.start.isoformat(),
                "finish": c.finish.isoformat() if c.finish else None,
                "status": c.status,
                "budget": c.budget,
                "media": c.campaign_type in media_types,
                "distributor": is_distributor_campaign(c, plan),
            }
            for c in plan.campaigns
        ],
        "issues": [i.as_dict() for i in issues],
        "counters": {
            "p1": sum(1 for i in issues if i.priority == "P1"),
            "p2": sum(1 for i in issues if i.priority == "P2"),
            "p3": sum(1 for i in issues if i.priority == "P3"),
        },
    }

    html = (
        TEMPLATE.replace("__TITLE__", plan.title)
        .replace("__TODAY__", today.strftime("%d.%m.%Y"))
        .replace("__TOTAL__", str(len(plan.campaigns)))
        .replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    )
    out_path.write_text(html, encoding="utf-8")
    return out_path
