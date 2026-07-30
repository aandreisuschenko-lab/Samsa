"""Интерактивный календарь-Гант (self-contained HTML, без внешних зависимостей).

Сценарий «что если» считается прямо в браузере: правила дедлайнов встроены
в страницу, поэтому сдвиг даты старта мгновенно пересчитывает этапы и
пересобирает список конфликтов — без повторного запуска пайплайна.
"""
from __future__ import annotations

import json
from datetime import date
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
    --paper:#FBFBFD; --ink:#0B1020; --muted:#5B6478; --line:#E8EAF2; --line-week:#B9C0D4;
    --blue:#1428A0; --blue-soft:#E8EBFA; --weekend:#F1F3F9;
    --red:#C3271A; --amber:#B26B00; --green:#147A4B; --violet:#6B3FA0;
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
    padding:14px 32px; border-bottom:1px solid var(--line); background:#fff; position:sticky; top:0; z-index:6;
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
  main { padding:26px 32px 60px; overflow-x:auto; }
  .grid { display:grid; grid-template-columns:250px 1fr; min-width:1150px; }

  .scale-label { border-bottom:2px solid var(--line-week); }
  .scale { position:relative; height:48px; border-bottom:2px solid var(--line-week); }
  .wk {
    position:absolute; top:3px; font-size:10px; color:var(--blue); font-weight:600;
    letter-spacing:.03em; white-space:nowrap; padding-left:4px; height:16px;
    border-left:2px solid var(--line-week);
  }
  .day {
    position:absolute; top:24px; font-size:9px; color:var(--muted);
    text-align:center; font-family:ui-monospace,monospace;
  }
  .day.we { color:#AAB0C2; }
  .day.now { color:var(--red); font-weight:700; }

  .label { padding:11px 12px 11px 0; border-bottom:1px solid var(--line); border-right:2px solid var(--line-week); }
  .label .id { font-size:11px; color:var(--muted); letter-spacing:.05em; }
  .label .name { font-weight:600; font-size:13px; }
  .label .meta { font-size:11px; color:var(--muted); }
  .track { position:relative; border-bottom:1px solid var(--line); background-repeat:repeat-x; }
  .runway { position:absolute; top:23px; height:6px; background:var(--runway); border-radius:3px; }
  .flight { position:absolute; top:20px; height:12px; background:var(--blue-soft); border:1px solid var(--blue);
            border-radius:3px; }
  .flight.media { background:#F1E9FA; border-color:var(--violet); }
  .pin { position:absolute; top:14px; width:22px; height:22px; margin-left:-11px; border-radius:50%;
         background:#fff; border:1.5px solid var(--blue); color:var(--blue);
         font-size:10px; font-weight:700; display:flex; align-items:center; justify-content:center;
         cursor:default; z-index:2; }
  .pin.late { border-color:var(--red); color:#fff; background:var(--red); }
  .pin.soon { border-color:var(--amber); color:var(--amber); background:#FDF7EC; }
  .start { position:absolute; top:11px; width:0; height:30px; border-left:2px solid var(--blue); z-index:2; }
  .start::after { content:attr(data-label); position:absolute; left:5px; top:-1px; font-size:10px; color:var(--blue);
                  white-space:nowrap; font-family:ui-monospace,monospace; }
  .today { position:absolute; top:0; bottom:0; width:0; border-left:2px dashed var(--red); z-index:4; }
  .today span { position:absolute; top:-19px; left:4px; font-size:10px; color:var(--red); white-space:nowrap;
                font-family:ui-monospace,monospace; }
  .status { display:inline-block; font-size:10px; padding:1px 7px; border-radius:999px; border:1px solid var(--line); }
  .st-done { color:var(--green); border-color:#BFE3D0; background:#F1FAF5; }
  .st-wip { color:var(--amber); border-color:#F0DCB8; background:#FDF7EC; }
  .st-todo { color:var(--muted); }

  .legend { margin-top:32px; border:1px solid var(--line); border-radius:10px; padding:20px 24px; background:#fff; }
  .legend h3 { margin:0 0 16px; font-size:12px; text-transform:uppercase; letter-spacing:.1em; color:var(--muted); }
  .legend-cols { display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:22px 34px; }
  .legend h4 { margin:0 0 10px; font-size:11px; text-transform:uppercase; letter-spacing:.07em; color:var(--ink); }
  .legend-item { display:flex; align-items:center; gap:10px; margin-bottom:8px; font-size:12px; color:var(--muted); }
  .legend-item b { color:var(--ink); font-weight:600; }
  .swatch { flex:0 0 36px; display:flex; align-items:center; justify-content:center; }
  .sw-pin { width:22px; height:22px; border-radius:50%; background:#fff; border:1.5px solid var(--blue);
            color:var(--blue); font-size:10px; font-weight:700; display:flex; align-items:center;
            justify-content:center; }
  .sw-pin.late { border-color:var(--red); background:var(--red); color:#fff; }
  .sw-pin.soon { border-color:var(--amber); color:var(--amber); background:#FDF7EC; }
  .sw-bar { width:32px; height:6px; border-radius:3px; background:var(--runway); }
  .sw-flight { width:32px; height:12px; border-radius:3px; background:var(--blue-soft); border:1px solid var(--blue); }
  .sw-flight.media { background:#F1E9FA; border-color:var(--violet); }
  .sw-line { width:0; height:20px; border-left:2px dashed var(--red); }
  .sw-line.solid { border-left:2px solid var(--blue); }
  .sw-band { width:30px; height:18px; background:var(--weekend); border:1px solid var(--line); }
  .sw-grid { width:30px; height:18px; border:1px solid var(--line);
             background:linear-gradient(to right, var(--line) 0 1px, transparent 1px 100%);
             background-size:7px 100%; }

  .issues { margin-top:36px; }
  .issue { border-left:3px solid var(--line); padding:8px 0 8px 14px; margin-bottom:12px; }
  .issue.P1 { border-color:var(--red); } .issue.P2 { border-color:var(--amber); } .issue.P3 { border-color:var(--muted); }
  .issue .t { font-weight:600; font-size:13px; }
  .issue .d { color:var(--muted); font-size:12px; }
  .issue .a { font-size:12px; margin-top:3px; }
  h2 { font-size:13px; text-transform:uppercase; letter-spacing:.1em; color:var(--muted); margin:0 0 14px; }
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
    <h3>Как читать календарь</h3>
    <div class="legend-cols">
      <div>
        <h4>Этапы подготовки</h4>
        <div class="legend-item"><span class="swatch"><span class="sw-pin">Б</span></span>
          <span><b>Бриф</b> — дедлайн постановки задачи в студию</span></div>
        <div class="legend-item"><span class="swatch"><span class="sw-pin">К</span></span>
          <span><b>Креатив</b> — дедлайн готовности макетов</span></div>
        <div class="legend-item"><span class="swatch"><span class="sw-pin">С</span></span>
          <span><b>Согласование</b> — дедлайн финального аппрува</span></div>
      </div>
      <div>
        <h4>Цвет этапа</h4>
        <div class="legend-item"><span class="swatch"><span class="sw-pin late">Б</span></span>
          <span><b>Красный</b> — дедлайн прошёл, статус не «Готово»</span></div>
        <div class="legend-item"><span class="swatch"><span class="sw-pin soon">К</span></span>
          <span><b>Оранжевый</b> — дедлайн в ближайшие 7 дней</span></div>
        <div class="legend-item"><span class="swatch"><span class="sw-pin">С</span></span>
          <span><b>Синий</b> — срок ещё не подошёл</span></div>
      </div>
      <div>
        <h4>Полосы и линии</h4>
        <div class="legend-item"><span class="swatch"><span class="sw-bar"></span></span>
          <span><b>Серая полоса</b> — окно продакшена: от брифа до старта</span></div>
        <div class="legend-item"><span class="swatch"><span class="sw-flight"></span></span>
          <span><b>Синий блок</b> — флайт кампании: от старта до финиша</span></div>
        <div class="legend-item"><span class="swatch"><span class="sw-flight media"></span></span>
          <span><b>Фиолетовый блок</b> — медийная кампания</span></div>
        <div class="legend-item"><span class="swatch"><span class="sw-line solid"></span></span>
          <span><b>Синяя черта</b> — дата старта кампании</span></div>
        <div class="legend-item"><span class="swatch"><span class="sw-line"></span></span>
          <span><b>Красный пунктир</b> — сегодняшний день</span></div>
      </div>
      <div>
        <h4>Сетка и статусы</h4>
        <div class="legend-item"><span class="swatch"><span class="sw-grid"></span></span>
          <span><b>Вертикальные линии</b> — границы суток, жирная — начало недели</span></div>
        <div class="legend-item"><span class="swatch"><span class="sw-band"></span></span>
          <span><b>Серая заливка</b> — суббота и воскресенье</span></div>
        <div class="legend-item"><span class="swatch"><span class="status st-done">Готово</span></span>
          <span>креатив готов, проверки кампанию не трогают</span></div>
        <div class="legend-item"><span class="swatch"><span class="status st-wip">В работе</span></span>
          <span>в производстве</span></div>
        <div class="legend-item"><span class="swatch"><span class="status st-todo">Не начато</span></span>
          <span>работа ещё не стартовала</span></div>
      </div>
    </div>
  </div>

  <div class="issues">
    <h2>Отчёт проверок</h2>
    <div id="issues"></div>
  </div>
</main>

<script>
const DATA = __DATA__;
const DAY = 86400000;
const MONTHS = ["янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"];
const parse = s => new Date(s + "T00:00:00");
const fmt = d => String(d.getDate()).padStart(2,"0") + "." + String(d.getMonth()+1).padStart(2,"0");
const today = parse(DATA.today);

function prevBusiness(d){ const x = new Date(d); while (x.getDay()===0 || x.getDay()===6) x.setTime(x.getTime()-DAY); return x; }
function isoWeek(d){
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - day);
  const start = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  return Math.ceil((((t - start) / DAY) + 1) / 7);
}

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
  // начало выравниваем на понедельник, чтобы полосы выходных совпали с неделями
  const from = new Date(min - 2*DAY);
  while (from.getDay() !== 1) from.setTime(from.getTime() - DAY);
  const to = new Date(max + 3*DAY);
  while (to.getDay() !== 1) to.setTime(to.getTime() + DAY);
  return [from, to];
}

function render(){
  const [from, to] = bounds();
  const span = Math.round((to - from) / DAY);
  const dayW = 100 / span;
  const pct = d => ((d - from) / DAY) / span * 100;
  const grid = document.getElementById("grid");
  grid.innerHTML = "";

  // фон: полоса выходных с периодом в неделю + линия на каждую границу суток
  const bgImage =
    "linear-gradient(to right, transparent 0 71.4286%, var(--weekend) 71.4286% 100%)," +
    "linear-gradient(to right, var(--line) 0 1px, transparent 1px 100%)";
  const bgSize = `${dayW*7}% 100%, ${dayW}% 100%`;
  const bg = `background-image:${bgImage};background-size:${bgSize}`;

  grid.insertAdjacentHTML("beforeend", '<div class="label scale-label"></div>');
  let scale = `<div class="scale" style="${bg}">`;
  for (let i = 0; i < span; i++){
    const d = new Date(from.getTime() + i*DAY);
    const we = (d.getDay() === 0 || d.getDay() === 6);
    const now = d.toDateString() === today.toDateString();
    if (d.getDay() === 1){
      scale += `<div class="wk" style="left:${pct(d)}%">W${isoWeek(d)} · ${d.getDate()} ${MONTHS[d.getMonth()]}</div>`;
    }
    scale += `<div class="day ${we?"we":""} ${now?"now":""}" style="left:${pct(d)}%;width:${dayW}%">${d.getDate()}</div>`;
  }
  scale += `<div class="today" style="left:${pct(today)}%"><span>сегодня ${fmt(today)}</span></div></div>`;
  grid.insertAdjacentHTML("beforeend", scale);

  let doneCount = 0, budget = 0;

  DATA.campaigns.forEach(c => {
    const sh = shifts[c.id] || 0;
    const d = deadlines(c, sh);
    const done = c.status === "Готово";
    if (done) doneCount++;
    budget += c.budget;

    const daysLeft = Math.round((d.start - today)/DAY);
    const late = !done && d.brief < today;
    const infeasible = !done && daysLeft >= 0 && daysLeft < d.leadTime;

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
      <div class="track ${show?"":"hidden"}" style="height:50px;${bg}">
        <div class="runway" style="left:${pct(d.brief)}%;width:${Math.max(pct(d.start)-pct(d.brief),0.3)}%"></div>
        <div class="flight ${c.media?"media":""}" style="left:${pct(d.start)}%;width:${Math.max(pct(flightEnd)-pct(d.start),0.5)}%"></div>
        ${pin(d.brief,"Б","Бриф")}${pin(d.creative,"К","Креатив")}${pin(d.approval,"С","Согласование")}
        <div class="start" style="left:${pct(d.start)}%" data-label="старт ${fmt(d.start)}"></div>
        <div class="today" style="left:${pct(today)}%"></div>
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
