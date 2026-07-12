// Маршрутизатор карточек услуг и реализация спортивной карточки.
// Зависит от: window.apiRequest, window.humanizeApiError, window.showToast,
// window.escapeHtml, window.appState, window.data, window.persistDemoState,
// window.openDoctorExamCard, window.getDoctorTemplate, window.getDoctorExam,
// window.saveDoctorExam, window.deleteDoctorExam, window.getOrCreateDraftVisit.
(function () {
  const SPORT_CARD_ROLE_ID = "service_card_sport";
  const SPORT_PHRASES_CODE = "sport_conclusion";

  function esc(value) {
    return (window.escapeHtml || String)(value);
  }

  const AUTO_EKG_CONCLUSION_PREFIX =
    "Ритм синусовый, ЧСС , нормальная электрическая позиция сердца, ЭКГ-комплексы без особенностей";

  function extractRuDate(value) {
    return String(value ?? "").match(/\b\d{2}\.\d{2}\.(?:\d{2}|\d{4})\b/)?.[0] || "";
  }

  function todayRuDate() {
    return new Date().toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "2-digit",
    });
  }

  function buildAutoEkgConclusion(date) {
    const finalDate = extractRuDate(date) || todayRuDate();
    return `${AUTO_EKG_CONCLUSION_PREFIX} от ${finalDate}`;
  }

  function isAutoEkgConclusion(value) {
    return String(value ?? "").trim().startsWith(`${AUTO_EKG_CONCLUSION_PREFIX} от `);
  }

  function getFirstNamedControl(elements) {
    if (!elements) return null;
    if (elements.length && elements.tagName === undefined) return elements[0] || null;
    return elements;
  }

  // ----- Определение типа карточки по услуге --------------------------------
  // driver — открывается уже существующая карточка председателя.
  // sport/pool/GTO — открываются в общей карточке председателя.
  // прочее — placeholder.
  // Жёсткий whitelist: только для согласованных услуг — своя карточка.
  // Все остальные услуги показывают плейсхолдер «Карточка пока не готова».
  const DRIVER_LEGACY_IDS = new Set([8, 29]);
  const PROF_LEGACY_IDS = new Set([16]);
  const SPORT_LEGACY_IDS = new Set([3, 4, 5]);
  const EKG_LEGACY_IDS = new Set([6, 20, 21, 27]);

  function resolveServiceCardKind(service) {
    if (!service) return "placeholder";
    const legacyId = Number(service.legacySourceId || service.legacy_source_id || 0);
    const name = String(service.name || "").trim().toLowerCase();

    if (DRIVER_LEGACY_IDS.has(legacyId)) return "driver";
    if (
      name === "водительская справка" ||
      name === "медицинская комиссия для водительского удостоверения" ||
      name === "медкомиссия для водительского удостоверения" ||
      name === "медицинское заключение для водительского удостоверения"
    ) {
      return "driver";
    }

    if (PROF_LEGACY_IDS.has(legacyId) || name.includes("профосмотр") || name.includes("29н")) {
      return "prof";
    }

    if (SPORT_LEGACY_IDS.has(legacyId)) return "sport";
    if (
      name === "справка в бассейн" ||
      name === "справка гто 1144" ||
      name === "справка гто" ||
      name === "справка для участия в соревнованиях" ||
      name === "справка спорт + экг" ||
      name === "справка для спорта" ||
      name === "спортивная справка"
    ) {
      return "sport";
    }

    if (EKG_LEGACY_IDS.has(legacyId) || (name.includes("\u044d\u043a\u0433") && !name.includes("\u0441\u043f\u043e\u0440\u0442"))) {
      return "ekg";
    }

    return "placeholder";
  }

  function findServiceById(serviceId) {
    if (typeof window.getServiceById === "function") {
      const service = window.getServiceById(serviceId);
      if (service) return service;
    }
    const services = window.data?.serverServices || [];
    return services.find(
      (item) =>
        String(item.id) === String(serviceId) ||
        String(item.backendId) === String(serviceId),
    ) || null;
  }

  function openServiceCard(serviceId) {
    const service = findServiceById(serviceId);
    if (!service) {
      (window.showToast || console.warn)("Услуга не найдена");
      return;
    }
    const client = (window.getSelectedClient && window.getSelectedClient()) || null;
    if (!client) {
      window.showToast && window.showToast("Сначала выберите клиента");
      return;
    }
    const visit = window.getOrCreateDraftVisit && window.getOrCreateDraftVisit(client.id);

    const kind = resolveServiceCardKind(service);
    if (kind === "driver" || kind === "prof" || kind === "chairman" || kind === "sport") {
      closeServiceCardOverlays();
      window.openDoctorExamCard({
        clientId: client.id,
        visitId: visit?.id || null,
        doctorRoleId: "chairman",
      });
      return;
    }
    if (kind === "ekg") {
      openSportCard({ clientId: client.id, visitId: visit?.id || null, service, doctorRoleId: "chairman" });
      return;
    }
    openServicePlaceholder(service);
  }

  function closeServiceCardOverlays() {
    const data = window.data;
    if (data?.sportCard) {
      data.sportCard.isOpen = false;
      data.sportCard.phrasePicker = null;
    }
    if (data?.servicePlaceholder) {
      data.servicePlaceholder.isOpen = false;
    }
  }

  // ----- Спортивная карточка -----------------------------------------------
  function ensureSportState() {
    const data = window.data;
    if (!data.sportCard) {
      data.sportCard = {
        isOpen: false,
        clientId: null,
        visitId: null,
        serviceId: null,
        examId: null,
        phrasePicker: null, // { isOpen, search, selected, items }
      };
    }
    if (!Array.isArray(data.sportPhrases)) data.sportPhrases = [];
    return data.sportCard;
  }

  function openSportCard({ clientId, visitId, service, doctorRoleId = SPORT_CARD_ROLE_ID }) {
    closeServiceCardOverlays();
    const state = ensureSportState();
    const roleId = doctorRoleId || SPORT_CARD_ROLE_ID;
    if (typeof window.getOrCreateDoctorExam === "function") {
      // Через существующий механизм doctor_exams. У doctor_role_id нет FK.
      const exam = window.getOrCreateDoctorExam(clientId, visitId, roleId);
      if (exam) state.examId = exam.id;
    }
    state.isOpen = true;
    state.clientId = clientId;
    state.visitId = visitId;
    state.serviceId = service?.id || service?.backendId || null;
    state.serviceName = service?.name || "Спортивная справка";
    state.doctorRoleId = roleId;
    state.phrasePicker = null;

    // Подгружаем справочник фраз (если ещё не загружены — загружаем).
    if (!window.data.sportPhrasesLoaded) {
      loadSportPhrases();
    }
    window.renderApp();
  }

  function closeSportCard() {
    const state = ensureSportState();
    state.isOpen = false;
    state.clientId = null;
    state.visitId = null;
    state.examId = null;
    state.doctorRoleId = null;
    state.phrasePicker = null;
    window.renderApp();
  }

  // ----- Загрузка / обновление справочника фраз -----------------------------
  async function loadSportPhrases() {
    try {
      const items = await window.apiRequest(
        `/template-phrases?code=${encodeURIComponent(SPORT_PHRASES_CODE)}`,
      );
      window.data.sportPhrases = Array.isArray(items) ? items : [];
      window.data.sportPhrasesLoaded = true;
      window.renderApp();
    } catch (error) {
      // Молча, на фронте оставим пустой список — кнопка "+" сможет создать первую.
      window.data.sportPhrases = window.data.sportPhrases || [];
      console.warn("Не удалось загрузить фразы спортивной справки", error);
    }
  }

  async function createSportPhrase(text) {
    const trimmed = String(text || "").trim();
    if (!trimmed) return null;
    // Проверка дубликата на фронте — даст быстрый отклик.
    const existing = (window.data.sportPhrases || []).find(
      (item) => String(item.text || item.name || "").trim() === trimmed,
    );
    if (existing) return existing;
    try {
      const created = await window.apiRequest(`/template-phrases`, {
        method: "POST",
        body: JSON.stringify({
          code: SPORT_PHRASES_CODE,
          name: trimmed.length > 100 ? trimmed.slice(0, 100) : trimmed,
          text: trimmed,
          is_default: false,
          is_active: true,
        }),
      });
      window.data.sportPhrases = (window.data.sportPhrases || []).concat([created]);
      return created;
    } catch (error) {
      window.showToast && window.showToast(
        window.humanizeApiError(error, "Не удалось добавить фразу в справочник"),
      );
      return null;
    }
  }

  // ----- Пикер фраз --------------------------------------------------------
  function openPhrasePicker(currentValue) {
    const state = ensureSportState();
    state.phrasePicker = {
      isOpen: true,
      search: "",
      selected: String(currentValue || ""),
    };
    window.renderApp();
  }

  function closePhrasePicker() {
    const state = ensureSportState();
    state.phrasePicker = null;
    window.renderApp();
  }

  function applyPhrasePicker() {
    const state = ensureSportState();
    const picker = state.phrasePicker;
    if (!picker) return;
    const form = document.querySelector("[data-sport-card-form]");
    if (form) {
      const conclusionEl = form.elements.conclusionText;
      if (conclusionEl) {
        conclusionEl.value = picker.selected || "";
        conclusionEl.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
    state.phrasePicker = null;
    window.renderApp();
  }

  // ----- Рендер ------------------------------------------------------------
  function renderCheckbox(name, checked, label) {
    return (
      '<label class="sport-checkbox">' +
      '<input type="checkbox" name="' + esc(name) + '"' + (checked ? " checked" : "") + ">" +
      "<span>" + esc(label) + "</span>" +
      "</label>"
    );
  }

  function renderSportCard() {
    const state = ensureSportState();
    if (!state.isOpen) return "";
    const template = window.getDoctorTemplate
      ? window.getDoctorTemplate(SPORT_CARD_ROLE_ID)
      : null;
    if (!template) {
      console.error("Не найден шаблон спортивной справки");
      return "";
    }
    const exam = window.getDoctorExam
      ? window.getDoctorExam(state.clientId, state.visitId, state.doctorRoleId || SPORT_CARD_ROLE_ID)
      : null;
    const fields = (exam && exam.fields) || {};
    const client = (window.data?.clients || []).find(
      (item) => String(item.id) === String(state.clientId),
    ) || null;
    const fullName = client?.fullName || client?.name || client?.fio || "Клиент";

    function val(key) {
      const v = fields[key];
      if (v !== undefined) return v;
      const def = (template.fields.find((f) => f.key === key) || {}).defaultValue;
      return def === undefined ? "" : def;
    }
    function isChecked(key) {
      const v = fields[key];
      if (v !== undefined) return Boolean(v);
      const def = (template.fields.find((f) => f.key === key) || {}).defaultValue;
      return Boolean(def);
    }

    const todayIso = new Date().toLocaleDateString("ru-RU");
    const examDate = val("examDate") || todayIso;
    const ekgDate = extractRuDate(val("ekg")) || extractRuDate(examDate) || todayIso;
    const ekgConclusion = String(val("ekgConclusion")).trim() || buildAutoEkgConclusion(ekgDate);

    return `
      <div class="sport-card-backdrop" data-sport-card>
        <div class="sport-card-window">
          <div class="sport-card-titlebar">
            <div class="sport-card-title">${esc(state.serviceName || "Спортивная справка")}</div>
            <button type="button" class="sport-card-close" data-sport-card-close>×</button>
          </div>

          <form class="sport-card-form" data-sport-card-form>
            <div class="sport-card-top">
              <label class="sport-card-field sport-card-field--date">
                <span>Дата</span>
                <input type="text" name="examDate" value="${esc(examDate)}" />
              </label>
              <label class="sport-card-field sport-card-field--fio">
                <span>Ф.И.О.</span>
                <input type="text" name="patientFullName" value="${esc(fullName)}" readonly />
              </label>
              <div class="sport-card-flags">
                ${renderCheckbox("hasGlasses", isChecked("hasGlasses"), "очки")}
                ${renderCheckbox("hasHearingAid", isChecked("hasHearingAid"), "слуховой аппарат")}
              </div>
            </div>

            <div class="sport-card-row sport-card-row--wide">
              <label>Мед. требования</label>
              <textarea name="medicalRequirements" rows="3">${esc(val("medicalRequirements"))}</textarea>
            </div>

            <div class="sport-card-grid">
              <label class="sport-card-field">
                <span>ЭКГ</span>
                <input type="text" name="ekg" value="${esc(val("ekg"))}" />
              </label>
              <label class="sport-card-field">
                <span>Заключение ЭКГ</span>
                <input type="text" name="ekgConclusion" value="${esc(ekgConclusion)}" />
              </label>
              <label class="sport-card-field">
                <span>Флюорография</span>
                <input type="text" name="fluorography" value="${esc(val("fluorography"))}" />
              </label>
              <label class="sport-card-field">
                <span>№ Логотипа</span>
                <input type="text" name="logotypeNumber" value="${esc(val("logotypeNumber"))}" />
              </label>
              <label class="sport-card-field sport-card-field--wide">
                <span>Диагноз</span>
                <input type="text" name="diagnosis" value="${esc(val("diagnosis"))}" />
              </label>
            </div>

            <div class="sport-card-row sport-card-row--conclusion">
              <label>Заключение</label>
              <div class="sport-card-conclusion">
                <textarea name="conclusionText" rows="3">${esc(val("conclusionText"))}</textarea>
                <button type="button" class="sport-card-pick" data-sport-pick-phrase title="Выбор из справочника">…</button>
              </div>
            </div>

            <div class="sport-card-decision">
              <label class="sport-card-radio">
                <input type="radio" name="conclusion" value="Годен" ${val("conclusion") === "Годен" ? "checked" : ""} />
                <span>Годен</span>
              </label>
              <label class="sport-card-radio">
                <input type="radio" name="conclusion" value="Не годен" ${val("conclusion") === "Не годен" ? "checked" : ""} />
                <span>Не годен</span>
              </label>
            </div>

            <div class="sport-card-actions">
              ${state.doctorRoleId === "chairman" ? '<button type="button" class="primary-button" data-sport-card-print>Печать</button>' : ""}
              <button type="submit" class="primary-button">Сохранить</button>
              <button type="button" class="ghost-button" data-sport-card-close>Отмена</button>
            </div>
          </form>
        </div>

        ${renderPhrasePicker()}
      </div>
    `;
  }

  function renderPhrasePicker() {
    const state = ensureSportState();
    const picker = state.phrasePicker;
    if (!picker || !picker.isOpen) return "";

    const search = String(picker.search || "");
    const phrases = window.data.sportPhrases || [];
    const items = search.length >= 3
      ? phrases.filter((item) =>
          String(item.text || item.name || "").toLowerCase().includes(search.toLowerCase()),
        )
      : [];
    const hint = search.length < 3
      ? "Начните поиск с трёх символов"
      : (items.length === 0 ? "Ничего не найдено" : `Найдено: ${items.length}`);
    const selected = String(picker.selected || "");

    const list = items
      .map(
        (item) => `
          <button type="button"
                  class="sport-phrase-item ${selected === item.text ? "sport-phrase-item--active" : ""}"
                  data-phrase-pick="${esc(item.text)}">
            ${esc(item.text || item.name || "")}
          </button>
        `,
      )
      .join("");

    return `
      <div class="sport-phrase-backdrop" data-phrase-picker>
        <div class="sport-phrase-window">
          <div class="sport-phrase-titlebar">
            <div class="sport-phrase-title">Выбор значений</div>
            <button type="button" class="sport-phrase-close" data-phrase-cancel>×</button>
          </div>
          <div class="sport-phrase-hint">${esc(hint)}</div>
          <div class="sport-phrase-search">
            <input type="text" data-phrase-search value="${esc(search)}" placeholder="Поиск" />
            <button type="button" class="sport-phrase-add" data-phrase-add title="Добавить как новую фразу">+</button>
          </div>
          <div class="sport-phrase-list">${list}</div>
          <div class="sport-phrase-selected">
            <label>Выбранное значение</label>
            <textarea data-phrase-selected rows="2">${esc(selected)}</textarea>
          </div>
          <div class="sport-phrase-actions">
            <button type="button" class="primary-button" data-phrase-ok>OK</button>
            <button type="button" class="ghost-button" data-phrase-cancel>Отмена</button>
          </div>
        </div>
      </div>
    `;
  }

  function renderServicePlaceholder() {
    const data = window.data;
    if (!data.servicePlaceholder || !data.servicePlaceholder.isOpen) return "";
    const name = data.servicePlaceholder.serviceName || "услуги";
    return `
      <div class="sport-card-backdrop" data-service-placeholder>
        <div class="sport-card-window sport-card-window--placeholder">
          <div class="sport-card-titlebar">
            <div class="sport-card-title">${esc(name)}</div>
            <button type="button" class="sport-card-close" data-service-placeholder-close>×</button>
          </div>
          <div class="sport-card-placeholder">
            <p>Карточка для этой услуги пока не готова.</p>
            <p class="muted">Позже здесь будет отдельная форма для услуги «${esc(name)}».</p>
          </div>
          <div class="sport-card-actions">
            <button type="button" class="primary-button" data-service-placeholder-close>Закрыть</button>
          </div>
        </div>
      </div>
    `;
  }

  function openServicePlaceholder(service) {
    closeServiceCardOverlays();
    window.data.servicePlaceholder = {
      isOpen: true,
      serviceName: service?.name || "Услуга",
    };
    window.renderApp();
  }

  function closeServicePlaceholder() {
    if (window.data.servicePlaceholder) window.data.servicePlaceholder.isOpen = false;
    window.renderApp();
  }

  // ----- Сохранение --------------------------------------------------------
  function collectSportFormData(form) {
    const template = window.getDoctorTemplate(SPORT_CARD_ROLE_ID);
    const result = {};
    (template?.fields || []).forEach((field) => {
      if (field.key === "patientFullName") return;
      const el = form.elements[field.key];
      if (!el) return;
      if (field.type === "checkbox") {
        result[field.key] = !!el.checked;
      } else if (field.type === "radio") {
        const checked = form.querySelector(`input[name="${field.key}"]:checked`);
        result[field.key] = checked ? checked.value : "";
      } else {
        result[field.key] = el.value;
      }
    });
    return result;
  }

  async function saveSportCard(form) {
    const state = ensureSportState();
    const data = collectSportFormData(form);
    if (state.examId && typeof window.saveDoctorExam === "function") {
      return window.saveDoctorExam(state.examId, data);
    }
    return null;
  }

  // ----- Биндинги ---------------------------------------------------------
  function bindServiceCardHandlers() {
    // Открытие карточки из услуги (кнопка "Открыть карточку")
    document.querySelectorAll("[data-open-service-card]").forEach((button) => {
      if (button.__sportBound) return;
      button.__sportBound = true;
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const serviceId = button.dataset.openServiceCard;
        openServiceCard(serviceId);
      });
    });

    // Закрытие placeholder
    document.querySelectorAll("[data-service-placeholder-close]").forEach((button) => {
      button.addEventListener("click", () => closeServicePlaceholder());
    });

    // Спортивная карточка
    const card = document.querySelector("[data-sport-card]");
    if (card) {
      // Не закрывать клик внутри окна
      const win = card.querySelector(".sport-card-window");
      win?.addEventListener("click", (event) => event.stopPropagation());
      card.querySelectorAll("[data-sport-card-close]").forEach((button) => {
        button.addEventListener("click", () => closeSportCard());
      });

      const form = card.querySelector("[data-sport-card-form]");
      if (form) {
        const syncAutoEkgConclusion = () => {
          const conclusionInput = getFirstNamedControl(form.elements.ekgConclusion);
          if (!conclusionInput) return;
          const currentValue = String(conclusionInput.value || "").trim();
          if (currentValue && !isAutoEkgConclusion(currentValue)) return;
          const ekgInput = getFirstNamedControl(form.elements.ekg);
          const examDateInput = getFirstNamedControl(form.elements.examDate);
          const ekgDate =
            extractRuDate(ekgInput?.value) ||
            extractRuDate(examDateInput?.value) ||
            todayRuDate();
          conclusionInput.value = buildAutoEkgConclusion(ekgDate);
        };
        const examDateInput = getFirstNamedControl(form.elements.examDate);
        const ekgInput = getFirstNamedControl(form.elements.ekg);
        examDateInput?.addEventListener("input", syncAutoEkgConclusion);
        examDateInput?.addEventListener("change", syncAutoEkgConclusion);
        ekgInput?.addEventListener("input", syncAutoEkgConclusion);
        ekgInput?.addEventListener("change", syncAutoEkgConclusion);

        form.addEventListener("submit", async (event) => {
          event.preventDefault();
          event.stopPropagation();
          await saveSportCard(form);
          window.showToast && window.showToast("Спортивная справка сохранена");
          closeSportCard();
        });
        const printBtn = form.querySelector("[data-sport-card-print]");
        if (printBtn) {
          printBtn.addEventListener("click", async (event) => {
            event.preventDefault();
            event.stopPropagation();
            const targetWindow = window.open("about:blank", "_blank");
            const saved = await saveSportCard(form);
            if (!saved) {
              if (targetWindow && !targetWindow.closed) {
                targetWindow.close();
              }
              return;
            }
            await window.printChairmanDocumentFromExam?.(ensureSportState().examId, { targetWindow });
          });
        }
        const pickBtn = form.querySelector("[data-sport-pick-phrase]");
        if (pickBtn) {
          pickBtn.addEventListener("click", (event) => {
            event.preventDefault();
            const conclusionEl = form.elements.conclusionText;
            openPhrasePicker(conclusionEl ? conclusionEl.value : "");
          });
        }
      }
    }

    // Пикер фраз
    const picker = document.querySelector("[data-phrase-picker]");
    if (picker) {
      const win = picker.querySelector(".sport-phrase-window");
      win?.addEventListener("click", (event) => event.stopPropagation());
      picker.querySelectorAll("[data-phrase-cancel]").forEach((button) => {
        button.addEventListener("click", () => closePhrasePicker());
      });
      picker.querySelector("[data-phrase-ok]")?.addEventListener("click", () => applyPhrasePicker());

      const search = picker.querySelector("[data-phrase-search]");
      const listEl = picker.querySelector(".sport-phrase-list");
      const hintEl = picker.querySelector(".sport-phrase-hint");
      if (search && listEl && hintEl) {
        const refreshList = () => {
          const state = ensureSportState();
          if (!state.phrasePicker) return;
          const value = String(search.value || "");
          state.phrasePicker.search = value;
          const phrases = window.data.sportPhrases || [];
          const items = value.length >= 3
            ? phrases.filter((item) =>
                String(item.text || item.name || "")
                  .toLowerCase()
                  .includes(value.toLowerCase()),
              )
            : [];
          if (value.length < 3) {
            hintEl.textContent = "Начните поиск с трёх символов";
          } else if (items.length === 0) {
            hintEl.textContent = "Ничего не найдено";
          } else {
            hintEl.textContent = "Найдено: " + items.length;
          }
          const selected = String(state.phrasePicker.selected || "");
          listEl.innerHTML = items
            .map((item) => {
              const txt = String(item.text || item.name || "");
              const safeText = esc(txt);
              const activeCls = selected === txt ? " sport-phrase-item--active" : "";
              return (
                '<button type="button" class="sport-phrase-item' + activeCls +
                '" data-phrase-pick="' + safeText + '">' + safeText + "</button>"
              );
            })
            .join("");
          // Перевешиваем обработчики на свеженарисованные кнопки.
          listEl.querySelectorAll("[data-phrase-pick]").forEach((btn) => {
            btn.addEventListener("click", () => {
              const st = ensureSportState();
              if (!st.phrasePicker) return;
              st.phrasePicker.selected = btn.dataset.phrasePick || "";
              const sel = picker.querySelector("[data-phrase-selected]");
              if (sel) sel.value = st.phrasePicker.selected;
              listEl.querySelectorAll(".sport-phrase-item").forEach((b) => {
                b.classList.toggle(
                  "sport-phrase-item--active",
                  (b.dataset.phrasePick || "") === st.phrasePicker.selected,
                );
              });
            });
          });
        };
        search.addEventListener("input", refreshList);
        // Не теряем фокус и каретку при первом открытии.
        search.focus();
        const len = search.value.length;
        try { search.setSelectionRange(len, len); } catch (e) {}
        // Если фразы загрузились асинхронно после открытия — не трогаем,
        // первый запуск списка случится при первом вводе.
        refreshList();
      }

      const selectedArea = picker.querySelector("[data-phrase-selected]");
      if (selectedArea) {
        selectedArea.addEventListener("input", (event) => {
          const state = ensureSportState();
          if (!state.phrasePicker) return;
          state.phrasePicker.selected = event.target.value;
        });
      }

      picker.querySelectorAll("[data-phrase-pick]").forEach((button) => {
        button.addEventListener("click", () => {
          const state = ensureSportState();
          if (!state.phrasePicker) return;
          state.phrasePicker.selected = button.dataset.phrasePick || "";
          window.renderApp();
        });
      });
      picker.querySelector("[data-phrase-add]")?.addEventListener("click", async () => {
        const state = ensureSportState();
        const text = (state.phrasePicker?.search || state.phrasePicker?.selected || "").trim();
        if (!text) {
          window.showToast && window.showToast("Введите текст для добавления");
          return;
        }
        const created = await createSportPhrase(text);
        if (created) {
          state.phrasePicker.selected = created.text;
          state.phrasePicker.search = "";
          window.showToast && window.showToast("Фраза добавлена в справочник");
          window.renderApp();
        }
      });
    }
  }

  function renderServiceCardModals() {
    if (window.appState?.doctorExamModal?.isOpen) return "";
    return renderSportCard() + renderServicePlaceholder();
  }

  window.openServiceCard = openServiceCard;
  window.openSportCard = openSportCard;
  window.closeServiceCardOverlays = closeServiceCardOverlays;
  window.closeSportCard = closeSportCard;
  window.openPhrasePicker = openPhrasePicker;
  window.closePhrasePicker = closePhrasePicker;
  window.renderServiceCardModals = renderServiceCardModals;
  window.bindServiceCardHandlers = bindServiceCardHandlers;
  window.loadSportPhrases = loadSportPhrases;
  window.resolveServiceCardKind = resolveServiceCardKind;
})();
