(function () {
  function esc(value) {
    return window.escapeHtml ? window.escapeHtml(value) : String(value ?? "");
  }

  function formatDate(value) {
    if (!value) return "—";
    try {
      return new Date(value).toLocaleDateString("ru-RU", {
        day: "2-digit",
        month: "2-digit",
        year: "2-digit",
        timeZone: "Europe/Moscow",
      });
    } catch {
      return String(value);
    }
  }

  function formatDateTime(value) {
    if (!value) return "—";
    try {
      return new Date(value).toLocaleString("ru-RU", {
        day: "2-digit",
        month: "2-digit",
        year: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Europe/Moscow",
      });
    } catch {
      return String(value);
    }
  }

  function getTypeName(code) {
    const item = (window.data?.blanksTypes || []).find((entry) => entry.code === code);
    return item?.name || code;
  }

  function getStatusMeta(status) {
    const map = {
      free: { label: "Свободен", className: "free" },
      issued: { label: "Выдан", className: "issued" },
      spoiled: { label: "Испорчен", className: "spoiled" },
      cancelled: { label: "Аннулирован", className: "cancelled" },
    };
    return map[status] || { label: status || "—", className: "free" };
  }

  function normalizeText(value) {
    return String(value ?? "").trim().toLowerCase();
  }

  async function loadBlanksData(options = {}) {
    const force = options.force === true;
    const data = window.data;
    if (!data || data.blanksLoading) return;

    let centerId = null;
    try {
      centerId = await window.resolveWorkspaceCenterId?.();
    } catch (error) {
      data.blanksError = window.humanizeApiError
        ? window.humanizeApiError(error, "Не удалось определить текущий медцентр")
        : String(error?.message || error || "Не удалось определить текущий медцентр");
      if (window.appState?.page === "blanks") window.renderApp?.();
      return;
    }

    if (data.blanksLoaded && Number(data.blanksCenterId) === Number(centerId) && !force) return;

    data.blanksLoading = true;
    data.blanksError = "";
    if (window.appState?.page === "blanks") {
      window.renderApp?.();
    }

    try {
      const centerQuery = new URLSearchParams({ center_id: String(centerId) }).toString();
      const [types, stats, batches, forms] = await Promise.all([
        window.apiRequest("/blanks/types"),
        window.apiRequest(`/blanks/stats?${centerQuery}`),
        window.apiRequest(`/blanks/batches?${centerQuery}`),
        window.apiRequest(`/blanks/forms?limit=1000&${centerQuery}`),
      ]);

      data.blanksTypes = Array.isArray(types) ? types : [];
      data.blanksStats = Array.isArray(stats?.items) ? stats.items : [];
      data.blanksBatches = Array.isArray(batches) ? batches : [];
      data.blanksForms = Array.isArray(forms) ? forms : [];
      data.blanksLoaded = true;
      data.blanksCenterId = Number(centerId);

      const activeBatchIds = new Set(data.blanksBatches.map((item) => String(item.id)));
      if (!activeBatchIds.has(String(window.appState?.blanksFilterBatchId || ""))) {
        window.appState.blanksFilterBatchId = "all";
      }
    } catch (error) {
      data.blanksError = window.humanizeApiError
        ? window.humanizeApiError(error, "Не удалось загрузить номерные бланки")
        : String(error?.message || error || "Не удалось загрузить номерные бланки");
    } finally {
      data.blanksLoading = false;
      if (window.appState?.page === "blanks") {
        window.renderApp?.();
      }
    }
  }

  function renderOverviewTab() {
    const items = Array.isArray(window.data?.blanksStats) ? window.data.blanksStats : [];
    if (!items.length) {
      return '<p class="muted">Пока нет партий бланков. Добавьте первую партию на вкладке «Партии».</p>';
    }

    return `
      <div class="stats-grid">
        ${items
          .map(
            (item) => `
              <article class="stat-card">
                <strong>${esc(item.blank_type_name || item.blank_type)}</strong>
                <span>Всего: ${Number(item.total || 0)}</span>
                <span>Свободно: ${Number(item.free || 0)}</span>
                <span>Выдано: ${Number(item.issued || 0)}</span>
                <span>Испорчено: ${Number(item.spoiled || 0)}</span>
                <span>Аннулировано: ${Number(item.cancelled || 0)}</span>
              </article>
            `,
          )
          .join("")}
      </div>
    `;
  }

  function renderBatchesTab() {
    const data = window.data || {};
    const appState = window.appState || {};
    const batches = Array.isArray(data.blanksBatches) ? data.blanksBatches : [];
    const typeOptions = Array.isArray(data.blanksTypes) ? data.blanksTypes : [];
    const centerName = window.getWorkspaceCenterName?.() || appState.centerFilter || "Медцентр";

    return `
      ${
        appState.blanksFormOpen
          ? `
            <form class="card blanks-batch-form" id="blanksBatchForm">
              <h3>Добавить диапазон номеров — ${esc(centerName)}</h3>
              <p class="muted">Диапазон будет принадлежать только выбранному медцентру. Укажите серию и первый с последним номером.</p>
              <div class="visit-form__grid">
                <label class="field">
                  <span>Тип бланка</span>
                  <select name="blank_type" required>
                    ${typeOptions.map((item) => `<option value="${esc(item.code)}">${esc(item.name)}</option>`).join("")}
                  </select>
                </label>
                <label class="field">
                  <span>Серия</span>
                  <input name="series" placeholder="АА" />
                </label>
                <label class="field">
                  <span>Номер с</span>
                  <input name="number_from" required placeholder="000001" />
                </label>
                <label class="field">
                  <span>Номер по</span>
                  <input name="number_to" required placeholder="000010" />
                </label>
                <label class="field">
                  <span>Дата получения</span>
                  <input type="date" name="received_at" />
                </label>
                <label class="field visit-form__wide">
                  <span>Комментарий</span>
                  <input name="comment" placeholder="Источник, примечание" />
                </label>
              </div>
              ${
                data.blanksFormError
                  ? `<div class="form-error">${esc(data.blanksFormError)}</div>`
                  : ""
              }
              <div class="visit-form__actions">
                <button type="button" class="ghost-button" data-blanks-close-form>Отмена</button>
                <button type="submit" class="primary-button">${data.blanksFormSaving ? "Добавление..." : "Добавить номера"}</button>
              </div>
            </form>
          `
          : ""
      }
      <article class="card">
        <h3>Партии бланков</h3>
        ${
          batches.length
            ? `
              <div class="data-table">
                <table>
                  <thead>
                    <tr>
                      <th>Дата</th>
                      <th>Тип</th>
                      <th>Серия</th>
                      <th>Диапазон</th>
                      <th>Кол-во</th>
                      <th>Своб.</th>
                      <th>Выдано</th>
                      <th>Испорч.</th>
                      <th>Аннул.</th>
                      <th>Комментарий</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${batches
                      .map(
                        (item) => `
                          <tr>
                            <td>${esc(formatDate(item.received_at || item.created_at))}</td>
                            <td>${esc(getTypeName(item.blank_type))}</td>
                            <td>${esc(item.series || "—")}</td>
                            <td>${esc(item.series || "")}${String(item.number_from).padStart(item.number_width || 6, "0")}–${esc(item.series || "")}${String(item.number_to).padStart(item.number_width || 6, "0")}</td>
                            <td>${Number(item.quantity || 0)}</td>
                            <td>${Number(item.free_count || 0)}</td>
                            <td>${Number(item.issued_count || 0)}</td>
                            <td>${Number(item.spoiled_count || 0)}</td>
                            <td>${Number(item.cancelled_count || 0)}</td>
                            <td>${esc(item.comment || "—")}</td>
                          </tr>
                        `,
                      )
                      .join("")}
                  </tbody>
                </table>
              </div>
            `
            : '<p class="muted">Партий пока нет.</p>'
        }
      </article>
    `;
  }

  function getFilteredForms() {
    const forms = Array.isArray(window.data?.blanksForms) ? window.data.blanksForms : [];
    const status = window.appState?.blanksFilterStatus || "all";
    const batchId = window.appState?.blanksFilterBatchId || "all";
    const search = normalizeText(window.appState?.blanksSearch || "");

    return forms.filter((item) => {
      if (status !== "all" && item.status !== status) return false;
      if (batchId !== "all" && String(item.batch_id) !== String(batchId)) return false;
      if (!search) return true;

      const haystack = [
        item.full_number,
        item.client_full_name,
        item.document_label,
        item.issued_by_name,
        item.spoiled_reason,
      ]
        .map(normalizeText)
        .join(" ");
      return haystack.includes(search);
    });
  }

  function getIssuedHistoryGroups() {
    const forms = Array.isArray(window.data?.blanksForms) ? window.data.blanksForms : [];
    const types = Array.isArray(window.data?.blanksTypes) ? window.data.blanksTypes : [];
    const search = normalizeText(window.appState?.blanksHistorySearch || "");
    const issuedForms = forms
      .filter((item) => item.status === "issued")
      .filter((item) => !search || normalizeText(item.full_number).includes(search))
      .sort((left, right) => {
        const leftTime = new Date(left.issued_at || 0).getTime();
        const rightTime = new Date(right.issued_at || 0).getTime();
        return rightTime - leftTime || Number(right.id || 0) - Number(left.id || 0);
      });

    const typeCodes = new Set(types.map((item) => item.code));
    const groups = types.map((item) => ({
      code: item.code,
      name: item.name,
      items: issuedForms.filter((form) => form.blank_type === item.code),
    }));

    issuedForms.forEach((form) => {
      if (typeCodes.has(form.blank_type)) return;
      typeCodes.add(form.blank_type);
      groups.push({
        code: form.blank_type,
        name: getTypeName(form.blank_type),
        items: issuedForms.filter((item) => item.blank_type === form.blank_type),
      });
    });

    return groups;
  }

  function renderHistoryTab() {
    const appState = window.appState || {};
    const groups = getIssuedHistoryGroups();
    const visibleCount = groups.reduce((total, group) => total + group.items.length, 0);
    const hasSearch = Boolean(normalizeText(appState.blanksHistorySearch || ""));
    const visibleGroups = hasSearch ? groups.filter((group) => group.items.length) : groups;

    return `
      <article class="card blanks-history">
        <div class="blanks-page__header">
          <div>
            <h3>История выданных документов</h3>
            <p class="muted">Все выданные номерные бланки сгруппированы по услугам.</p>
          </div>
          <span class="blanks-history__total">Найдено: ${visibleCount}</span>
        </div>
        <label class="field blanks-history__search">
          <span>Поиск по номеру</span>
          <input
            type="search"
            data-blanks-history-search
            value="${esc(appState.blanksHistorySearch || "")}"
            placeholder="Введите номер бланка"
            autocomplete="off"
          />
        </label>
        <div class="blanks-history__groups">
          ${
            visibleGroups.length
              ? visibleGroups
                  .map(
                    (group) => `
                <section class="blanks-history-group" data-blank-history-group="${esc(group.code)}">
                  <div class="blanks-history-group__header">
                    <h4>${esc(group.name)}</h4>
                    <span>${group.items.length}</span>
                  </div>
                  ${
                    group.items.length
                      ? `
                        <div class="data-table">
                          <table>
                            <thead>
                              <tr>
                                <th>Номер</th>
                                <th>Пациент</th>
                                <th>Документ</th>
                                <th>Дата выдачи</th>
                                <th>Кто выдал</th>
                              </tr>
                            </thead>
                            <tbody>
                              ${group.items
                                .map(
                                  (item) => `
                                    <tr>
                                      <td><strong>${esc(item.full_number)}</strong></td>
                                      <td>${esc(item.client_full_name || "—")}</td>
                                      <td>${esc(item.document_label || "—")}</td>
                                      <td>${esc(formatDateTime(item.issued_at))}</td>
                                      <td>${esc(item.issued_by_name || "—")}</td>
                                    </tr>
                                  `,
                                )
                                .join("")}
                            </tbody>
                          </table>
                        </div>
                      `
                      : `<p class="muted blanks-history-group__empty">${
                          hasSearch ? "Документы с таким номером не найдены." : "Выданных документов пока нет."
                        }</p>`
                  }
                </section>
              `,
                  )
                  .join("")
              : '<p class="muted blanks-history__empty">Документ с таким номером не найден.</p>'
          }
        </div>
      </article>
    `;
  }

  function renderFormsTab() {
    const data = window.data || {};
    const appState = window.appState || {};
    const forms = getFilteredForms();
    const batches = Array.isArray(data.blanksBatches) ? data.blanksBatches : [];

    return `
      <article class="card">
        <div class="blanks-page__header">
          <div>
            <h3>Номера бланков</h3>
            <p class="muted">Чтобы вернуть ошибочно занятый номер, откройте выданные бланки.</p>
          </div>
          <button type="button" class="primary-button" data-blanks-show-issued>Освободить выданный номер</button>
        </div>
        <div class="blanks-filters">
          <label class="field">
            <span>Статус</span>
            <select data-blanks-filter-status>
              <option value="all" ${appState.blanksFilterStatus === "all" ? "selected" : ""}>Все</option>
              <option value="free" ${appState.blanksFilterStatus === "free" ? "selected" : ""}>Свободные</option>
              <option value="issued" ${appState.blanksFilterStatus === "issued" ? "selected" : ""}>Выданные</option>
              <option value="spoiled" ${appState.blanksFilterStatus === "spoiled" ? "selected" : ""}>Испорченные</option>
              <option value="cancelled" ${appState.blanksFilterStatus === "cancelled" ? "selected" : ""}>Аннулированные</option>
            </select>
          </label>
          <label class="field">
            <span>Партия</span>
            <select data-blanks-filter-batch>
              <option value="all">Все партии</option>
              ${batches
                .map(
                  (item) => `
                    <option value="${item.id}" ${String(appState.blanksFilterBatchId) === String(item.id) ? "selected" : ""}>
                      ${esc(item.series || "")}${String(item.number_from).padStart(item.number_width || 6, "0")}–${esc(item.series || "")}${String(item.number_to).padStart(item.number_width || 6, "0")}
                    </option>
                  `,
                )
                .join("")}
            </select>
          </label>
          <label class="field blanks-filters__search">
            <span>Поиск</span>
            <input data-blanks-search value="${esc(appState.blanksSearch || "")}" placeholder="Номер, клиент, документ" />
          </label>
        </div>
        ${
          forms.length
            ? `
              <div class="data-table">
                <table>
                  <thead>
                    <tr>
                      <th>Номер</th>
                      <th>Статус</th>
                      <th>Клиент</th>
                      <th>Документ</th>
                      <th>Дата выдачи</th>
                      <th>Кто выдал</th>
                      <th>Причина</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    ${forms
                      .map((item) => {
                        const meta = getStatusMeta(item.status);
                        return `
                          <tr>
                            <td>${esc(item.full_number)}</td>
                            <td><span class="blank-status blank-status--${meta.className}">${esc(meta.label)}</span></td>
                            <td>${esc(item.client_full_name || "—")}</td>
                            <td>${esc(item.document_label || "—")}</td>
                            <td>${esc(formatDateTime(item.issued_at))}</td>
                            <td>${esc(item.issued_by_name || "—")}</td>
                            <td>${esc(item.spoiled_reason || item.cancelled_reason || "—")}</td>
                            <td>
                              ${
                                item.status === "free"
                                  ? `<button type="button" class="ghost-button" data-blank-spoil="${item.id}">Испорчен</button>`
                                  : item.status === "issued"
                                    ? `<button type="button" class="ghost-button" data-blank-release="${item.id}" data-blank-number="${esc(item.full_number)}">Освободить номер</button>`
                                  : ""
                              }
                            </td>
                          </tr>
                        `;
                      })
                      .join("")}
                  </tbody>
                </table>
              </div>
            `
            : '<p class="muted">По текущим фильтрам бланков не найдено.</p>'
        }
      </article>
    `;
  }

  function renderActiveTab() {
    const tab = window.appState?.blanksTab || "overview";
    if (tab === "batches") return renderBatchesTab();
    if (tab === "forms") return renderFormsTab();
    if (tab === "history") return renderHistoryTab();
    return renderOverviewTab();
  }

  function renderBlanksPage() {
    const data = window.data || {};
    const appState = window.appState || {};
    const centerName = window.getWorkspaceCenterName?.() || appState.centerFilter || "Медцентр";

    return `
      <section class="card">
        <div class="blanks-page__header">
          <div>
            <h3>Бланки</h3>
            <p class="blanks-page__center">${esc(centerName)}</p>
            <p class="muted">Показаны только диапазоны и номера выбранного медцентра.</p>
          </div>
          <div class="blanks-page__actions">
            <button type="button" class="primary-button" data-blanks-add-numbers ${appState.blanksFormOpen ? "disabled" : ""}>
              ${appState.blanksFormOpen ? "Форма открыта" : "Добавить номера"}
            </button>
            <button type="button" class="ghost-button" data-blanks-refresh>Обновить</button>
          </div>
        </div>
        <div class="tabs">
          <button type="button" class="tabs__item ${appState.blanksTab === "overview" ? "tabs__item--active" : ""}" data-blanks-tab="overview">Обзор</button>
          <button type="button" class="tabs__item ${appState.blanksTab === "history" ? "tabs__item--active" : ""}" data-blanks-tab="history">История выдачи</button>
          <button type="button" class="tabs__item ${appState.blanksTab === "batches" ? "tabs__item--active" : ""}" data-blanks-tab="batches">Партии</button>
          <button type="button" class="tabs__item ${appState.blanksTab === "forms" ? "tabs__item--active" : ""}" data-blanks-tab="forms">Номера бланков</button>
        </div>
        ${data.blanksError ? `<div class="form-error">${esc(data.blanksError)}</div>` : ""}
        ${data.blanksLoading && !data.blanksLoaded ? '<p class="muted">Загрузка данных по бланкам...</p>' : renderActiveTab()}
      </section>
    `;
  }

  function bindBlanksHandlers() {
    if (window.appState?.page !== "blanks") return;

    document.querySelectorAll("[data-blanks-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        window.appState.blanksTab = button.dataset.blanksTab || "overview";
        window.persistDemoState?.();
        window.renderApp?.();
      });
    });

    document.querySelector("[data-blanks-refresh]")?.addEventListener("click", () => {
      loadBlanksData({ force: true });
    });

    document.querySelector("[data-blanks-add-numbers]")?.addEventListener("click", () => {
      window.appState.blanksTab = "batches";
      window.appState.blanksFormOpen = true;
      window.data.blanksFormError = "";
      window.persistDemoState?.();
      window.renderApp?.();
      window.requestAnimationFrame(() => {
        document.querySelector("#blanksBatchForm select, #blanksBatchForm input")?.focus();
      });
    });

    document.querySelector("[data-blanks-show-issued]")?.addEventListener("click", () => {
      window.appState.blanksFilterStatus = "issued";
      window.appState.blanksSearch = "";
      window.persistDemoState?.();
      window.renderApp?.();
      window.showToast?.("Выберите нужный номер и нажмите «Освободить номер» в его строке");
    });

    document.querySelector("[data-blanks-close-form]")?.addEventListener("click", () => {
      window.appState.blanksFormOpen = false;
      window.data.blanksFormError = "";
      window.persistDemoState?.();
      window.renderApp?.();
    });

    document.querySelector("[data-blanks-filter-status]")?.addEventListener("change", (event) => {
      window.appState.blanksFilterStatus = event.target.value || "all";
      window.persistDemoState?.();
      window.renderApp?.();
    });

    document.querySelector("[data-blanks-filter-batch]")?.addEventListener("change", (event) => {
      window.appState.blanksFilterBatchId = event.target.value || "all";
      window.persistDemoState?.();
      window.renderApp?.();
    });

    document.querySelector("[data-blanks-search]")?.addEventListener("input", (event) => {
      window.appState.blanksSearch = event.target.value || "";
      window.persistDemoState?.();
      window.renderApp?.();
    });

    document.querySelector("[data-blanks-history-search]")?.addEventListener("input", (event) => {
      window.appState.blanksHistorySearch = event.target.value || "";
      window.renderApp?.();
      const searchInput = document.querySelector("[data-blanks-history-search]");
      if (searchInput) {
        searchInput.focus();
        searchInput.setSelectionRange(searchInput.value.length, searchInput.value.length);
      }
    });

    document.getElementById("blanksBatchForm")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const formData = new FormData(form);

      window.data.blanksFormSaving = true;
      window.data.blanksFormError = "";
      window.renderApp?.();

      try {
        const centerId = await window.resolveWorkspaceCenterId?.();
        await window.apiRequest("/blanks/batches", {
          method: "POST",
          body: JSON.stringify({
            blank_type: formData.get("blank_type"),
            center_id: Number(centerId),
            series: String(formData.get("series") || "").trim() || null,
            number_from: String(formData.get("number_from") || "").trim(),
            number_to: String(formData.get("number_to") || "").trim(),
            received_at: String(formData.get("received_at") || "").trim() || null,
            comment: String(formData.get("comment") || "").trim() || null,
          }),
        });
        window.appState.blanksFormOpen = false;
        window.persistDemoState?.();
        window.showToast?.("Партия бланков добавлена");
        await loadBlanksData({ force: true });
      } catch (error) {
        window.data.blanksFormError = window.humanizeApiError
          ? window.humanizeApiError(error, "Не удалось добавить партию")
          : String(error?.message || error || "Не удалось добавить партию");
        window.renderApp?.();
      } finally {
        window.data.blanksFormSaving = false;
        if (window.appState?.page === "blanks") {
          window.renderApp?.();
        }
      }
    });

    document.querySelectorAll("[data-blank-spoil]").forEach((button) => {
      button.addEventListener("click", async () => {
        const formId = button.dataset.blankSpoil;
        if (!formId) return;
        const reason = window.prompt("Укажите причину порчи бланка", "Испорчен при заполнении");
        if (reason === null) return;

        try {
          await window.apiRequest(`/blanks/forms/${encodeURIComponent(formId)}/spoil`, {
            method: "POST",
            body: JSON.stringify({ reason }),
          });
          window.showToast?.("Бланк отмечен как испорченный");
          await loadBlanksData({ force: true });
        } catch (error) {
          window.showToast?.(
            window.humanizeApiError
              ? window.humanizeApiError(error, "Не удалось изменить статус бланка")
              : String(error?.message || error || "Не удалось изменить статус бланка"),
          );
        }
      });
    });

    document.querySelectorAll("[data-blank-release]").forEach((button) => {
      button.addEventListener("click", async () => {
        const formId = button.dataset.blankRelease;
        const blankNumber = button.dataset.blankNumber || "";
        if (!formId) return;
        const confirmed = window.confirm(
          `Освободить номер ${blankNumber}?\n\nИспользуйте это действие, только если документ не был напечатан. Номер снова будет доступен следующему пациенту.`,
        );
        if (!confirmed) return;

        button.disabled = true;
        try {
          await window.apiRequest(`/blanks/forms/${encodeURIComponent(formId)}/release`, {
            method: "POST",
          });
          window.showToast?.(`Номер ${blankNumber} освобождён`);
          await loadBlanksData({ force: true });
        } catch (error) {
          button.disabled = false;
          window.showToast?.(
            window.humanizeApiError
              ? window.humanizeApiError(error, "Не удалось освободить номер")
              : String(error?.message || error || "Не удалось освободить номер"),
          );
        }
      });
    });
  }

  window.loadBlanksData = loadBlanksData;
  window.renderBlanksPage = renderBlanksPage;
  window.bindBlanksHandlers = bindBlanksHandlers;
})();
