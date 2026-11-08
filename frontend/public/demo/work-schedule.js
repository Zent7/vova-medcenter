// График работы: таблица месяца одного медцентра (вкладки медцентров), правка дней, статистика план-факт и печать.
//
// Файл грузится до app.js. Из app.js берутся глобально: apiRequest, humanizeApiError,
// showToast, renderApp, openActionModal, closeActionModal, actionModalContent, appState,
// canViewWorkSchedule.
// app.js вызывает renderWorkScheduleContent (страница), bindWorkScheduleEvents (после
// каждой перерисовки), loadWorkSchedule (вход в раздел) и resetWorkSchedule (выход).
// Таблицу видят админ, врач и оператор; правят график, ставки и суммы — только админ. Врач и оператор
// смотрят статистику только по своим часам, без ставки и сумм.
// Каждый запрос называет медцентр (center_id): сотрудник с двумя медцентрами стоит в таблице каждого.

const WS_WEEKDAYS = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];
const WS_MONTH_NAMES = [
  "январь", "февраль", "март", "апрель", "май", "июнь",
  "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
];
const WS_KIND_CODES = { dayoff: "Отг", sick: "Бол", vacation: "Отп" };
const WS_KIND_LABELS = { shift: "Смена", dayoff: "Отгул", sick: "Больничный", vacation: "Отпуск" };
const WS_MAX_ABSENCE_DAYS = 366;

function wsEscape(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function wsPad(value) {
  return String(value).padStart(2, "0");
}

function wsToday() {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1, day: now.getDate() };
}

function wsDateKey(year, month, day) {
  return `${year}-${wsPad(month)}-${wsPad(day)}`;
}

// 0 — воскресенье, как в Date.getUTCDay().
function wsWeekday(year, month, day) {
  return new Date(Date.UTC(year, month - 1, day)).getUTCDay();
}

function wsIsWeekend(year, month, day) {
  const weekday = wsWeekday(year, month, day);
  return weekday === 0 || weekday === 6;
}

function wsShiftMonth(year, month, delta) {
  const shifted = new Date(Date.UTC(year, month - 1 + delta, 1));
  return { year: shifted.getUTCFullYear(), month: shifted.getUTCMonth() + 1 };
}

function wsMonthTitle(year, month) {
  return `${WS_MONTH_NAMES[month - 1]} ${year}`;
}

// «Создать график» заполняет месяц, который открыт, если он позже текущего; иначе — следующий.
function wsResolveCreateTarget(today, displayed) {
  const current = today.year * 12 + today.month;
  const shown = displayed.year * 12 + displayed.month;
  if (shown > current) return { year: displayed.year, month: displayed.month };
  return wsShiftMonth(today.year, today.month, 1);
}

function wsTime(value) {
  return String(value || "").slice(0, 5);
}

function wsFormatHours(value) {
  const number = Number(value) || 0;
  return number.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
}

function wsFormatMoney(value) {
  if (value === null || value === undefined) return "—";
  return `${Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ₽`;
}

function wsRowMeta(row) {
  if (!row.pattern) return "график не задан";
  return `${row.pattern} · ${wsTime(row.shift_start)}–${wsTime(row.shift_end)}`;
}

// Чистые правила формы дня: что записать и какую ошибку показать. Без DOM, его читает обертка.
function wsDayValuesToRequest(values) {
  const kind = values.kind || "";
  if (!kind) return { error: "Выберите, что стоит в этот день." };
  if (kind === "none") return { clear: true };
  if (kind !== "shift") return { body: { kind } };
  const start = String(values.start || "").trim();
  const end = String(values.end || "").trim();
  if (!start || !end) return { error: "Укажите, со скольки и до скольки работает сотрудник." };
  if (start === end) return { error: "Начало и конец смены не должны совпадать." };
  return { body: { kind, start_time: start, end_time: end } };
}

function wsAbsenceRequest(values) {
  const from = String(values.from || "");
  const to = String(values.to || "");
  if (!from || !to) return { error: "Укажите даты: с какого и по какое число." };
  if (to < from) return { error: "Дата «по» не может быть раньше даты «с»." };
  const days = Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86400000) + 1;
  if (days > WS_MAX_ABSENCE_DAYS) return { error: "Период не может быть длиннее года." };
  return { body: { kind: values.kind, date_from: from, date_to: to } };
}

// Факт: в каждой строке либо оба времени, либо ни одного (тогда факт идет из отметок «На работу»).
function wsFactItemsFromValues(rows) {
  const items = [];
  for (const row of rows) {
    const start = String(row.start || "").trim();
    const end = String(row.end || "").trim();
    if (Boolean(start) !== Boolean(end)) {
      return { error: `${wsFormatDateLabel(row.date)}: заполните и начало, и конец факта или оставьте оба пустыми.` };
    }
    if (start && start === end) {
      return { error: `${wsFormatDateLabel(row.date)}: начало и конец факта не должны совпадать.` };
    }
    items.push({ work_date: row.date, start_time: start || null, end_time: end || null });
  }
  return { items };
}

// Родительный падеж месяца: «6 ноября 2026».
const WS_MONTH_GENITIVE = [
  "января", "февраля", "марта", "апреля", "мая", "июня",
  "июля", "августа", "сентября", "октября", "ноября", "декабря",
];

function wsFormatDateLabel(dateKey) {
  const [year, month, day] = String(dateKey).split("-").map(Number);
  return `${day} ${WS_MONTH_GENITIVE[month - 1]} ${year}`;
}

// График часов по дням: серый — по графику, красный — по факту. Геометрия без DOM, чтобы ее можно было проверить.
function buildWsHoursChart(days, options = {}) {
  const width = options.width || 720;
  const height = options.height || 230;
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
  const bars = list.map((day, index) => {
    const center = pad.left + slot * index + slot / 2;
    const planHours = Number(day.plan_hours) || 0;
    const factHours = Number(day.fact_hours) || 0;
    const planHeight = (planHours / yMax) * innerHeight;
    const factHeight = (factHours / yMax) * innerHeight;
    return {
      day: index + 1,
      date: day.work_date,
      labelX: center,
      plan: { x: center - barWidth - 1, y: pad.top + innerHeight - planHeight, width: barWidth, height: planHeight, hours: planHours },
      fact: { x: center + 1, y: pad.top + innerHeight - factHeight, width: barWidth, height: factHeight, hours: factHours },
    };
  });
  const ticks = [];
  for (let value = 0; value <= yMax; value += 2) {
    ticks.push({ value, y: pad.top + innerHeight - (value / yMax) * innerHeight });
  }
  return { width, height, pad, yMax, bars, ticks };
}

function renderWsChartSvg(chart) {
  const { width, height, pad, ticks, bars } = chart;
  const grid = ticks
    .map(
      (tick) =>
        `<line class="ws-chart__grid" x1="${pad.left}" x2="${width - pad.right}" y1="${tick.y.toFixed(1)}" y2="${tick.y.toFixed(1)}"></line>` +
        `<text class="ws-chart__tick" x="${pad.left - 6}" y="${(tick.y + 3).toFixed(1)}" text-anchor="end">${tick.value}</text>`,
    )
    .join("");
  const columns = bars
    .map(
      (bar) =>
        `<rect class="ws-chart__plan" x="${bar.plan.x.toFixed(1)}" y="${bar.plan.y.toFixed(1)}" width="${bar.plan.width.toFixed(1)}" height="${bar.plan.height.toFixed(1)}">` +
        `<title>${bar.day}: по графику ${wsFormatHours(bar.plan.hours)} ч</title></rect>` +
        `<rect class="ws-chart__fact" x="${bar.fact.x.toFixed(1)}" y="${bar.fact.y.toFixed(1)}" width="${bar.fact.width.toFixed(1)}" height="${bar.fact.height.toFixed(1)}">` +
        `<title>${bar.day}: по факту ${wsFormatHours(bar.fact.hours)} ч</title></rect>` +
        `<text class="ws-chart__day" x="${bar.labelX.toFixed(1)}" y="${height - 8}" text-anchor="middle">${bar.day}</text>`,
    )
    .join("");
  return `<svg class="ws-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Часы по дням: серым по графику, красным по факту">${grid}${columns}</svg>`;
}

function wsInitialState() {
  const today = wsToday();
  return {
    year: today.year,
    month: today.month,
    mode: "view",
    // Медцентры для вкладок (из последнего ответа) и медцентр таблицы, выбранный на вкладке.
    centers: [],
    centerId: null,
    grid: null,
    loading: false,
    error: "",
    requestId: 0,
    selectedUserId: null,
    firstShiftUserId: null,
    stats: null,
    statsKey: "",
    statsOpen: false,
    // Что показывает открытая статистика: график часов или таблица отметок («list»).
    statsView: "chart",
    statsLoading: false,
    statsError: "",
    factEditing: false,
    busy: false,
  };
}

const wsState = wsInitialState();

function wsIsAdmin() {
  return appState.auth.roleCode === "admin";
}

// Медцентр таблицы: тот, что выбран на вкладке, а без выбора — медцентр последнего ответа.
function wsCenterId() {
  return wsState.centerId || wsState.grid?.center?.id || null;
}

function wsCenterLabel() {
  return wsState.grid?.center?.name || "";
}

// Каждый запрос правки называет медцентр: одна учетка может стоять в двух медцентрах.
function wsCenterQuery() {
  const id = wsCenterId();
  return id ? `center_id=${encodeURIComponent(id)}` : "";
}

function wsWithCenter(path) {
  const query = wsCenterQuery();
  return query ? `${path}?${query}` : path;
}

// Ставки и суммы видит только админ. Врач и оператор смотрят статистику своих часов без денег.
function wsCanSeeMoney() {
  return wsIsAdmin();
}

function wsCanOpen() {
  return canViewWorkSchedule();
}

// Статистика открыта и есть о ком ее считать: админу нужен выбранный сотрудник, врачу и оператору — они сами.
function wsStatsReady() {
  return wsState.statsOpen && (!wsIsAdmin() || Boolean(wsState.selectedUserId));
}

// Статистика открыта таблицей отметок, а не графиком.
function wsStatsListing() {
  return wsState.statsOpen && wsState.statsView === "list";
}

// Правка дней — админ в режиме «Редактировать» и только в текущем месяце.
function wsCanEdit() {
  if (!wsIsAdmin() || wsState.mode !== "edit") return false;
  const today = wsToday();
  return wsState.year === today.year && wsState.month === today.month;
}

// Выход из программы: новый номер запроса отбрасывает ответы, которые еще летят от прошлого сеанса.
function resetWorkSchedule() {
  const requestId = wsState.requestId + 1;
  Object.assign(wsState, wsInitialState(), { requestId });
}

function wsFindRow(userId) {
  return (wsState.grid?.rows || []).find((row) => Number(row.user_id) === Number(userId)) || null;
}

function wsFindDay(row, dateKey) {
  return (row?.days || []).find((day) => day.work_date === dateKey) || null;
}

function wsCellContent(day) {
  if (!day) return "";
  if (day.kind === "shift") {
    const number = day.shift_no ? `<span class="ws__cell-no">смена ${Number(day.shift_no)}</span>` : "";
    return `<span class="ws__cell-time">${wsEscape(wsTime(day.start_time))}-${wsEscape(wsTime(day.end_time))}</span>${number}`;
  }
  return `<span class="ws__cell-code">${wsEscape(WS_KIND_CODES[day.kind] || "")}</span>`;
}

// Смены того же сотрудника в других медцентрах в этот день: подсказка к клетке и окну дня.
function wsConflictText(day) {
  const items = Array.isArray(day?.conflicts) ? day.conflicts : [];
  if (!items.length) return "";
  const places = items.map((item) => `${item.center_name} ${wsTime(item.start_time)}–${wsTime(item.end_time)}`);
  return `В этот день смена также в медцентре: ${places.join(", ")}`;
}

function wsCellTitle(row, day, dateKey) {
  const label = wsFormatDateLabel(dateKey);
  if (!day) return `${row.full_name}, ${label}: пусто`;
  if (day.kind !== "shift") return `${row.full_name}, ${label}: ${WS_KIND_LABELS[day.kind] || day.kind}`;
  const plan = `${wsTime(day.start_time)}–${wsTime(day.end_time)}`;
  const fact = day.fact_start_time && day.fact_end_time ? `, факт ${wsTime(day.fact_start_time)}–${wsTime(day.fact_end_time)}` : "";
  const conflict = wsConflictText(day);
  return `${row.full_name}, ${label}: смена ${plan}${fact}${conflict ? `. ${conflict}` : ""}`;
}

function wsRenderRow(row, grid, editable) {
  const selected = Number(wsState.selectedUserId) === Number(row.user_id);
  // Строка стоит в таблице медцентра: полоска слева — цвет этого медцентра.
  const color = grid.center?.color || "";
  const days = [];
  const dayMap = new Map((row.days || []).map((day) => [day.work_date, day]));
  for (let day = 1; day <= grid.days_in_month; day += 1) {
    const dateKey = wsDateKey(grid.year, grid.month, day);
    const entry = dayMap.get(dateKey) || null;
    const weekend = wsIsWeekend(grid.year, grid.month, day);
    const kindClass = entry ? ` ws__cell--${entry.kind}` : " is-empty";
    const factChanged =
      entry && entry.kind === "shift" && entry.fact_start_time && entry.fact_end_time &&
      (entry.fact_start_time !== entry.start_time || entry.fact_end_time !== entry.end_time);
    // Красным — смена в этот день и в другом медцентре, где тоже работает этот сотрудник.
    const conflict = Boolean(entry && entry.kind === "shift" && Array.isArray(entry.conflicts) && entry.conflicts.length);
    const editAttrs = editable
      ? ` data-ws-cell data-ws-user="${wsEscape(row.user_id)}" data-ws-date="${dateKey}" tabindex="0" role="button"`
      : "";
    days.push(
      `<td class="ws__cell${kindClass}${weekend ? " is-weekend" : ""}${factChanged ? " is-fact-changed" : ""}${conflict ? " is-conflict" : ""}"${editAttrs} title="${wsEscape(wsCellTitle(row, entry, dateKey))}">${wsCellContent(entry)}</td>`,
    );
  }
  const nameAttrs = wsIsAdmin() ? ` data-ws-name="${wsEscape(row.user_id)}" tabindex="0" role="button"` : "";
  return `
    <tr class="ws__row${selected ? " is-selected" : ""}${row.is_active ? "" : " is-inactive"}" style="--ws-color: ${wsEscape(color)}">
      <th class="ws__name" scope="row"${nameAttrs}>
        <span class="ws__name-text">${wsEscape(row.full_name)}</span>
        <span class="ws__name-meta">${wsEscape(row.role_name)}</span>
        <span class="ws__name-meta">${wsEscape(wsRowMeta(row))}${row.is_active ? "" : " · отключен"}</span>
      </th>
      ${days.join("")}
    </tr>`;
}

function wsRenderTable(grid) {
  const weekdayHeads = [];
  const dayHeads = [];
  for (let day = 1; day <= grid.days_in_month; day += 1) {
    const weekend = wsIsWeekend(grid.year, grid.month, day) ? " is-weekend" : "";
    const weekday = WS_WEEKDAYS[wsWeekday(grid.year, grid.month, day)];
    weekdayHeads.push(`<th class="ws__day${weekend}" scope="col">${weekday}</th>`);
    dayHeads.push(`<th class="ws__day ws__day-no${weekend}" scope="col">${day}</th>`);
  }
  const editable = wsCanEdit();
  const emptyHint = wsIsAdmin() ? " Добавьте их в разделе «Сотрудники»." : "";
  const body = grid.rows.length
    ? grid.rows.map((row) => wsRenderRow(row, grid, editable)).join("")
    : `<tr><td class="ws__empty" colspan="${grid.days_in_month + 1}">В этом медцентре пока нет сотрудников.${emptyHint}</td></tr>`;
  return `
    <div class="ws__scroll">
      <table class="ws__table">
        <thead>
          <tr><th class="ws__name ws__corner" scope="col" rowspan="2">Сотрудник</th>${weekdayHeads.join("")}</tr>
          <tr>${dayHeads.join("")}</tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>`;
}

// Вкладки медцентров: таблица одна на медцентр, поэтому сотрудник с двумя медцентрами виден в обоих.
function wsRenderCenterTabs(centers, activeId) {
  const list = Array.isArray(centers) ? centers : [];
  if (!list.length) return `<div class="ws__tabs"><span class="muted">Медцентры не назначены.</span></div>`;
  const tabs = list
    .map((center) => {
      const active = Number(center.id) === Number(activeId);
      return `<button class="ws__tab${active ? " is-active" : ""}" type="button" aria-pressed="${active ? "true" : "false"}" data-ws-center="${wsEscape(center.id)}" style="--ws-color: ${wsEscape(center.color || "")}">${wsEscape(center.name)}</button>`;
    })
    .join("");
  return `<div class="ws__tabs" role="group" aria-label="Медцентр">${tabs}</div>`;
}

function wsRenderLegend() {
  return `
    <div class="ws__legend">
      <span class="ws__legend-group">
        <span class="ws__key ws__key--shift">смена</span>
        <span class="ws__key ws__key--dayoff">Отг — отгул</span>
        <span class="ws__key ws__key--sick">Бол — больничный</span>
        <span class="ws__key ws__key--vacation">Отп — отпуск</span>
        <span class="ws__key ws__key--conflict">красным — смена в двух медцентрах в один день</span>
        <span class="ws__key ws__key--fact">красная точка — факт отличается</span>
      </span>
    </div>`;
}

function wsRenderSelection(row) {
  if (!row) return "";
  const canEdit = wsCanEdit();
  const hasPattern = Boolean(row.pattern);
  const firstShiftHint = hasPattern
    ? "Выбрать день, с которого начинается график"
    : "У сотрудника не задан график: задайте его в разделе «Сотрудник»";
  return `
    <div class="ws__selection" data-ws-selection="${wsEscape(row.user_id)}">
      <span class="ws__selection-name">Выбран: <b>${wsEscape(row.full_name)}</b></span>
      ${canEdit
        ? `<button class="ghost-button" type="button" data-ws-first-shift-start="${wsEscape(row.user_id)}" ${hasPattern ? "" : "disabled"} title="${wsEscape(firstShiftHint)}">Назначить первую смену</button>
           <button class="ghost-button" type="button" data-ws-absence="vacation" data-ws-user="${wsEscape(row.user_id)}">Добавить отпуск</button>
           <button class="ghost-button" type="button" data-ws-absence="sick" data-ws-user="${wsEscape(row.user_id)}">Больничный</button>`
        : ""}
      <button class="ghost-button" type="button" data-ws-stats-toggle>${wsState.statsOpen ? "Скрыть статистику" : "Статистика"}</button>
      <button class="ghost-button" type="button" data-ws-clear-selection>Снять выбор</button>
    </div>`;
}

function wsRenderBanner() {
  const row = wsFindRow(wsState.firstShiftUserId);
  if (!row) return "";
  return `
    <div class="ws__banner" role="status">
      Нажмите на день, с которого начинается график: <b>${wsEscape(row.full_name)}</b>.
      <button class="ghost-button" type="button" data-ws-first-shift-cancel>Отмена</button>
    </div>`;
}

function wsRenderFooter(grid) {
  const admin = wsIsAdmin();
  const editing = wsState.mode === "edit";
  const statsButton = `<button class="ghost-button" type="button" data-ws-stats-toggle>${wsState.statsOpen ? "Скрыть статистику" : "Статистика"}</button>`;
  // «Списки» переключают статистику между графиком и таблицей отметок; из таблицы кнопка возвращает график.
  const listButton = `<button class="ghost-button" type="button" data-ws-list-toggle>${wsStatsListing() ? "График" : "Списки"}</button>`;
  const reportButton = `<button class="ghost-button" type="button" data-ws-report>Сформировать месяц</button>`;
  const tools = admin
    ? `<div class="ws__tools">
         <button class="primary-button" type="button" data-ws-create ${wsState.busy ? "disabled" : ""}>Создать график</button>
         <button class="ghost-button" type="button" data-ws-edit-toggle>${editing ? "Закрыть редактирование" : "Редактировать"}</button>
         ${statsButton}
         ${listButton}
         ${reportButton}
       </div>`
    : `<div class="ws__tools">${statsButton}${listButton}${reportButton}</div>`;
  return `
    <div class="ws__footer">
      <div class="ws__months">
        <button class="ghost-button" type="button" data-ws-month="-1" aria-label="Предыдущий месяц">◀</button>
        <span class="ws__month">${wsEscape(wsMonthTitle(grid.year, grid.month))}</span>
        <button class="ghost-button" type="button" data-ws-month="1" aria-label="Следующий месяц">▶</button>
      </div>
      ${tools}
    </div>`;
}

function wsRenderStatsPanel() {
  if (!wsCanOpen() || !wsState.statsOpen) return "";
  const admin = wsIsAdmin();
  const row = admin ? wsFindRow(wsState.selectedUserId) : null;
  if (admin && !row) {
    return `<div class="ws__stats"><div class="empty">Нажмите на имя сотрудника, чтобы увидеть его статистику.</div></div>`;
  }
  if (wsState.statsLoading && !wsState.stats) {
    return `<div class="ws__stats"><div class="empty">Считаем статистику…</div></div>`;
  }
  if (wsState.statsError) {
    return `<div class="ws__stats"><div class="note employee-note employee-note--error">${wsEscape(wsState.statsError)}</div></div>`;
  }
  // Админ смотрит выбранного сотрудника, врач и оператор — только себя.
  const userId = admin ? row.user_id : appState.auth.userId;
  const stat = (wsState.stats?.rows || []).find((item) => Number(item.user_id) === Number(userId));
  if (!stat) return `<div class="ws__stats"><div class="empty">Статистики за этот месяц пока нет.</div></div>`;
  const money = wsCanSeeMoney();
  const listing = wsStatsListing();
  const rateLine = stat.hourly_rate == null ? "ставка не задана" : `ставка ${wsFormatMoney(stat.hourly_rate)} в час`;
  const factEditor = admin && wsState.factEditing ? wsRenderFactEditor(row, stat) : "";
  return `
    <div class="ws__stats" data-ws-stats="${wsEscape(stat.user_id)}" data-ws-stats-view="${listing ? "list" : "chart"}">
      <div class="ws__stats-head">
        <div>
          <h4>Статистика: ${wsEscape(stat.full_name)}</h4>
          <div class="muted">${wsEscape(wsMonthTitle(wsState.year, wsState.month))} · ${wsEscape(wsRowMeta(stat))}${money ? ` · ${wsEscape(rateLine)}` : ""}</div>
        </div>
        <div class="ws__stats-actions">
          ${admin ? `<button class="ghost-button" type="button" data-ws-fact-toggle>${wsState.factEditing ? "Закрыть правку факта" : "Редактировать факт"}</button>` : ""}
          <button class="ghost-button" type="button" data-ws-stats-toggle>Закрыть</button>
        </div>
      </div>
      ${listing
        ? wsRenderMarksTable(stat)
        : `<div class="ws__legend-chart"><span class="ws-legend-dot is-plan"></span>по графику <span class="ws-legend-dot is-fact"></span>по факту, часов в день</div>
      <div class="ws__chart">${renderWsChartSvg(buildWsHoursChart(stat.days))}</div>`}
      <table class="ws__summary">
        <thead><tr><th></th><th>Дней</th><th>Часов</th>${money ? "<th>Сумма (часы × ставка)</th>" : ""}</tr></thead>
        <tbody>
          <tr><th scope="row">План по графику</th><td>${stat.plan.days}</td><td>${wsFormatHours(stat.plan.hours)}</td>${money ? `<td>${wsFormatMoney(stat.plan.amount)}</td>` : ""}</tr>
          <tr><th scope="row">Факт</th><td>${stat.fact.days}</td><td>${wsFormatHours(stat.fact.hours)}</td>${money ? `<td>${wsFormatMoney(stat.fact.amount)}</td>` : ""}</tr>
        </tbody>
      </table>
      ${factEditor}
    </div>`;
}

// Список «Списки»: отметки месяца из поля marks и ручные правки факта (mark.manual), новые сверху, время как отмечено.
// Открытая отметка и отметка длиннее 12 часов красные, как в блоке «Статуса»; правка красной не бывает, она помечена
// словом «вручную». Сам вид строк и даты берется из work-status.js.
function wsRenderMarksTable(stat) {
  const marks = Array.isArray(stat.marks) ? stat.marks : [];
  if (!marks.length) {
    return `<div class="empty">В этом месяце отметок «На работу» пока нет.</div>`;
  }
  const lines = marks
    .map((mark) => {
      const flag = mark.manual ? "" : wstMarkFlag(mark);
      const rowClass = flag ? `wst-marks__row wst-marks__row--${flag}` : "wst-marks__row";
      let hint = "";
      if (flag === "open") hint = "Нет отметки «С работы»";
      else if (flag === "long") hint = "Дольше 12 часов: проверьте, не забыли ли отметить уход";
      else if (mark.manual) hint = "Ручная правка факта: в статистике день считается по ней, а не по отметкам";
      const name = `${wsEscape(stat.full_name)}${mark.manual ? '<span class="wst-marks__manual">вручную</span>' : ""}`;
      const end = mark.ended_at ? wstStampHtml(mark.ended_at) : "на работе";
      return (
        `<tr class="${rowClass}"${hint ? ` title="${wsEscape(hint)}"` : ""}>` +
        `<td>${name}</td><td>${wstStampHtml(mark.started_at)}</td><td>${end}</td>` +
        `<td>${wstFormatElapsed(mark.duration_seconds)}</td></tr>`
      );
    })
    .join("");
  return `
    <div class="ws__scroll wst-marks">
      <table class="ws__summary wst-marks__table">
        <thead><tr><th>Сотрудник</th><th>Начало</th><th>Конец</th><th>Длит.</th></tr></thead>
        <tbody>${lines}</tbody>
      </table>
    </div>`;
}

function wsRenderFactEditor(row, stat) {
  const shiftDays = stat.days.filter((day) => day.plan_hours > 0);
  const planByDate = new Map((row.days || []).map((day) => [day.work_date, day]));
  const lines = shiftDays
    .map((day) => {
      const dateKey = day.work_date;
      const entry = planByDate.get(dateKey) || {};
      const factStart = entry.fact_start_time ? wsTime(entry.fact_start_time) : "";
      const factEnd = entry.fact_end_time ? wsTime(entry.fact_end_time) : "";
      return `
        <tr>
          <td>${wsEscape(wsFormatDateLabel(dateKey))}</td>
          <td>${wsEscape(wsTime(entry.start_time))}–${wsEscape(wsTime(entry.end_time))}</td>
          <td><input type="time" data-ws-fact-start="${dateKey}" value="${wsEscape(factStart)}" aria-label="Факт, начало" /></td>
          <td><input type="time" data-ws-fact-end="${dateKey}" value="${wsEscape(factEnd)}" aria-label="Факт, конец" /></td>
        </tr>`;
    })
    .join("");
  return `
    <form class="ws__fact-form" data-ws-fact-form="${wsEscape(row.user_id)}">
      <h4>Фактическое время</h4>
      <p class="muted">Пустые поля: факт берется из отметок «На работу». Заполненные поля заменяют отметки этого дня.</p>
      ${lines
        ? `<table class="ws__summary"><thead><tr><th>Дата</th><th>По графику</th><th>Факт с</th><th>Факт до</th></tr></thead><tbody>${lines}</tbody></table>`
        : '<div class="empty">В этом месяце у сотрудника нет смен.</div>'}
      <div class="note employee-note employee-note--error hidden" data-ws-fact-error></div>
      <div class="ws__form-actions">
        <button class="primary-button" type="submit" ${lines ? "" : "disabled"}>Сохранить факт</button>
        <button class="ghost-button" type="button" data-ws-fact-cancel>Отмена</button>
      </div>
    </form>`;
}

function renderWorkScheduleContent() {
  if (!wsCanOpen()) {
    return `
      <section class="card">
        <h3>График работы</h3>
        <div class="note">Раздел доступен админу, врачу и оператору.</div>
      </section>`;
  }
  const grid = wsState.grid;
  const admin = wsIsAdmin();
  const editing = wsCanEdit();
  // Вкладки берутся из последнего ответа и остаются на месте, пока таблица нового медцентра грузится.
  const centers = wsState.centers.length ? wsState.centers : grid?.centers || [];
  const tabs = wsRenderCenterTabs(centers, wsCenterId());
  let body;
  if (!grid) {
    const note = wsState.error ? `<div class="note employee-note employee-note--error">${wsEscape(wsState.error)}</div>` : "";
    const message = wsState.loading
      ? `<div class="empty">Загружаем график...</div>`
      : `<div class="empty">График пока не загружен.</div>`;
    body = `${tabs}${note}${message}`;
  } else {
    const selectedRow = admin ? wsFindRow(wsState.selectedUserId) : null;
    body = `
      ${tabs}
      ${wsRenderLegend()}
      ${wsState.error ? `<div class="note employee-note employee-note--error">${wsEscape(wsState.error)}</div>` : ""}
      ${editing ? `<div class="ws__hint">Нажмите на день, чтобы задать смену, отгул, больничный или отпуск. Нажмите на имя, чтобы выбрать сотрудника.</div>` : ""}
      ${wsRenderBanner()}
      ${wsRenderSelection(selectedRow)}
      ${wsRenderTable(grid)}
      ${wsRenderStatsPanel()}
      ${wsRenderFooter(grid)}
      ${admin ? "" : `<div class="ws__hint muted">Таблица только для просмотра. Правит график администратор. Статистика показывает только ваши часы.</div>`}`;
  }
  return `
    <section class="card ws${editing ? " is-editing" : ""}" data-work-schedule>
      <div class="ws__head">
        <div>
          <h3>График работы${grid ? ` — ${wsEscape(wsMonthTitle(grid.year, grid.month))}` : ""}</h3>
          <p class="muted">${admin ? "Вкладка — медцентр, у каждого свой график. Сотрудник с двумя медцентрами виден в обоих; красным — смены в двух медцентрах в один день." : "Смены сотрудников выбранного медцентра."}</p>
        </div>
      </div>
      ${body}
    </section>`;
}

// Загрузка и действия.

async function loadWorkSchedule() {
  if (!wsCanOpen()) return;
  const requestId = ++wsState.requestId;
  wsState.loading = true;
  wsState.error = "";
  renderApp();
  try {
    const query = wsCenterQuery();
    const grid = await apiRequest(`/work-schedule/month?year=${wsState.year}&month=${wsState.month}${query ? `&${query}` : ""}`);
    if (requestId !== wsState.requestId) return;
    wsState.grid = grid;
    wsState.centers = grid.centers || [];
    wsState.centerId = grid.center?.id ?? wsState.centerId;
    if (wsState.selectedUserId && !wsFindRow(wsState.selectedUserId)) wsState.selectedUserId = null;
    if (wsState.firstShiftUserId && !wsFindRow(wsState.firstShiftUserId)) wsState.firstShiftUserId = null;
    if (wsStatsReady()) {
      loadWorkStats();
    }
  } catch (error) {
    if (requestId !== wsState.requestId) return;
    wsState.error = humanizeApiError(error, "Не удалось загрузить график");
  } finally {
    if (requestId === wsState.requestId) {
      wsState.loading = false;
      renderApp();
    }
  }
}

function wsStatsKey() {
  return `${wsState.year}-${wsState.month}-${wsCenterId() || ""}`;
}

async function loadWorkStats() {
  if (!wsCanOpen()) return null;
  const key = wsStatsKey();
  wsState.statsLoading = true;
  wsState.statsError = "";
  try {
    const query = wsCenterQuery();
    const stats = await apiRequest(`/work-schedule/stats?year=${wsState.year}&month=${wsState.month}${query ? `&${query}` : ""}`);
    wsState.stats = stats;
    wsState.statsKey = key;
    return stats;
  } catch (error) {
    wsState.statsError = humanizeApiError(error, "Не удалось посчитать статистику");
    return null;
  } finally {
    wsState.statsLoading = false;
    renderApp();
  }
}

// Отправка изменения: при успехе перечитываем таблицу и статистику, при ошибке возвращаем текст.
async function wsSend(path, method, body) {
  const options = { method };
  if (body !== undefined) options.body = body;
  try {
    await apiRequest(path, options);
    wsState.stats = null;
    return "";
  } catch (error) {
    return humanizeApiError(error, "Не удалось сохранить график");
  }
}

// Правка дней — только в текущем месяце: при переходе в другой месяц режим правки выключается.
function wsSetMonth(year, month) {
  const today = wsToday();
  if (year !== today.year || month !== today.month) wsState.mode = "view";
  wsState.year = year;
  wsState.month = month;
  wsState.selectedUserId = null;
  wsState.firstShiftUserId = null;
  wsState.statsOpen = false;
  wsState.stats = null;
  wsState.factEditing = false;
  loadWorkSchedule();
}

// Вкладка медцентра: таблица и статистика берутся для него, выбор и факт сбрасываются. Старую таблицу
// убираем сразу, чтобы клик по клетке не ушел в другой медцентр.
function wsSelectCenter(centerId) {
  const id = Number(centerId);
  if (!id || id === Number(wsCenterId())) return;
  wsState.centerId = id;
  wsState.grid = null;
  wsState.selectedUserId = null;
  wsState.firstShiftUserId = null;
  wsState.statsOpen = false;
  wsState.stats = null;
  wsState.statsError = "";
  wsState.factEditing = false;
  loadWorkSchedule();
}

function wsToggleEdit() {
  if (!wsIsAdmin()) return;
  if (wsState.mode === "edit") {
    wsState.mode = "view";
    wsState.firstShiftUserId = null;
    renderApp();
    return;
  }
  const today = wsToday();
  wsState.mode = "edit";
  wsState.selectedUserId = null;
  wsState.firstShiftUserId = null;
  if (wsState.year !== today.year || wsState.month !== today.month) {
    wsSetMonth(today.year, today.month);
  } else {
    renderApp();
  }
}

async function wsCreateSchedule() {
  if (!wsIsAdmin() || wsState.busy) return;
  const today = wsToday();
  const target = wsResolveCreateTarget(today, { year: wsState.year, month: wsState.month });
  wsState.busy = true;
  renderApp();
  try {
    const result = await apiRequest("/work-schedule/month/generate", {
      method: "POST",
      body: { year: target.year, month: target.month, center_id: wsCenterId() },
    });
    const missing = result.users_without_start || [];
    const notes = missing.length
      ? ` Не назначена первая смена: ${missing.join(", ")}. Выберите сотрудника и нажмите «Назначить первую смену».`
      : "";
    const centerName = wsCenterLabel();
    showToast(`График${centerName ? ` ${centerName}` : ""} на ${wsMonthTitle(target.year, target.month)} создан: смен ${result.created}.${notes}`);
    wsSetMonth(target.year, target.month);
  } catch (error) {
    showToast(humanizeApiError(error, "Не удалось создать график"));
  } finally {
    wsState.busy = false;
    renderApp();
  }
}

function wsSelectUser(userId) {
  const id = Number(userId);
  wsState.selectedUserId = Number(wsState.selectedUserId) === id ? null : id;
  wsState.factEditing = false;
  if (!wsState.selectedUserId) {
    wsState.statsOpen = false;
    wsState.firstShiftUserId = null;
  }
  wsState.stats = null;
  if (wsState.statsOpen && wsState.selectedUserId) loadWorkStats();
  renderApp();
}

function wsToggleStats() {
  if (!wsCanOpen()) return;
  if (wsIsAdmin() && !wsState.selectedUserId) {
    showToast("Выберите сотрудника: нажмите на его имя в таблице.");
    return;
  }
  wsState.statsOpen = !wsState.statsOpen;
  wsState.factEditing = false;
  if (wsState.statsOpen) {
    wsState.statsView = "chart";
    wsState.stats = null;
    loadWorkStats();
  }
  renderApp();
}

// «Списки» переключают статистику между графиком и таблицей отметок. Если статистика закрыта, открывают ее таблицей.
function wsToggleList() {
  if (!wsCanOpen()) return;
  if (wsIsAdmin() && !wsState.selectedUserId) {
    showToast("Выберите сотрудника: нажмите на его имя в таблице.");
    return;
  }
  if (wsState.statsOpen) {
    wsState.statsView = wsState.statsView === "list" ? "chart" : "list";
  } else {
    wsState.statsOpen = true;
    wsState.statsView = "list";
    wsState.factEditing = false;
    wsState.stats = null;
    loadWorkStats();
  }
  renderApp();
}

async function wsCellClick(userId, dateKey) {
  if (!wsCanEdit()) return;
  const row = wsFindRow(userId);
  if (!row) return;
  if (wsState.firstShiftUserId) {
    if (Number(wsState.firstShiftUserId) !== Number(userId)) {
      showToast(`Выберите день в строке: ${row.full_name}.`);
      return;
    }
    const label = wsFormatDateLabel(dateKey);
    if (!window.confirm(`Начать график ${row.full_name} с ${label}?\n\nАвто-смены с этого дня пересчитаются заново. Отгулы, больничные, отпуска и ручные смены останутся.`)) return;
    wsState.firstShiftUserId = null;
    wsState.busy = true;
    renderApp();
    const error = await wsSend(wsWithCenter(`/work-schedule/${encodeURIComponent(userId)}/first-shift`), "POST", { work_date: dateKey });
    wsState.busy = false;
    if (error) {
      showToast(error);
      renderApp();
      return;
    }
    showToast(`График ${row.full_name} начат с ${label}.`);
    await loadWorkSchedule();
    return;
  }
  openWsDayModal(userId, dateKey);
}

function wsDayModalHtml(row, dateKey) {
  const day = wsFindDay(row, dateKey);
  const kind = day ? day.kind : "shift";
  const start = day && day.kind === "shift" ? wsTime(day.start_time) : wsTime(row.shift_start);
  const end = day && day.kind === "shift" ? wsTime(day.end_time) : wsTime(row.shift_end);
  const options = ["shift", "dayoff", "sick", "vacation", "none"]
    .map((value) => {
      const label = value === "none" ? "Без смены (очистить день)" : WS_KIND_LABELS[value];
      return `<label class="ws-day-form__kind"><input type="radio" name="kind" value="${value}" ${value === kind ? "checked" : ""} /> ${label}</label>`;
    })
    .join("");
  const hint = row.pattern
    ? `По графику ${wsEscape(row.pattern)}: ${wsEscape(wsTime(row.shift_start))}–${wsEscape(wsTime(row.shift_end))}.`
    : "Сотрудник работает вручную: время смены задайте здесь.";
  const conflict = wsConflictText(day);
  const centerName = wsCenterLabel();
  return `
    <form class="ws-day-form" data-ws-day-form="${wsEscape(row.user_id)}" data-ws-date="${dateKey}">
      <p class="ws-day-form__date">${wsEscape(wsFormatDateLabel(dateKey))} · ${wsEscape(row.full_name)}${centerName ? ` · ${wsEscape(centerName)}` : ""}</p>
      <fieldset class="ws-day-form__kinds">${options}</fieldset>
      <div class="ws-day-form__times">
        <label>Со скольки <input type="time" name="start" value="${wsEscape(start)}" /></label>
        <label>До скольки <input type="time" name="end" value="${wsEscape(end)}" /></label>
      </div>
      <p class="ws-day-form__hint">${hint}</p>
      ${conflict ? `<p class="ws-day-form__hint ws-day-form__conflict">${wsEscape(conflict)}. Проверьте, что сотрудник успевает в обе смены.</p>` : ""}
      <div class="note employee-note employee-note--error hidden" data-ws-day-error></div>
      <div class="ws-day-form__actions">
        <button class="primary-button" type="submit">Сохранить</button>
        <button class="ghost-button" type="button" data-ws-day-cancel>Отмена</button>
      </div>
    </form>`;
}

function openWsDayModal(userId, dateKey) {
  const row = wsFindRow(userId);
  if (!row) return;
  openActionModal(row.full_name, wsDayModalHtml(row, dateKey), "modal--schedule-day");
  const form = actionModalContent?.querySelector("[data-ws-day-form]");
  if (!form) return;
  const showError = (message) => {
    const note = form.querySelector("[data-ws-day-error]");
    if (!note) return;
    note.textContent = message;
    note.classList.remove("hidden");
  };
  form.querySelector("[data-ws-day-cancel]")?.addEventListener("click", () => closeActionModal());
  form.addEventListener("input", () => form.querySelector("[data-ws-day-error]")?.classList.add("hidden"));
  form.addEventListener("change", () => form.querySelector("[data-ws-day-error]")?.classList.add("hidden"));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = {
      kind: form.querySelector('input[name="kind"]:checked')?.value || "",
      start: form.querySelector('input[name="start"]')?.value || "",
      end: form.querySelector('input[name="end"]')?.value || "",
    };
    const request = wsDayValuesToRequest(values);
    if (request.error) return showError(request.error);
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.disabled = true;
    const path = wsWithCenter(`/work-schedule/${encodeURIComponent(userId)}/days/${dateKey}`);
    const error = request.clear
      ? await wsSend(path, "DELETE")
      : await wsSend(path, "PUT", request.body);
    if (error) {
      if (submit) submit.disabled = false;
      return showError(error);
    }
    closeActionModal();
    await loadWorkSchedule();
  });
}

function wsAbsenceModalHtml(row, kind) {
  const today = wsToday();
  const inMonth = today.year === wsState.year && today.month === wsState.month;
  const defaultDay = inMonth ? today.day : 1;
  const from = wsDateKey(wsState.year, wsState.month, defaultDay);
  return `
    <form class="ws-day-form" data-ws-absence-form="${wsEscape(row.user_id)}" data-ws-kind="${wsEscape(kind)}">
      <p class="ws-day-form__date">${wsEscape(WS_KIND_LABELS[kind])} · ${wsEscape(row.full_name)}${wsCenterLabel() ? ` · ${wsEscape(wsCenterLabel())}` : ""}</p>
      <div class="ws-day-form__times">
        <label>С какого числа <input type="date" name="from" value="${from}" /></label>
        <label>По какое число <input type="date" name="to" value="${from}" /></label>
      </div>
      <p class="ws-day-form__hint">Все дни периода станут «${wsEscape(WS_KIND_LABELS[kind].toLowerCase())}»: время смены в них пропадает, цикл графика не сдвигается.</p>
      <div class="note employee-note employee-note--error hidden" data-ws-day-error></div>
      <div class="ws-day-form__actions">
        <button class="primary-button" type="submit">Сохранить период</button>
        <button class="ghost-button" type="button" data-ws-day-cancel>Отмена</button>
      </div>
    </form>`;
}

function openWsAbsenceModal(userId, kind) {
  const row = wsFindRow(userId);
  if (!row || !wsCanEdit()) return;
  openActionModal(row.full_name, wsAbsenceModalHtml(row, kind), "modal--schedule-day");
  const form = actionModalContent?.querySelector("[data-ws-absence-form]");
  if (!form) return;
  form.querySelector("[data-ws-day-cancel]")?.addEventListener("click", () => closeActionModal());
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const request = wsAbsenceRequest({
      kind,
      from: form.querySelector('input[name="from"]')?.value || "",
      to: form.querySelector('input[name="to"]')?.value || "",
    });
    const note = form.querySelector("[data-ws-day-error]");
    if (request.error) {
      if (note) {
        note.textContent = request.error;
        note.classList.remove("hidden");
      }
      return;
    }
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.disabled = true;
    const error = await wsSend(wsWithCenter(`/work-schedule/${encodeURIComponent(userId)}/absences`), "POST", request.body);
    if (error) {
      if (submit) submit.disabled = false;
      if (note) {
        note.textContent = error;
        note.classList.remove("hidden");
      }
      return;
    }
    closeActionModal();
    showToast(`${WS_KIND_LABELS[kind]}: ${row.full_name} записан(а) на период.`);
    await loadWorkSchedule();
  });
}

function wsStartFirstShift(userId) {
  const row = wsFindRow(userId);
  if (!row || !wsCanEdit()) return;
  if (!row.pattern) {
    showToast("У сотрудника не задан график: задайте его в разделе «Сотрудник».");
    return;
  }
  wsState.firstShiftUserId = Number(userId);
  renderApp();
}

function wsSaveFacts(userId) {
  const form = document.querySelector(`[data-ws-fact-form="${userId}"]`);
  if (!form) return;
  const rows = [...form.querySelectorAll("[data-ws-fact-start]")].map((input) => {
    const dateKey = input.getAttribute("data-ws-fact-start");
    const end = form.querySelector(`[data-ws-fact-end="${dateKey}"]`);
    return { date: dateKey, start: input.value, end: end ? end.value : "" };
  });
  const prepared = wsFactItemsFromValues(rows);
  const note = form.querySelector("[data-ws-fact-error]");
  if (prepared.error) {
    if (note) {
      note.textContent = prepared.error;
      note.classList.remove("hidden");
    }
    return;
  }
  wsState.busy = true;
  renderApp();
  wsSend(wsWithCenter(`/work-schedule/${encodeURIComponent(userId)}/facts`), "PUT", { items: prepared.items }).then(async (error) => {
    wsState.busy = false;
    if (error) {
      showToast(error);
      renderApp();
      return;
    }
    wsState.factEditing = false;
    showToast("Факт сохранен");
    await loadWorkSchedule();
    if (wsState.statsOpen) await loadWorkStats();
  });
}

// Отчет без денег (withMoney=false) — для врача и оператора: часы остаются, ставка и суммы уходят.
function wsMonthReportHtml(stats, withMoney = wsCanSeeMoney()) {
  const centerName = stats.center?.name ? ` — ${stats.center.name}` : "";
  const title = `График работы${centerName} — ${wsMonthTitle(stats.year, stats.month)}`;
  const totals = { planDays: 0, planHours: 0, planAmount: 0, factDays: 0, factHours: 0, factAmount: 0 };
  const lines = stats.rows
    .map((row, index) => {
      totals.planDays += row.plan.days;
      totals.planHours += row.plan.hours;
      totals.factDays += row.fact.days;
      totals.factHours += row.fact.hours;
      if (row.plan.amount != null) totals.planAmount += row.plan.amount;
      if (row.fact.amount != null) totals.factAmount += row.fact.amount;
      return `
        <tr>
          <td>${index + 1}</td>
          <td>${wsEscape(row.full_name)}</td>
          <td>${wsEscape(row.role_name)}</td>
          <td>${wsEscape(row.center_name || "")}</td>
          <td>${wsEscape(row.pattern ? `${row.pattern}, ${wsTime(row.shift_start)}–${wsTime(row.shift_end)}` : "не задан")}</td>
          ${withMoney ? `<td class="num">${row.hourly_rate == null ? "—" : wsEscape(wsFormatHours(row.hourly_rate))}</td>` : ""}
          <td class="num">${row.plan.days}</td>
          <td class="num">${wsFormatHours(row.plan.hours)}</td>
          ${withMoney ? `<td class="num">${wsFormatMoney(row.plan.amount)}</td>` : ""}
          <td class="num">${row.fact.days}</td>
          <td class="num">${wsFormatHours(row.fact.hours)}</td>
          ${withMoney ? `<td class="num">${wsFormatMoney(row.fact.amount)}</td>` : ""}
        </tr>`;
    })
    .join("");
  return `<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>${wsEscape(title)}</title>
  <style>
    @page { size: A4 landscape; margin: 12mm; }
    body { margin: 0; color: #111827; font-family: "Arial Cyr", Arial, sans-serif; font-size: 11px; }
    h1 { margin: 0 0 10px; font-size: 18px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border: 1px solid #9ca3af; padding: 4px 5px; vertical-align: top; }
    th { background: #e5e7eb; text-align: left; }
    td.num { text-align: right; white-space: nowrap; }
    tfoot td { font-weight: 700; }
    .sign { display: flex; justify-content: space-between; margin-top: 28px; }
    .sign div { width: 40%; border-top: 1px solid #111827; padding-top: 4px; }
  </style>
</head>
<body>
  <h1>${wsEscape(title)}</h1>
  <table>
    <thead>
      <tr>
        <th>№</th><th>Сотрудник</th><th>Роль</th><th>Медцентр</th><th>График</th>${withMoney ? "<th>Ставка, ₽/ч</th>" : ""}
        <th>План: дней</th><th>План: часов</th>${withMoney ? "<th>План: сумма</th>" : ""}
        <th>Факт: дней</th><th>Факт: часов</th>${withMoney ? "<th>Факт: сумма</th>" : ""}
      </tr>
    </thead>
    <tbody>${lines || `<tr><td colspan="${withMoney ? 12 : 9}">В этом месяце нет сотрудников с графиком.</td></tr>`}</tbody>
    <tfoot>
      <tr>
        <td colspan="${withMoney ? 6 : 5}">Итого</td>
        <td class="num">${totals.planDays}</td><td class="num">${wsFormatHours(totals.planHours)}</td>${withMoney ? `<td class="num">${wsFormatMoney(totals.planAmount)}</td>` : ""}
        <td class="num">${totals.factDays}</td><td class="num">${wsFormatHours(totals.factHours)}</td>${withMoney ? `<td class="num">${wsFormatMoney(totals.factAmount)}</td>` : ""}
      </tr>
    </tfoot>
  </table>
  <div class="sign"><div>Ответственный</div><div>Бухгалтер</div></div>
</body>
</html>`;
}

// «Сформировать месяц»: окно печати, как у кассы. Окно открываем сразу, иначе браузер его заблокирует.
async function openWsMonthReport() {
  if (!wsCanOpen()) return;
  const printWindow = window.open("about:blank", "_blank");
  if (!printWindow) {
    showToast("Браузер заблокировал окно печати");
    return;
  }
  printWindow.document.write('<!doctype html><meta charset="utf-8"><p style="font-family:Arial">Готовим отчет…</p>');
  const stats = wsState.stats && wsState.statsKey === wsStatsKey() ? wsState.stats : await loadWorkStats();
  if (!stats) {
    printWindow.close();
    showToast(wsState.statsError || "Не удалось сформировать отчет");
    return;
  }
  printWindow.document.open();
  printWindow.document.write(wsMonthReportHtml(stats));
  printWindow.document.close();
  printWindow.focus();
  window.setTimeout(() => {
    try {
      printWindow.print();
    } catch (error) {
      console.warn("Не удалось открыть печать графика", error);
    }
  }, 250);
}

// Обработчики раздела. Вызывается после каждой перерисовки: элементы каждый раз новые.
function bindWorkScheduleEvents() {
  const root = document.querySelector("[data-work-schedule]");
  if (!root) return;

  root.querySelectorAll("[data-ws-month]").forEach((button) => {
    button.addEventListener("click", () => {
      const next = wsShiftMonth(wsState.year, wsState.month, Number(button.dataset.wsMonth) || 0);
      wsSetMonth(next.year, next.month);
    });
  });

  root.querySelectorAll("[data-ws-center]").forEach((button) => {
    button.addEventListener("click", () => wsSelectCenter(button.dataset.wsCenter));
  });

  root.querySelectorAll("[data-ws-name]").forEach((element) => {
    element.addEventListener("click", () => wsSelectUser(element.dataset.wsName));
    element.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        wsSelectUser(element.dataset.wsName);
      }
    });
  });

  root.querySelectorAll("[data-ws-cell]").forEach((cell) => {
    const open = () => wsCellClick(cell.dataset.wsUser, cell.dataset.wsDate);
    cell.addEventListener("click", open);
    cell.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        open();
      }
    });
  });

  root.querySelector("[data-ws-create]")?.addEventListener("click", wsCreateSchedule);
  root.querySelector("[data-ws-edit-toggle]")?.addEventListener("click", wsToggleEdit);
  root.querySelectorAll("[data-ws-stats-toggle]").forEach((button) => button.addEventListener("click", wsToggleStats));
  root.querySelectorAll("[data-ws-list-toggle]").forEach((button) => button.addEventListener("click", wsToggleList));
  root.querySelector("[data-ws-report]")?.addEventListener("click", openWsMonthReport);
  root.querySelector("[data-ws-clear-selection]")?.addEventListener("click", () => wsSelectUser(wsState.selectedUserId));
  root.querySelectorAll("[data-ws-first-shift-start]").forEach((button) => {
    button.addEventListener("click", () => wsStartFirstShift(button.dataset.wsFirstShiftStart));
  });
  root.querySelector("[data-ws-first-shift-cancel]")?.addEventListener("click", () => {
    wsState.firstShiftUserId = null;
    renderApp();
  });
  root.querySelectorAll("[data-ws-absence]").forEach((button) => {
    button.addEventListener("click", () => openWsAbsenceModal(button.dataset.wsUser, button.dataset.wsAbsence));
  });
  root.querySelector("[data-ws-fact-toggle]")?.addEventListener("click", () => {
    wsState.factEditing = !wsState.factEditing;
    renderApp();
  });
  root.querySelector("[data-ws-fact-cancel]")?.addEventListener("click", () => {
    wsState.factEditing = false;
    renderApp();
  });
  root.querySelector("[data-ws-fact-form]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    wsSaveFacts(event.currentTarget.dataset.wsFactForm);
  });
}
