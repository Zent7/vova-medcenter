// Статус «На работу / С работы»: большая кнопка, счетчик времени на работе, месячная сводка
// план-факт по дням и список отметок месяца. Отметки ведет сервер (/work-status), график берется из модуля графика.
//
// Файл грузится до app.js, рядом с work-schedule.js: месяц, экранирование и числа берутся оттуда
// (wsToday, wsShiftMonth, wsMonthTitle, wsPad, wsEscape, wsFormatHours). Из app.js берутся
// apiRequest, humanizeApiError, renderApp.
// app.js вызывает renderStatusContent (страница), bindWorkStatusEvents (после каждой перерисовки),
// loadWorkStatus (вход в раздел) и resetWorkStatus (выход из программы).
// Счетчик идет по часам сервера: старт отметки берется из ответа, «сейчас» — по поправке часов.

const WST_TIME_ZONE = "Europe/Moscow";

function wstInitialState() {
  const today = wsToday();
  return {
    year: today.year,
    month: today.month,
    data: null,
    loading: false,
    busy: false,
    error: "",
    requestId: 0,
    offsetMs: 0,
    timerId: null,
  };
}

const wstState = wstInitialState();

// Выход из программы: останавливаем счетчик и отбрасываем ответы, которые еще летят от прошлого сеанса.
function resetWorkStatus() {
  wstStopTimer();
  const requestId = wstState.requestId + 1;
  Object.assign(wstState, wstInitialState(), { requestId });
}

// «ЧЧ:ММ:СС» для счетчика; часы могут быть больше суток.
function wstFormatElapsed(totalSeconds) {
  const seconds = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${wsPad(hours)}:${wsPad(minutes)}:${wsPad(seconds % 60)}`;
}

// Время отметки для подписи: «09:05» по московскому времени, как в графике.
function wstFormatMark(iso) {
  const moment = new Date(iso);
  if (Number.isNaN(moment.getTime())) return "";
  return moment.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", timeZone: WST_TIME_ZONE });
}

// Отметка без «С работы» или длиннее 12 часов — красным: такие строки проверяют первыми.
const WST_LONG_MARK_SECONDS = 12 * 3600;

function wstMarkFlag(mark) {
  if (!mark?.ended_at) return "open";
  return Number(mark.duration_seconds) > WST_LONG_MARK_SECONDS ? "long" : "";
}

// Дата и время для списка отметок по московскому времени: «07-11-2026» и «17:19:02».
function wstStampParts(iso) {
  const moment = new Date(iso);
  if (Number.isNaN(moment.getTime())) return null;
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: WST_TIME_ZONE,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(moment);
  const part = (type) => parts.find((item) => item.type === type)?.value || "";
  return {
    date: `${part("day")}-${part("month")}-${part("year")}`,
    time: `${part("hour")}:${part("minute")}:${part("second")}`,
  };
}

// «07-11-2026 17:19:02» одной строкой.
function wstFormatStamp(iso) {
  const stamp = wstStampParts(iso);
  return stamp ? `${stamp.date} ${stamp.time}` : "";
}

// Для таблицы: дата не рвется при переносе строки, время уходит на следующую строку на узком экране.
function wstStampHtml(iso) {
  const stamp = wstStampParts(iso);
  return stamp ? `<span class="wst-marks__date">${stamp.date}</span> ${stamp.time}` : "";
}

function renderWstMarkRow(mark, options) {
  const flag = wstMarkFlag(mark);
  const rowClass = flag ? `wst-marks__row wst-marks__row--${flag}` : "wst-marks__row";
  const hint =
    flag === "open" ? "Нет отметки «С работы»" : flag === "long" ? "Дольше 12 часов: проверьте, не забыли ли отметить уход" : "";
  const end = mark.ended_at ? wstStampHtml(mark.ended_at) : "на работе";
  const elapsed = wstFormatElapsed(mark.duration_seconds);
  const duration = flag === "open" && options.live ? `<span data-wst-mark-elapsed>${elapsed}</span>` : elapsed;
  return (
    `<tr class="${rowClass}"${hint ? ` title="${wsEscape(hint)}"` : ""}>` +
    `<td>${wstStampHtml(mark.started_at)}</td><td>${end}</td><td>${duration}</td></tr>`
  );
}

// Блок «Отметки»: заголовок, пояснение и таблица «Начало — Конец — Длительность», новые сверху.
// live — открытая отметка тикает вместе со счетчиком статуса; в статистике админа она стоит на времени ответа.
function renderWstMarksBlock(title, marks, options = {}) {
  const list = Array.isArray(marks) ? marks : [];
  const body = list.length
    ? `<div class="ws__scroll wst-marks">
        <table class="ws__summary wst-marks__table">
          <thead><tr><th>Начало</th><th>Конец</th><th>Длит.</th></tr></thead>
          <tbody>${list.map((mark) => renderWstMarkRow(mark, options)).join("")}</tbody>
        </table>
      </div>`
    : `<div class="empty">За этот месяц отметок нет.</div>`;
  return `
    <div class="wst-marks-block">
      <h4>${wsEscape(title)}</h4>
      <p class="muted wst-marks-block__note">Красным — отметка без «С работы» или длиннее 12 часов.</p>
      ${body}
    </div>`;
}

// Столбики месяца: серым — по графику; оранжевым — факт в пределах плана; зеленым поверх — переработка;
// на всю высоту — дни отпуска. Геометрия без DOM, чтобы ее можно было проверить.
function buildWstChart(days, options = {}) {
  const width = options.width || 720;
  const height = options.height || 240;
  const pad = { left: 36, right: 10, top: 12, bottom: 24 };
  const list = Array.isArray(days) ? days : [];
  const peak = list.reduce(
    (max, day) => Math.max(max, Number(day.plan_hours) || 0, Number(day.fact_hours) || 0),
    0,
  );
  const yMax = Math.max(12, Math.ceil(peak / 4) * 4);
  const innerWidth = width - pad.left - pad.right;
  const innerHeight = height - pad.top - pad.bottom;
  const slot = list.length ? innerWidth / list.length : innerWidth;
  const barWidth = Math.max(2, Math.min(11, slot * 0.36));
  const yOf = (hours) => pad.top + innerHeight - (hours / yMax) * innerHeight;
  const heightOf = (hours) => (hours / yMax) * innerHeight;
  const bars = list.map((day, index) => {
    const left = pad.left + slot * index;
    const center = left + slot / 2;
    const plan = Number(day.plan_hours) || 0;
    const fact = Number(day.fact_hours) || 0;
    const inPlan = Math.min(fact, plan);
    const overtime = Math.max(fact - plan, 0);
    return {
      day: index + 1,
      date: day.work_date,
      vacation: day.kind === "vacation" ? { x: left, y: pad.top, width: slot, height: innerHeight } : null,
      labelX: center,
      plan: { x: center - barWidth - 1, y: yOf(plan), width: barWidth, height: heightOf(plan), hours: plan },
      inPlan: { x: center + 1, y: yOf(inPlan), width: barWidth, height: heightOf(inPlan), hours: inPlan },
      overtime: { x: center + 1, y: yOf(fact), width: barWidth, height: heightOf(overtime), hours: overtime },
      fact,
    };
  });
  const ticks = [];
  for (let value = 0; value <= yMax; value += 2) {
    ticks.push({ value, y: yOf(value) });
  }
  return { width, height, pad, yMax, bars, ticks };
}

function renderWstChartSvg(chart) {
  const { width, height, pad, ticks, bars } = chart;
  const grid = ticks
    .map(
      (tick) =>
        `<line class="ws-chart__grid" x1="${pad.left}" x2="${width - pad.right}" y1="${tick.y.toFixed(1)}" y2="${tick.y.toFixed(1)}"></line>` +
        `<text class="ws-chart__tick" x="${pad.left - 6}" y="${(tick.y + 3).toFixed(1)}" text-anchor="end">${tick.value}</text>`,
    )
    .join("");
  const vacations = bars
    .filter((bar) => bar.vacation)
    .map(
      (bar) =>
        `<rect class="wst-chart__vacation" x="${bar.vacation.x.toFixed(1)}" y="${bar.vacation.y.toFixed(1)}" width="${bar.vacation.width.toFixed(1)}" height="${bar.vacation.height.toFixed(1)}">` +
        `<title>${bar.day}: отпуск</title></rect>`,
    )
    .join("");
  const columns = bars
    .map(
      (bar) =>
        `<rect class="wst-chart__plan" x="${bar.plan.x.toFixed(1)}" y="${bar.plan.y.toFixed(1)}" width="${bar.plan.width.toFixed(1)}" height="${bar.plan.height.toFixed(1)}">` +
        `<title>${bar.day}: по графику ${wsFormatHours(bar.plan.hours)} ч</title></rect>` +
        `<rect class="wst-chart__fact" x="${bar.inPlan.x.toFixed(1)}" y="${bar.inPlan.y.toFixed(1)}" width="${bar.inPlan.width.toFixed(1)}" height="${bar.inPlan.height.toFixed(1)}">` +
        `<title>${bar.day}: по факту ${wsFormatHours(bar.fact)} ч</title></rect>` +
        (bar.overtime.hours > 0
          ? `<rect class="wst-chart__over" x="${bar.overtime.x.toFixed(1)}" y="${bar.overtime.y.toFixed(1)}" width="${bar.overtime.width.toFixed(1)}" height="${bar.overtime.height.toFixed(1)}">` +
            `<title>${bar.day}: переработка ${wsFormatHours(bar.overtime.hours)} ч</title></rect>`
          : "") +
        `<text class="ws-chart__day" x="${bar.labelX.toFixed(1)}" y="${height - 8}" text-anchor="middle">${bar.day}</text>`,
    )
    .join("");
  return `<svg class="ws-chart wst-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Часы по дням: серым по графику, оранжевым по факту, зеленым переработка">${grid}${vacations}${columns}</svg>`;
}

// Сколько секунд сотрудник на работе сейчас: старт — из ответа сервера, «сейчас» — по его часам.
function wstElapsedSeconds() {
  const open = wstState.data?.open;
  if (!open) return 0;
  const started = Date.parse(open.started_at);
  if (Number.isNaN(started)) return Number(open.elapsed_seconds) || 0;
  return (Date.now() + wstState.offsetMs - started) / 1000;
}

function wstApply(payload) {
  wstState.data = payload;
  const serverNow = Date.parse(payload.now);
  wstState.offsetMs = Number.isNaN(serverNow) ? 0 : serverNow - Date.now();
}

function wstStopTimer() {
  if (wstState.timerId !== null) {
    window.clearInterval(wstState.timerId);
    wstState.timerId = null;
  }
}

// Перерисовываем только цифры счетчика: страница целиком не нужна каждую секунду.
function wstTick() {
  const element = document.querySelector("[data-wst-elapsed]");
  if (!element || !wstState.data?.open) {
    wstStopTimer();
    return;
  }
  const text = wstFormatElapsed(wstElapsedSeconds());
  element.textContent = text;
  // Открытая строка в списке отметок показывает то же время, что и большой счетчик.
  document.querySelectorAll("[data-wst-mark-elapsed]").forEach((node) => {
    node.textContent = text;
  });
}

function wstStartTimer() {
  wstStopTimer();
  if (!wstState.data?.open) return;
  wstState.timerId = window.setInterval(wstTick, 1000);
}

function renderStatusContent() {
  const payload = wstState.data;
  const open = payload?.open || null;
  const totals = payload?.totals || { plan_hours: 0, fact_hours: 0, overtime_hours: 0 };
  const chart = payload ? buildWstChart(payload.days) : null;
  return `
    <section class="card wst" data-work-status>
      <div class="wst__head">
        <div>
          <h3>Статус</h3>
          <p class="muted">Нажмите «На работу», когда пришли, и «С работы», когда уходите. Время считается само.</p>
        </div>
      </div>
      <div class="wst__now">
        <button
          class="wst__toggle${open ? " is-on" : ""}"
          type="button"
          data-wst-toggle
          aria-pressed="${open ? "true" : "false"}"
          ${wstState.busy || !payload ? "disabled" : ""}
        >
          <span class="wst__toggle-label">${open ? "С работы" : "На работу"}</span>
          ${open ? `<span class="wst__toggle-time" data-wst-elapsed>${wstFormatElapsed(wstElapsedSeconds())}</span>` : ""}
        </button>
        <div class="wst__hint">
          ${open ? `Вы на работе с ${wsEscape(wstFormatMark(open.started_at))} (по Москве).` : "Сейчас отметки о работе нет."}
          ${wstState.error ? `<div class="note employee-note employee-note--error">${wsEscape(wstState.error)}</div>` : ""}
        </div>
      </div>
      ${
        payload
          ? `
            <div class="wst__month">
              <button class="ghost-button" type="button" data-wst-month="-1" aria-label="Предыдущий месяц">◀</button>
              <strong>${wsEscape(wsMonthTitle(wstState.year, wstState.month))}</strong>
              <button class="ghost-button" type="button" data-wst-month="1" aria-label="Следующий месяц">▶</button>
            </div>
            <div class="wst__totals">
              <span>По графику: <strong>${wsFormatHours(totals.plan_hours)} ч</strong></span>
              <span>Факт: <strong>${wsFormatHours(totals.fact_hours)} ч</strong></span>
              <span>Переработка: <strong>${wsFormatHours(totals.overtime_hours)} ч</strong></span>
            </div>
            <div class="ws__scroll wst__chart">${renderWstChartSvg(chart)}</div>
            <div class="wst__legend">
              <span class="wst__key wst__key--plan">По графику</span>
              <span class="wst__key wst__key--fact">Факт в пределах плана</span>
              <span class="wst__key wst__key--over">Переработка</span>
              <span class="wst__key wst__key--vacation">Отпуск</span>
            </div>
            ${renderWstMarksBlock("Отметки за месяц", payload.marks, { live: true })}`
          : `<div class="empty">${wstState.loading ? "Загружаем статус..." : "Статус пока не загружен."}</div>`
      }
    </section>`;
}

// Загрузка и действия. Каждый запрос получает номер: отвечает только последний.

async function loadWorkStatus() {
  const requestId = ++wstState.requestId;
  wstState.loading = true;
  wstState.error = "";
  renderApp();
  try {
    const payload = await apiRequest(`/work-status/me?year=${wstState.year}&month=${wstState.month}`);
    if (requestId !== wstState.requestId) return;
    wstApply(payload);
  } catch (error) {
    if (requestId !== wstState.requestId) return;
    wstState.error = humanizeApiError(error, "Не удалось загрузить статус");
  } finally {
    if (requestId === wstState.requestId) {
      wstState.loading = false;
      renderApp();
    }
  }
}

// Кнопка: открыта отметка — «С работы», иначе — «На работу». После ответа перечитываем месяц,
// который открыт на экране, потому что сервер отдает текущий месяц.
async function wstToggle() {
  if (wstState.busy || !wstState.data) return;
  const leaving = Boolean(wstState.data.open);
  wstState.busy = true;
  wstState.error = "";
  renderApp();
  try {
    await apiRequest(leaving ? "/work-status/stop" : "/work-status/start", { method: "POST" });
  } catch (error) {
    wstState.busy = false;
    wstState.error = humanizeApiError(error, leaving ? "Не удалось отметить уход" : "Не удалось отметить приход");
    renderApp();
    return;
  }
  wstState.busy = false;
  await loadWorkStatus();
}

function wstChangeMonth(delta) {
  const next = wsShiftMonth(wstState.year, wstState.month, delta);
  wstState.year = next.year;
  wstState.month = next.month;
  wstState.data = null;
  loadWorkStatus();
}

function bindWorkStatusEvents() {
  const root = document.querySelector("[data-work-status]");
  if (!root) {
    wstStopTimer();
    return;
  }
  root.querySelector("[data-wst-toggle]")?.addEventListener("click", wstToggle);
  root.querySelectorAll("[data-wst-month]").forEach((button) => {
    button.addEventListener("click", () => wstChangeMonth(Number(button.dataset.wstMonth) || 0));
  });
  wstStartTimer();
}
