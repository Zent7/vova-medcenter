// Журнал изменений графика и ставок сотрудников: страница только для админа. Записи пишет сервер
// (audit_logs, entity_type «staff_schedule»), здесь они читаются через /audit-logs и показываются
// таблицей с фильтрами по сотруднику и действию.
//
// Файл грузится после work-schedule.js: из него берется wsEscape. Из app.js берутся apiRequest,
// humanizeApiError, renderApp и appState. app.js вызывает renderJournalContent (страница),
// bindAuditJournalEvents (после каждой перерисовки), loadAuditJournal (вход в раздел) и
// resetAuditJournal (выход из программы). Скрытый пункт меню защитой не считается: сервер
// отдает журнал только админу и сам отвечает 403 остальным.

const AJ_ENTITY = "staff_schedule";
const AJ_LIMIT = 500;
const AJ_TIME_ZONE = "Europe/Moscow";
// Подписи действий; порядок ключей — порядок пунктов в фильтре «Действие».
const AJ_ACTIONS = {
  schedule_create: "График создан",
  schedule_update: "График изменен",
  rate_update: "Ставка изменена",
  month_generate: "График на месяц создан",
  first_shift: "Первая смена назначена",
  day_update: "День изменен",
  day_clear: "День очищен",
  absence_add: "Отпуск или больничный",
  facts_update: "Факт изменен",
  staff_delete: "Учетная запись удалена",
};
const AJ_KIND_LABELS = { shift: "смена", dayoff: "отгул", sick: "больничный", vacation: "отпуск" };

function canViewAuditJournal() {
  return appState.auth.roleCode === "admin";
}

function ajInitialState() {
  return { entries: null, loading: false, error: "", requestId: 0, staffFilter: "", actionFilter: "" };
}

const ajState = ajInitialState();

// Выход из программы: отбрасываем ответ, который еще летит от прошлого сеанса.
function resetAuditJournal() {
  const requestId = ajState.requestId + 1;
  Object.assign(ajState, ajInitialState(), { requestId });
}

// Время записи по Москве: «06.11.2026 23:57». Сервер отдает время с поясом; без пояса считаем UTC.
function ajFormatWhen(value) {
  const text = String(value ?? "");
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(text);
  const date = new Date(hasZone ? text : `${text}Z`);
  if (!text || Number.isNaN(date.getTime())) return text;
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: AJ_TIME_ZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(date)
      .map((part) => [part.type, part.value]),
  );
  return `${parts.day}.${parts.month}.${parts.year} ${parts.hour}:${parts.minute}`;
}

// «2026-11-05» -> «05.11.2026».
function ajDate(iso) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso ?? ""));
  return match ? `${match[3]}.${match[2]}.${match[1]}` : String(iso ?? "");
}

function ajRate(value) {
  return value === null || value === undefined ? "не задана" : `${value} ₽/ч`;
}

// День как в таблице графика: «смена 09:00-20:00», «отгул», «пусто».
function ajDayText(day) {
  if (!day) return "пусто";
  if (day.kind === "shift" && day.start && day.end) return `смена ${day.start}-${day.end}`;
  return AJ_KIND_LABELS[day.kind] || String(day.kind ?? "");
}

// Что именно изменили, одной строкой без разметки: экранируется при выводе. Если запись относится к медцентру,
// его название идет первым: «Медилэнд · 05.11.2026: смена 09:00-20:00 → отгул».
function ajDescribe(entry) {
  const payload = entry.payload_json || {};
  const text = ajDescribeChange(entry.action, payload);
  const center = typeof payload.center === "string" ? payload.center.trim() : "";
  if (!center) return text;
  return text ? `${center} · ${text}` : center;
}

function ajDescribeChange(action, payload) {
  switch (action) {
    case "schedule_create":
      return `${payload.schedule || "без графика"}, ставка ${ajRate(payload.hourly_rate)}`;
    case "schedule_update":
      return `${payload.before || "без графика"} → ${payload.after || "без графика"}`;
    case "rate_update":
      return `${ajRate(payload.before)} → ${ajRate(payload.after)}`;
    case "month_generate":
      return `за ${String(payload.month ?? "").padStart(2, "0")}.${payload.year ?? ""}, создано смен: ${payload.created ?? 0}`;
    case "first_shift": {
      const was = payload.anchor_before ? `, было ${ajDate(payload.anchor_before)}` : "";
      return `${ajDate(payload.work_date)}${was}, создано смен: ${payload.created ?? 0}`;
    }
    case "day_update":
      return `${ajDate(payload.date)}: ${ajDayText(payload.before)} → ${ajDayText(payload.after)}`;
    case "day_clear":
      return `${ajDate(payload.date)}: был ${ajDayText(payload.before)}, стало пусто`;
    case "absence_add":
      return `${AJ_KIND_LABELS[payload.kind] || payload.kind || ""} с ${ajDate(payload.from)} по ${ajDate(payload.to)}, дней изменено: ${payload.days ?? 0}`;
    case "facts_update": {
      const items = Array.isArray(payload.items) ? payload.items : [];
      return items
        .map((item) => `${ajDate(item.date)}: ${item.before || "по отметкам"} → ${item.after || "по отметкам"}`)
        .join("; ");
    }
    case "staff_delete":
      return `${payload.schedule ? `был график ${payload.schedule}, ` : ""}ставка ${ajRate(payload.hourly_rate)}`;
    default:
      return "";
  }
}

// Имя сотрудника: из учетки, а если ее стерли, из самой записи (это делает сервер).
function ajStaffLabel(entry) {
  return entry.entity_name || `Сотрудник #${entry.entity_id}`;
}

function ajStaffNames(entries) {
  return [...new Set(entries.map(ajStaffLabel))].sort((left, right) => left.localeCompare("ru"));
}

function ajFilteredEntries() {
  const entries = ajState.entries || [];
  return entries.filter(
    (entry) =>
      (!ajState.staffFilter || ajStaffLabel(entry) === ajState.staffFilter) &&
      (!ajState.actionFilter || entry.action === ajState.actionFilter),
  );
}

// Загрузка. Каждый запрос получает номер: отвечает только последний.
async function loadAuditJournal() {
  const requestId = ++ajState.requestId;
  ajState.loading = true;
  ajState.error = "";
  renderApp();
  try {
    const entries = await apiRequest(`/audit-logs?entity_type=${AJ_ENTITY}&limit=${AJ_LIMIT}`);
    if (requestId !== ajState.requestId) return;
    ajState.entries = Array.isArray(entries) ? entries : [];
  } catch (error) {
    if (requestId !== ajState.requestId) return;
    ajState.error = humanizeApiError(error, "Не удалось загрузить журнал");
  } finally {
    if (requestId === ajState.requestId) {
      ajState.loading = false;
      renderApp();
    }
  }
}

function renderJournalContent() {
  const entries = ajState.entries;
  const filtered = entries ? ajFilteredEntries() : [];
  const filtersOn = Boolean(ajState.staffFilter || ajState.actionFilter);

  let body;
  if (!entries) {
    body = `<div class="empty">${ajState.loading ? "Загружаем журнал..." : "Журнал пока не загружен."}</div>`;
  } else if (!filtered.length) {
    body = `<div class="empty">${filtersOn ? "По выбранным фильтрам записей нет." : "Записей пока нет."}</div>`;
  } else {
    body = `
      <div class="data-table aj__table">
        <table>
          <thead>
            <tr><th>Когда</th><th>Кто изменил</th><th>Сотрудник</th><th>Что изменено</th></tr>
          </thead>
          <tbody>
            ${filtered
              .map(
                (entry) => `
                  <tr>
                    <td>${wsEscape(ajFormatWhen(entry.created_at))}</td>
                    <td>${wsEscape(entry.user_name || "—")}</td>
                    <td>${wsEscape(ajStaffLabel(entry))}</td>
                    <td>
                      <strong>${wsEscape(AJ_ACTIONS[entry.action] || entry.action)}</strong>
                      <div class="muted">${wsEscape(ajDescribe(entry))}</div>
                    </td>
                  </tr>`,
              )
              .join("")}
          </tbody>
        </table>
      </div>`;
  }

  const filters = entries
    ? `
      <div class="toolbar">
        <label class="field">
          <span>Сотрудник</span>
          <select data-aj-staff>
            <option value="">Все сотрудники</option>
            ${ajStaffNames(entries)
              .map(
                (name) =>
                  `<option value="${wsEscape(name)}"${name === ajState.staffFilter ? " selected" : ""}>${wsEscape(name)}</option>`,
              )
              .join("")}
          </select>
        </label>
        <label class="field">
          <span>Действие</span>
          <select data-aj-action>
            <option value="">Все действия</option>
            ${Object.entries(AJ_ACTIONS)
              .map(
                ([action, label]) =>
                  `<option value="${action}"${action === ajState.actionFilter ? " selected" : ""}>${wsEscape(label)}</option>`,
              )
              .join("")}
          </select>
        </label>
      </div>
      <p class="muted aj__count">Записей: ${filtered.length}${entries.length >= AJ_LIMIT ? `, показаны последние ${AJ_LIMIT}` : ""}</p>`
    : "";

  return `
    <section class="card aj" data-audit-journal>
      <div class="aj__head">
        <div>
          <h3>Журнал изменений</h3>
          <p class="muted">Кто и когда менял график, время смены, ставку и дни сотрудников. Записи видит только админ.</p>
        </div>
        <button class="ghost-button" type="button" data-aj-refresh ${ajState.loading ? "disabled" : ""}>Обновить</button>
      </div>
      ${filters}
      ${ajState.error ? `<div class="note employee-note employee-note--error">${wsEscape(ajState.error)}</div>` : ""}
      ${body}
    </section>`;
}

function bindAuditJournalEvents() {
  const root = document.querySelector("[data-audit-journal]");
  if (!root) return;
  root.querySelector("[data-aj-refresh]")?.addEventListener("click", () => loadAuditJournal());
  root.querySelector("[data-aj-staff]")?.addEventListener("change", (event) => {
    ajState.staffFilter = event.currentTarget.value;
    renderApp();
  });
  root.querySelector("[data-aj-action]")?.addEventListener("change", (event) => {
    ajState.actionFilter = event.currentTarget.value;
    renderApp();
  });
}
