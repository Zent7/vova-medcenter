(function () {
  const CHAIRMAN_MEDICAL_REQUIREMENTS_HISTORY_KEY = "vova-chairman-medical-requirements-history-v1";

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function normalizeMedicalRequirementValue(value) {
    return String(value ?? "").trim();
  }

  function loadMedicalRequirementsHistory() {
    try {
      const raw = window.localStorage?.getItem(CHAIRMAN_MEDICAL_REQUIREMENTS_HISTORY_KEY);
      const values = raw ? JSON.parse(raw) : [];
      return Array.isArray(values)
        ? values.map(normalizeMedicalRequirementValue).filter(Boolean)
        : [];
    } catch {
      return [];
    }
  }

  function saveMedicalRequirementsHistory(values) {
    const uniqueValues = [];
    const seen = new Set();
    (Array.isArray(values) ? values : []).forEach((value) => {
      const normalized = normalizeMedicalRequirementValue(value);
      const key = normalized.toLowerCase();
      if (!normalized || seen.has(key)) return;
      seen.add(key);
      uniqueValues.push(normalized);
    });
    try {
      window.localStorage?.setItem(CHAIRMAN_MEDICAL_REQUIREMENTS_HISTORY_KEY, JSON.stringify(uniqueValues.slice(0, 80)));
    } catch {
      // localStorage may be unavailable in embedded views.
    }
    return uniqueValues;
  }

  function rememberMedicalRequirementValue(value) {
    const normalized = normalizeMedicalRequirementValue(value);
    if (!normalized) return loadMedicalRequirementsHistory();
    return saveMedicalRequirementsHistory([normalized, ...loadMedicalRequirementsHistory()]);
  }

  window.rememberChairmanMedicalRequirement = rememberMedicalRequirementValue;

  function repairPresetText(value) {
    const text = String(value ?? "");
    if (!text) return "";
    if (typeof window.repairDemoText === "function") {
      const repaired = window.repairDemoText(text);
      if (repaired && repaired !== text) return repaired;
    }
    try {
      return decodeURIComponent(escape(text));
    } catch {
      return text;
    }
  }

  function normalizePresetKey(value) {
    return repairPresetText(value).trim().toLowerCase();
  }

  function findDoctorPreset(presets, presetName) {
    if (!presets || typeof presets !== "object") return null;
    if (Object.prototype.hasOwnProperty.call(presets, presetName)) {
      return presets[presetName];
    }

    const normalizedPresetName = normalizePresetKey(presetName);
    const match = Object.entries(presets).find(([key]) => normalizePresetKey(key) === normalizedPresetName);
    return match ? match[1] : null;
  }

  function isPresetTextField(element) {
    if (!element || element.type === "radio" || element.type === "checkbox") return false;
    if (element.tagName === "TEXTAREA") return true;
    if (element.tagName !== "INPUT") return false;
    return ["", "text", "search", "tel", "url", "email", "number"].includes(element.type || "");
  }

  function getFirstNamedControl(elements) {
    if (!elements) return null;
    if (elements.length && elements.tagName === undefined) return elements[0] || null;
    return elements;
  }

  function getNamedControls(elements) {
    if (!elements) return [];
    if (elements.length && elements.tagName === undefined) return Array.from(elements);
    return [elements];
  }

  function dispatchPresetFieldEvents(element) {
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function escapeCssAttributeValue(value) {
    if (window.CSS?.escape) return window.CSS.escape(String(value));
    return String(value).replace(/["\\]/g, "\\$&");
  }

  function applyPresetFieldValue(form, fieldKey, value) {
    const element = getFirstNamedControl(form.elements[fieldKey]);
    if (!isPresetTextField(element)) return false;

    const nextValue = value == null ? "" : repairPresetText(value);
    if (element.value === nextValue) return false;

    element.value = nextValue;
    dispatchPresetFieldEvents(element);
    return true;
  }

  function notifyMissingDoctorPreset(doctorRoleId, presetName, presets) {
    const availablePresets = presets && typeof presets === "object" ? Object.keys(presets) : [];
    console.warn("Doctor preset was not found", {
      doctorRoleId,
      presetName,
      availablePresets,
    });
    window.showToast?.(`Не найден пресет врача: ${repairPresetText(presetName) || "без названия"}`);
  }

  const AUTO_EKG_CONCLUSION_PREFIX =
    "Ритм синусовый, ЧСС , нормальная электрическая позиция сердца, ЭКГ-комплексы без особенностей";
  const GUARD_AUTO_EKG_CONCLUSION_PREFIX =
    "Ритм синусовый, ЧСС, ЭОС нормальное положение, ЭКГ без особенностей";

  function extractRuDate(value) {
    return String(value ?? "").match(/\b\d{2}\.\d{2}\.(?:\d{2}|\d{4})\b/)?.[0] || "";
  }

  function todayRuDate(useFullYear = false) {
    return new Date().toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: useFullYear ? "numeric" : "2-digit",
    });
  }

  function getAutoEkgConclusionPrefix(chairmanType = "") {
    return chairmanType === "guard" ? GUARD_AUTO_EKG_CONCLUSION_PREFIX : AUTO_EKG_CONCLUSION_PREFIX;
  }

  function buildAutoEkgConclusion(date, chairmanType = "") {
    const finalDate = extractRuDate(date) || todayRuDate(chairmanType === "guard");
    return `${getAutoEkgConclusionPrefix(chairmanType)} от ${finalDate}`;
  }

  function isAutoEkgConclusion(value, chairmanType = "") {
    const normalized = String(value ?? "").trim();
    if (normalized.startsWith(`${getAutoEkgConclusionPrefix(chairmanType)} от `)) return true;
    return chairmanType === "guard" && normalized.startsWith(`${AUTO_EKG_CONCLUSION_PREFIX} от `);
  }

  function closeMedicalRequirementsPicker() {
    document.querySelector("[data-medical-requirements-picker]")?.remove();
  }

  function openMedicalRequirementsPicker(textarea) {
    if (!textarea) return;
    closeMedicalRequirementsPicker();

    const currentTextareaValue = normalizeMedicalRequirementValue(textarea.value);
    let history = currentTextareaValue
      ? rememberMedicalRequirementValue(currentTextareaValue)
      : saveMedicalRequirementsHistory(loadMedicalRequirementsHistory());
    let selectedValue = currentTextareaValue || history[0] || "";
    const overlay = document.createElement("div");
    overlay.className = "medical-requirements-picker";
    overlay.dataset.medicalRequirementsPicker = "true";
    overlay.innerHTML = `
      <div class="medical-requirements-picker__panel" role="dialog" aria-modal="true" aria-label="Выбор значений">
        <div class="medical-requirements-picker__head">
          <strong>Выбор значений</strong>
          <button type="button" class="medical-requirements-picker__close" data-medical-requirements-close aria-label="Закрыть">×</button>
        </div>
        <label class="medical-requirements-picker__label">Начните поиск с трех символов</label>
        <div class="medical-requirements-picker__top">
          <input class="medical-requirements-picker__search" data-medical-requirements-search value="${escapeHtml(selectedValue)}" />
          <button type="button" class="medical-requirements-picker__small" data-medical-requirements-remove>-</button>
          <button type="button" class="medical-requirements-picker__small" data-medical-requirements-add>+</button>
          <button type="button" class="medical-requirements-picker__ok" data-medical-requirements-ok>OK</button>
        </div>
        <div class="medical-requirements-picker__list" data-medical-requirements-list></div>
      </div>
    `;

    const panel = overlay.querySelector(".medical-requirements-picker__panel");
    const searchInput = overlay.querySelector("[data-medical-requirements-search]");
    const listNode = overlay.querySelector("[data-medical-requirements-list]");

    const commitValue = (value) => {
      const normalized = normalizeMedicalRequirementValue(value);
      if (!normalized) return;
      textarea.value = normalized;
      rememberMedicalRequirementValue(normalized);
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
      textarea.dispatchEvent(new Event("change", { bubbles: true }));
      closeMedicalRequirementsPicker();
    };

    const renderList = () => {
      const query = normalizeMedicalRequirementValue(searchInput?.value).toLowerCase();
      const visibleValues = history.filter((item) => !query || item.toLowerCase().includes(query));
      listNode.innerHTML = visibleValues.length
        ? visibleValues
            .map(
              (item) => `
                <button type="button" class="medical-requirements-picker__item${item === selectedValue ? " medical-requirements-picker__item--active" : ""}" data-medical-requirements-value="${escapeHtml(item)}">
                  <span>${escapeHtml(item)}</span>
                </button>
              `,
            )
            .join("")
        : `<div class="medical-requirements-picker__empty">Введите значение и нажмите + или OK</div>`;

      listNode.querySelectorAll("[data-medical-requirements-value]").forEach((button) => {
        button.addEventListener("click", () => {
          selectedValue = normalizeMedicalRequirementValue(button.dataset.medicalRequirementsValue);
          if (searchInput) searchInput.value = selectedValue;
          renderList();
        });
        button.addEventListener("dblclick", () => commitValue(button.dataset.medicalRequirementsValue));
      });
    };

    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) closeMedicalRequirementsPicker();
    });
    panel?.addEventListener("click", (event) => event.stopPropagation());
    overlay.querySelector("[data-medical-requirements-close]")?.addEventListener("click", closeMedicalRequirementsPicker);
    overlay.querySelector("[data-medical-requirements-ok]")?.addEventListener("click", () => {
      commitValue(selectedValue || searchInput?.value);
    });
    overlay.querySelector("[data-medical-requirements-add]")?.addEventListener("click", () => {
      selectedValue = normalizeMedicalRequirementValue(searchInput?.value);
      history = rememberMedicalRequirementValue(selectedValue);
      renderList();
    });
    overlay.querySelector("[data-medical-requirements-remove]")?.addEventListener("click", () => {
      const removeKey = normalizeMedicalRequirementValue(selectedValue || searchInput?.value).toLowerCase();
      history = saveMedicalRequirementsHistory(history.filter((item) => item.toLowerCase() !== removeKey));
      selectedValue = history[0] || "";
      if (searchInput) searchInput.value = "";
      renderList();
    });
    searchInput?.addEventListener("input", () => {
      selectedValue = normalizeMedicalRequirementValue(searchInput.value);
      renderList();
    });
    searchInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        commitValue(selectedValue || searchInput.value);
      }
      if (event.key === "Escape") {
        event.preventDefault();
        closeMedicalRequirementsPicker();
      }
    });

    document.body.appendChild(overlay);
    renderList();
    setTimeout(() => searchInput?.focus(), 0);
  }

  function renderClassicRadio(name, value, options) {
    return `
      <div class="doctor-classic-radio-group">
        ${(options || [])
          .map(
            (option) => `
              <label class="doctor-classic-radio">
                <input
                  type="radio"
                  name="${escapeHtml(name)}"
                  value="${escapeHtml(option)}"
                  ${option === value ? "checked" : ""}
                />
                <span>${escapeHtml(option)}</span>
              </label>
            `,
          )
          .join("")}
      </div>
    `;
  }

  function renderCheckboxField(name, checked, label) {
    return `
      <label class="chairman-checkbox">
        <input type="checkbox" name="${escapeHtml(name)}" ${checked ? "checked" : ""} />
        <span>${escapeHtml(label)}</span>
      </label>
    `;
  }

  function renderPhthisiatristClassic(template, exam, client) {
    const fields = exam.fields || {};
    const fullName = client?.fullName || client?.name || client?.fio || "Клиент";

    return `
      <div class="doctor-classic-backdrop" data-doctor-exam-modal>
        <div class="doctor-classic-window">
          <div class="doctor-classic-titlebar">
            <div class="doctor-classic-title">${escapeHtml(template.name)}</div>
            <button type="button" class="doctor-classic-close" data-doctor-exam-close>×</button>
          </div>

          <form
            class="doctor-classic-form"
            data-doctor-exam-form
            data-exam-id="${escapeHtml(exam.id)}"
            data-doctor-role-id="${escapeHtml(template.id)}"
          >
            <div class="doctor-classic-body">
              <div class="doctor-classic-main">
                <div class="doctor-classic-row doctor-classic-row--fio">
                  <div class="doctor-classic-label">Ф.И.О.</div>
                  <div class="doctor-classic-field">
                    <input
                      class="doctor-classic-input doctor-classic-input--fio"
                      type="text"
                      name="patientFullName"
                      value="${escapeHtml(fullName)}"
                      readonly
                    />
                  </div>
                </div>

                <div class="doctor-classic-row doctor-classic-row--complaints">
                  <div class="doctor-classic-label">Жалобы:</div>
                  <div class="doctor-classic-field doctor-classic-field--complaints">
                    <div class="doctor-classic-complaints-left">
                      <select class="doctor-classic-select" name="complaintsPreset">
                        ${(template.fields.find((f) => f.key === "complaintsPreset")?.options || [])
                          .map(
                            (option) => `
                              <option value="${escapeHtml(option)}" ${
                                option === (fields.complaintsPreset ?? "") ? "selected" : ""
                              }>
                                ${escapeHtml(option)}
                              </option>
                            `,
                          )
                          .join("")}
                      </select>
                    </div>
                    <div class="doctor-classic-complaints-right">
                      <input
                        class="doctor-classic-input"
                        type="text"
                        name="complaints"
                        value="${escapeHtml(fields.complaints ?? "")}"
                      />
                    </div>
                  </div>
                </div>

                <div class="doctor-classic-row">
                  <div class="doctor-classic-label">Анамнез:</div>
                  <div class="doctor-classic-field">
                    <textarea
                      class="doctor-classic-textarea doctor-classic-textarea--mid"
                      name="anamnesis"
                    >${escapeHtml(fields.anamnesis ?? "")}</textarea>
                  </div>
                </div>

                <div class="doctor-classic-row">
                  <div class="doctor-classic-label">Объективно:</div>
                  <div class="doctor-classic-field">
                    <textarea
                      class="doctor-classic-textarea doctor-classic-textarea--mid"
                      name="objective"
                    >${escapeHtml(fields.objective ?? "")}</textarea>
                  </div>
                </div>

                <div class="doctor-classic-row">
                  <div class="doctor-classic-label">Диагноз:</div>
                  <div class="doctor-classic-field">
                    <textarea
                      class="doctor-classic-textarea doctor-classic-textarea--diagnosis"
                      name="diagnosis"
                    >${escapeHtml(fields.diagnosis ?? "")}</textarea>
                  </div>
                </div>

                <div class="doctor-classic-row doctor-classic-row--conclusion">
                  <div class="doctor-classic-label">Заключение:</div>
                  <div class="doctor-classic-field">
                    ${renderClassicRadio(
                      "conclusion",
                      fields.conclusion ?? "Годен",
                      template.fields.find((f) => f.key === "conclusion")?.options || [],
                    )}

                    <div class="doctor-classic-bottom-line">
                      <div class="doctor-classic-bottom-item doctor-classic-bottom-item--validity">
                        <label class="doctor-classic-inline-label">Срок:</label>
                        <select class="doctor-classic-select doctor-classic-select--small" name="validity">
                          ${(template.fields.find((f) => f.key === "validity")?.options || [])
                            .map(
                              (option) => `
                                <option value="${escapeHtml(option)}" ${
                                  option === (fields.validity ?? "") ? "selected" : ""
                                }>
                                  ${escapeHtml(option)}
                                </option>
                              `,
                            )
                            .join("")}
                        </select>
                      </div>

                      <div class="doctor-classic-bottom-item doctor-classic-bottom-item--mkb">
                        <label class="doctor-classic-inline-label">МКБ10:</label>
                        <input
                          class="doctor-classic-input doctor-classic-input--mkb"
                          type="text"
                          name="mkb10"
                          value="${escapeHtml(fields.mkb10 ?? "")}"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                <div class="doctor-classic-row doctor-classic-row--note">
                  <div class="doctor-classic-label">Примечание:</div>
                  <div class="doctor-classic-field">
                    <textarea
                      class="doctor-classic-textarea doctor-classic-textarea--note"
                      name="note"
                    >${escapeHtml(fields.note ?? "")}</textarea>
                  </div>
                </div>
              </div>

              <div class="doctor-classic-sidebar">
                <button type="submit" class="doctor-classic-sidebtn">ОК</button>
                <button type="button" class="doctor-classic-sidebtn" data-doctor-exam-close>Отмена</button>
                <button type="button" class="doctor-classic-sidebtn doctor-classic-sidebtn--danger" data-doctor-exam-delete>удалить врача</button>
              </div>
            </div>
          </form>
        </div>
      </div>
    `;
  }

  function renderTherapistClassic(template, exam, client) {
    const fields = exam.fields || {};
    const fullName = client?.fullName || client?.name || client?.fio || "Клиент";

    const fieldOptions = (key) => template.fields.find((f) => f.key === key)?.options || [];
    const fieldDefault = (key) => template.fields.find((f) => f.key === key)?.defaultValue ?? "";
    const fieldValue = (key) => fields[key] ?? fieldDefault(key);

    return `
      <div class="doctor-classic-backdrop" data-doctor-exam-modal>
        <div class="doctor-classic-window therapist-window">
          <div class="doctor-classic-titlebar">
            <div class="doctor-classic-title">${escapeHtml(template.name)}</div>
            <button type="button" class="doctor-classic-close" data-doctor-exam-close>×</button>
          </div>

          <form
            class="doctor-classic-form therapist-form"
            data-doctor-exam-form
            data-exam-id="${escapeHtml(exam.id)}"
            data-doctor-role-id="${escapeHtml(template.id)}"
          >
            <div class="doctor-classic-body therapist-body">
              <div class="doctor-classic-main therapist-main">
                <div class="doctor-classic-row doctor-classic-row--fio therapist-row">
                  <div class="doctor-classic-label">Ф.И.О.</div>
                  <div class="doctor-classic-field">
                    <input
                      class="doctor-classic-input doctor-classic-input--fio"
                      type="text"
                      name="patientFullName"
                      value="${escapeHtml(fullName)}"
                      readonly
                    />
                  </div>
                </div>

                <div class="doctor-classic-row doctor-classic-row--complaints therapist-row">
                  <div class="doctor-classic-label">Жалобы:</div>
                  <div class="doctor-classic-field doctor-classic-field--complaints">
                    <div class="doctor-classic-complaints-left">
                      <select class="doctor-classic-select" name="complaintsPreset">
                        ${fieldOptions("complaintsPreset")
                          .map(
                            (option) => `
                              <option value="${escapeHtml(option)}" ${
                                option === fieldValue("complaintsPreset") ? "selected" : ""
                              }>
                                ${escapeHtml(option)}
                              </option>
                            `,
                          )
                          .join("")}
                      </select>
                    </div>
                    <div class="doctor-classic-complaints-right">
                      <input
                        class="doctor-classic-input"
                        type="text"
                        name="complaints"
                        value="${escapeHtml(fieldValue("complaints"))}"
                      />
                    </div>
                  </div>
                </div>

                <div class="doctor-classic-row therapist-row">
                  <div class="doctor-classic-label">Анамнез:</div>
                  <div class="doctor-classic-field">
                    <textarea class="doctor-classic-textarea therapist-textarea--short" name="anamnesis">${escapeHtml(fieldValue("anamnesis"))}</textarea>
                  </div>
                </div>

                <div class="doctor-classic-row therapist-row">
                  <div class="doctor-classic-label">Эпиданамнез:</div>
                  <div class="doctor-classic-field">
                    <textarea class="doctor-classic-textarea therapist-textarea--short" name="epidemiologicalAnamnesis">${escapeHtml(fieldValue("epidemiologicalAnamnesis"))}</textarea>
                  </div>
                </div>

                <div class="doctor-classic-row therapist-row">
                  <div class="doctor-classic-label">Аллергологический анамнез:</div>
                  <div class="doctor-classic-field">
                    <textarea class="doctor-classic-textarea therapist-textarea--short" name="allergicAnamnesis">${escapeHtml(fieldValue("allergicAnamnesis"))}</textarea>
                  </div>
                </div>

                <div class="therapist-section-label">Объективно:</div>
                <div class="therapist-objective-grid">
                  <div class="therapist-field">
                    <label>Состояние:</label>
                    <input class="doctor-classic-input" type="text" name="generalCondition" value="${escapeHtml(fieldValue("generalCondition"))}" />
                  </div>
                  <div class="therapist-field">
                    <label>Лимфоузлы:</label>
                    <input class="doctor-classic-input" type="text" name="lymphNodes" value="${escapeHtml(fieldValue("lymphNodes"))}" />
                  </div>
                  <div class="therapist-field">
                    <label>Кожные покровы:</label>
                    <input class="doctor-classic-input" type="text" name="skin" value="${escapeHtml(fieldValue("skin"))}" />
                  </div>
                  <div class="therapist-field">
                    <label>Пульс:</label>
                    <input class="doctor-classic-input" type="text" name="pulse" value="${escapeHtml(fieldValue("pulse"))}" />
                  </div>
                  <div class="therapist-field">
                    <label>АД:</label>
                    <input class="doctor-classic-input" type="text" name="bloodPressure" value="${escapeHtml(fieldValue("bloodPressure"))}" />
                  </div>
                  <div class="therapist-field">
                    <label>Дыхание:</label>
                    <input class="doctor-classic-input" type="text" name="breathing" value="${escapeHtml(fieldValue("breathing"))}" />
                  </div>
                  <div class="therapist-field">
                    <label>Тоны сердца:</label>
                    <input class="doctor-classic-input" type="text" name="heartSounds" value="${escapeHtml(fieldValue("heartSounds"))}" />
                  </div>
                  <div class="therapist-field">
                    <label>Живот:</label>
                    <input class="doctor-classic-input" type="text" name="abdomen" value="${escapeHtml(fieldValue("abdomen"))}" />
                  </div>
                  <div class="therapist-field">
                    <label>Язык:</label>
                    <input class="doctor-classic-input" type="text" name="tongue" value="${escapeHtml(fieldValue("tongue"))}" />
                  </div>
                  <div class="therapist-field">
                    <label>Глюкоза:</label>
                    <input class="doctor-classic-input" type="text" name="glucose" value="${escapeHtml(fieldValue("glucose"))}" />
                  </div>
                  <div class="therapist-field">
                    <label>Холестерин:</label>
                    <input class="doctor-classic-input" type="text" name="cholesterol" value="${escapeHtml(fieldValue("cholesterol"))}" />
                  </div>
                  <div class="therapist-field">
                    <label>Вес:</label>
                    <input class="doctor-classic-input" type="text" name="weight" value="${escapeHtml(fieldValue("weight"))}" />
                  </div>
                  <div class="therapist-field">
                    <label>Рост:</label>
                    <input class="doctor-classic-input" type="text" name="height" value="${escapeHtml(fieldValue("height"))}" />
                  </div>
                </div>

                <div class="doctor-classic-row therapist-row therapist-row--diagnosis">
                  <div class="doctor-classic-label">Диагноз:</div>
                  <div class="doctor-classic-field">
                    <textarea class="doctor-classic-textarea doctor-classic-textarea--diagnosis" name="diagnosis">${escapeHtml(fieldValue("diagnosis"))}</textarea>
                  </div>
                </div>

                <div class="doctor-classic-row doctor-classic-row--conclusion therapist-row">
                  <div class="doctor-classic-label">Заключение:</div>
                  <div class="doctor-classic-field">
                    <div class="doctor-classic-bottom-line therapist-bottom-line">
                      <div class="doctor-classic-bottom-item doctor-classic-bottom-item--validity">
                        <label class="doctor-classic-inline-label">Срок:</label>
                        <select class="doctor-classic-select doctor-classic-select--small" name="validity">
                          ${fieldOptions("validity")
                            .map(
                              (option) => `
                                <option value="${escapeHtml(option)}" ${option === fieldValue("validity") ? "selected" : ""}>
                                  ${escapeHtml(option)}
                                </option>
                              `,
                            )
                            .join("")}
                        </select>
                      </div>

                      ${renderClassicRadio("conclusion", fieldValue("conclusion"), fieldOptions("conclusion"))}

                      <div class="doctor-classic-bottom-item doctor-classic-bottom-item--mkb">
                        <label class="doctor-classic-inline-label">МКБ10:</label>
                        <input
                          class="doctor-classic-input doctor-classic-input--mkb"
                          type="text"
                          name="mkb10"
                          value="${escapeHtml(fieldValue("mkb10"))}"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                <div class="doctor-classic-row doctor-classic-row--note therapist-row">
                  <div class="doctor-classic-label">Примечание:</div>
                  <div class="doctor-classic-field">
                    <textarea class="doctor-classic-textarea doctor-classic-textarea--note" name="note">${escapeHtml(fieldValue("note"))}</textarea>
                  </div>
                </div>
              </div>

              <div class="doctor-classic-sidebar">
                <button type="submit" class="doctor-classic-sidebtn">ОК</button>
                <button type="button" class="doctor-classic-sidebtn" data-doctor-exam-close>Отмена</button>
                <button type="button" class="doctor-classic-sidebtn doctor-classic-sidebtn--danger" data-doctor-exam-delete>удалить врача</button>
              </div>
            </div>
          </form>
        </div>
      </div>
    `;
  }

  function renderSectionedClassic(template, exam, client, config) {
    const fields = exam.fields || {};
    const fullName = client?.fullName || client?.name || client?.fio || "Клиент";
    const fieldOptions = (key) => template.fields.find((f) => f.key === key)?.options || [];
    const fieldDefault = (key) => template.fields.find((f) => f.key === key)?.defaultValue ?? "";
    const fieldValue = (key) => fields[key] ?? fieldDefault(key);
    const sections = config.sections || [];

    return `
      <div class="doctor-classic-backdrop" data-doctor-exam-modal>
        <div class="doctor-classic-window sectioned-doctor-window">
          <div class="doctor-classic-titlebar">
            <div class="doctor-classic-title">${escapeHtml(template.name)}</div>
            <button type="button" class="doctor-classic-close" data-doctor-exam-close>×</button>
          </div>

          <form
            class="doctor-classic-form"
            data-doctor-exam-form
            data-exam-id="${escapeHtml(exam.id)}"
            data-doctor-role-id="${escapeHtml(template.id)}"
          >
            <div class="doctor-classic-body sectioned-doctor-body">
              <div class="doctor-classic-main sectioned-doctor-main">
                <div class="doctor-classic-row doctor-classic-row--fio sectioned-doctor-row">
                  <div class="doctor-classic-label">Ф.И.О.</div>
                  <div class="doctor-classic-field">
                    <input class="doctor-classic-input doctor-classic-input--fio" type="text" name="patientFullName" value="${escapeHtml(fullName)}" readonly />
                  </div>
                </div>

                <div class="doctor-classic-row doctor-classic-row--complaints sectioned-doctor-row">
                  <div class="doctor-classic-label">Жалобы:</div>
                  <div class="doctor-classic-field doctor-classic-field--complaints">
                    <div class="doctor-classic-complaints-left">
                      <select class="doctor-classic-select" name="complaintsPreset">
                        ${fieldOptions("complaintsPreset")
                          .map(
                            (option) => `
                              <option value="${escapeHtml(option)}" ${option === fieldValue("complaintsPreset") ? "selected" : ""}>
                                ${escapeHtml(option)}
                              </option>
                            `,
                          )
                          .join("")}
                      </select>
                    </div>
                    <div class="doctor-classic-complaints-right">
                      <input class="doctor-classic-input" type="text" name="complaints" value="${escapeHtml(fieldValue("complaints"))}" />
                    </div>
                  </div>
                </div>

                <div class="doctor-classic-row sectioned-doctor-row">
                  <div class="doctor-classic-label">Анамнез:</div>
                  <div class="doctor-classic-field">
                    <textarea class="doctor-classic-textarea therapist-textarea--short" name="anamnesis">${escapeHtml(fieldValue("anamnesis"))}</textarea>
                  </div>
                </div>

                ${sections
                  .map((section) => `
                    <div class="sectioned-doctor-section">
                      <div class="therapist-section-label">${escapeHtml(section.title)}</div>
                      <div class="sectioned-doctor-grid ${section.columns === 1 ? "sectioned-doctor-grid--single" : ""}">
                        ${(section.items || [])
                          .map((item) => `
                            <div class="sectioned-doctor-field ${item.type === "textarea" ? "sectioned-doctor-field--full" : ""}">
                              <label>${escapeHtml(item.label)}</label>
                              ${item.type === "textarea"
                                ? `<textarea class="doctor-classic-textarea sectioned-doctor-textarea" name="${escapeHtml(item.key)}">${escapeHtml(fieldValue(item.key))}</textarea>`
                                : `<input class="doctor-classic-input" type="text" name="${escapeHtml(item.key)}" value="${escapeHtml(fieldValue(item.key))}" />`}
                            </div>
                          `)
                          .join("")}
                      </div>
                    </div>
                  `)
                  .join("")}

                <div class="doctor-classic-row sectioned-doctor-row">
                  <div class="doctor-classic-label">Диагноз:</div>
                  <div class="doctor-classic-field">
                    <textarea class="doctor-classic-textarea doctor-classic-textarea--diagnosis" name="diagnosis">${escapeHtml(fieldValue("diagnosis"))}</textarea>
                  </div>
                </div>

                <div class="doctor-classic-row doctor-classic-row--conclusion sectioned-doctor-row">
                  <div class="doctor-classic-label">Заключение:</div>
                  <div class="doctor-classic-field">
                    <div class="doctor-classic-bottom-line sectioned-doctor-bottom-line">
                      <div class="doctor-classic-bottom-item doctor-classic-bottom-item--validity">
                        <label class="doctor-classic-inline-label">Срок:</label>
                        <select class="doctor-classic-select doctor-classic-select--small" name="validity">
                          ${fieldOptions("validity")
                            .map(
                              (option) => `
                                <option value="${escapeHtml(option)}" ${option === fieldValue("validity") ? "selected" : ""}>
                                  ${escapeHtml(option)}
                                </option>
                              `,
                            )
                            .join("")}
                        </select>
                      </div>

                      ${renderClassicRadio("conclusion", fieldValue("conclusion"), fieldOptions("conclusion"))}

                      <div class="doctor-classic-bottom-item doctor-classic-bottom-item--mkb">
                        <label class="doctor-classic-inline-label">МКБ10:</label>
                        <input class="doctor-classic-input doctor-classic-input--mkb" type="text" name="mkb10" value="${escapeHtml(fieldValue("mkb10"))}" />
                      </div>
                    </div>
                  </div>
                </div>

                <div class="doctor-classic-row doctor-classic-row--note sectioned-doctor-row">
                  <div class="doctor-classic-label">Примечание:</div>
                  <div class="doctor-classic-field">
                    <textarea class="doctor-classic-textarea doctor-classic-textarea--note" name="note">${escapeHtml(fieldValue("note"))}</textarea>
                  </div>
                </div>
              </div>

              <div class="doctor-classic-sidebar">
                <button type="submit" class="doctor-classic-sidebtn">ОК</button>
                <button type="button" class="doctor-classic-sidebtn" data-doctor-exam-close>Отмена</button>
                <button type="button" class="doctor-classic-sidebtn doctor-classic-sidebtn--danger" data-doctor-exam-delete>удалить врача</button>
              </div>
            </div>
          </form>
        </div>
      </div>
    `;
  }

  function renderOtolaryngologistClassic(template, exam, client) {
    return renderSectionedClassic(template, exam, client, {
      sections: [
        {
          title: "Объективно:",
          items: [
            { key: "objective", label: "Описание", type: "textarea" },
            { key: "earRight", label: "AD" },
            { key: "earLeft", label: "AS" },
            { key: "op", label: "OP" },
            { key: "vestibular", label: "Вестиб." },
          ],
        },
      ],
    });
  }

  function renderOphthalmologistClassic(template, exam, client) {
    return renderSectionedClassic(template, exam, client, {
      sections: [
        {
          title: "Объективно:",
          items: [
            { key: "visualAcuityRight", label: "Острота зрения OD" },
            { key: "visualAcuityLeft", label: "Острота зрения OS" },
            { key: "visualFieldsRight", label: "Поля зрения OD" },
            { key: "visualFieldsLeft", label: "Поля зрения OS" },
            { key: "colorVision", label: "Цветоощущение" },
            { key: "ocularFundus", label: "Глазное дно" },
          ],
        },
      ],
    });
  }

  function renderUzistClassic(template, exam, client) {
    return renderSectionedClassic(template, exam, client, {
      sections: [
        {
          title: "Исследование:",
          items: [
            { key: "studyName", label: "Исследование" },
            { key: "objective", label: "Описание УЗИ", type: "textarea" },
            { key: "recommendation", label: "Рекомендации", type: "textarea" },
          ],
          columns: 1,
        },
      ],
    });
  }

  function renderSanatoriumChairmanClassic(template, exam, client, chairmanInfo) {
    const fields = exam.fields || {};
    const chairmanType = chairmanInfo.type || "certificate072";
    const fullName = client?.fullName || client?.name || client?.fio || "Клиент";
    const birthDate = fields.birthDate || client?.birthDate || window.formatApiDate?.(client?.rawApiClient?.birth_date) || "";
    const therapistExam = window.getDoctorExam?.(exam.clientId, exam.visitId, "therapist") || null;
    const fieldValue = (key, fallback = "") => String(fields[key] ?? fallback ?? "");
    const textInput = (name, value = "", options = {}) => `
      <input
        class="doctor-classic-input ${escapeHtml(options.className || "")}"
        type="${escapeHtml(options.type || "text")}"
        name="${escapeHtml(name)}"
        value="${escapeHtml(value)}"
        ${options.placeholder ? `placeholder="${escapeHtml(options.placeholder)}"` : ""}
        ${options.readonly ? "readonly" : ""}
        ${options.dateMask ? "data-date-mask" : ""}
      />
    `;
    const textarea = (name, value = "", placeholder = "") => `
      <textarea
        class="doctor-classic-textarea sanatorium-card-textarea"
        name="${escapeHtml(name)}"
        ${placeholder ? `placeholder="${escapeHtml(placeholder)}"` : ""}
      >${escapeHtml(value)}</textarea>
    `;
    const diagnosisRow = (label, diagnosisKey, mkbKey) => `
      <div class="sanatorium-diagnosis-row">
        <label>${escapeHtml(label)}</label>
        ${textInput(diagnosisKey, fieldValue(diagnosisKey))}
        <span>МКБ-10</span>
        ${textInput(mkbKey, fieldValue(mkbKey), { className: "sanatorium-card-input--mkb" })}
      </div>
    `;
    const quickInput = (targetName, value = "", options = {}) => `
      <input
        class="doctor-classic-input sanatorium-quick-input ${escapeHtml(options.className || "")}"
        type="text"
        value="${escapeHtml(value)}"
        data-sanatorium-quick-target="${escapeHtml(targetName)}"
        ${options.placeholder ? `placeholder="${escapeHtml(options.placeholder)}"` : ""}
      />
    `;
    const quickDiagnosisRow = (label, diagnosisKey, mkbKey) => `
      <label class="sanatorium-quick-diagnosis-row">
        <span>${escapeHtml(label)}</span>
        ${quickInput(diagnosisKey, fieldValue(diagnosisKey), { placeholder: "Диагноз" })}
        ${quickInput(mkbKey, fieldValue(mkbKey), {
          className: "sanatorium-card-input--mkb",
          placeholder: "МКБ-10",
        })}
      </label>
    `;
    const accompaniment = fieldValue("accompaniment", "2");
    const treatmentType = fieldValue("treatmentType", "1");
    const chairmanTitle = chairmanInfo.label || template.name;
    const formLabel = chairmanType === "certificate070" ? "070/у" : "072/у";
    const rawClient = client?.rawApiClient || {};
    const chairmanName = fieldValue("chairmanName", exam.doctorName || "");
    const attendingDoctorName = fieldValue("attendingDoctorName", therapistExam?.doctorName || "");

    return `
      <div class="doctor-classic-backdrop" data-doctor-exam-modal>
        <div class="chairman-window sanatorium-chairman-window">
          <div class="doctor-classic-titlebar">
            <div class="doctor-classic-title doctor-classic-title--stacked">
              <span>${escapeHtml(chairmanTitle)}</span>
              <small>Карточка председателя для форм 070/у и 072/у · текущая форма ${escapeHtml(formLabel)}</small>
            </div>
            <button type="button" class="doctor-classic-close" data-doctor-exam-close>×</button>
          </div>

          <form
            class="chairman-form chairman-form--${escapeHtml(chairmanType)} sanatorium-chairman-form"
            data-doctor-exam-form
            data-exam-id="${escapeHtml(exam.id)}"
            data-doctor-role-id="${escapeHtml(template.id)}"
            data-chairman-form-type="${escapeHtml(chairmanType)}"
          >
            <div class="chairman-form-context">
              <strong>${escapeHtml(chairmanTitle)}</strong>
              <span>Поля собраны по рабочему эскизу председателя и сохраняются в осмотр для печати формы ${escapeHtml(formLabel)}.</span>
            </div>

            <details class="sanatorium-quick-entry" open>
              <summary>
                <span>Быстрый ввод</span>
                <small>Поля, выделенные жёлтым на рабочем образце</small>
              </summary>
              <div class="sanatorium-quick-entry__body">
                <label class="sanatorium-quick-subject">
                  <span>Код субъекта РФ</span>
                  ${quickInput("subjectCode", fieldValue("subjectCode"), { placeholder: "Например, 23" })}
                </label>
                <div class="sanatorium-quick-diagnoses">
                  ${quickDiagnosisRow("Основное заболевание", "diagnosis", "mkb10")}
                  ${quickDiagnosisRow("Сопутствующее заболевание", "comorbidDiagnosis", "comorbidMkb10")}
                  ${quickDiagnosisRow("Осложнение основного заболевания", "complicationDiagnosis", "complicationMkb10")}
                  ${quickDiagnosisRow("Причина инвалидности", "disabilityDiagnosis", "disabilityMkb10")}
                  ${quickDiagnosisRow("Диагноз направления", "referralDiagnosis", "referralMkb10")}
                </div>
                <div class="sanatorium-quick-seasons">
                  <span>Рекомендуемый сезон</span>
                  <button type="button" data-sanatorium-quick-season="all">Круглогодично</button>
                  <button type="button" data-sanatorium-quick-season="seasonWinter">Зима</button>
                  <button type="button" data-sanatorium-quick-season="seasonSpring">Весна</button>
                  <button type="button" data-sanatorium-quick-season="seasonSummer">Лето</button>
                  <button type="button" data-sanatorium-quick-season="seasonAutumn">Осень</button>
                </div>
              </div>
            </details>

            <div class="sanatorium-patient-strip">
              <label><span>Дата рождения</span>${textInput("birthDate", birthDate, { dateMask: true })}</label>
              <label class="sanatorium-patient-strip__fio"><span>Ф.И.О.</span>${textInput("patientFullName", fullName, { readonly: true })}</label>
              <div class="sanatorium-patient-strip__flags">
                ${renderCheckboxField("hasGlasses", !!fields.hasGlasses, "очки")}
                ${renderCheckboxField("hasHearingAid", !!fields.hasHearingAid, "слуховой аппарат")}
              </div>
            </div>

            <label class="sanatorium-wide-field"><span>Медицинские требования</span>${textarea("medicalRequirements", fieldValue("medicalRequirements"))}</label>

            <div class="sanatorium-chairman-grid">
              <section class="sanatorium-card-page">
                <h3>Пациент и право на социальную поддержку</h3>
                <div class="sanatorium-field-grid sanatorium-field-grid--two">
                  <label><span>Полис ОМС</span>${textInput("omsPolicy", fieldValue("omsPolicy", rawClient.oms_policy || ""))}</label>
                  <label><span>СНИЛС</span>${textInput("snils", fieldValue("snils", rawClient.snils || client?.snils || ""))}</label>
                </div>
                <label class="sanatorium-wide-field sanatorium-wide-field--compact"><span>Наименование страховой медицинской организации</span>${textInput("insuranceOrganization", fieldValue("insuranceOrganization"))}</label>

                <div class="sanatorium-subsection">
                  <h4>Документ, подтверждающий право на набор социальных услуг</h4>
                  <div class="sanatorium-field-grid sanatorium-field-grid--three">
                    <label><span>Серия</span>${textInput("benefitDocumentSeries", fieldValue("benefitDocumentSeries"))}</label>
                    <label><span>Номер</span>${textInput("benefitDocumentNumber", fieldValue("benefitDocumentNumber"))}</label>
                    <label><span>Дата выдачи</span>${textInput("benefitDocumentIssueDate", fieldValue("benefitDocumentIssueDate"), { dateMask: true })}</label>
                  </div>
                </div>

                <div class="sanatorium-subsection sanatorium-subsection--accent">
                  <h4>Данные для санаторно-курортной карты 072/у</h4>
                  <label class="sanatorium-wide-field sanatorium-wide-field--compact"><span>Наименование санаторно-курортной организации</span>${textInput("sanatoriumName", fieldValue("sanatoriumName"))}</label>
                  <div class="sanatorium-field-grid sanatorium-field-grid--two">
                    <label><span>ОГРН организации</span>${textInput("sanatoriumOgrn", fieldValue("sanatoriumOgrn"))}</label>
                    <label><span>Номер путевки</span>${textInput("voucherNumber", fieldValue("voucherNumber"))}</label>
                  </div>
                  <div class="sanatorium-course-grid">
                    <label><span>Период с</span>${textInput("treatmentStartDate", fieldValue("treatmentStartDate"), { dateMask: true })}</label>
                    <label><span>по</span>${textInput("treatmentEndDate", fieldValue("treatmentEndDate"), { dateMask: true })}</label>
                    <label><span>Курс, дней</span>${textInput("treatmentDurationDays", fieldValue("treatmentDurationDays"), { type: "number" })}</label>
                  </div>
                </div>

                <div class="sanatorium-subsection">
                  <h4>Диагнозы</h4>
                  ${diagnosisRow("Основное заболевание", "diagnosis", "mkb10")}
                  ${diagnosisRow("Сопутствующие заболевания", "comorbidDiagnosis", "comorbidMkb10")}
                  ${diagnosisRow("Осложнение основного заболевания", "complicationDiagnosis", "complicationMkb10")}
                  ${diagnosisRow("Заболевание — причина инвалидности", "disabilityDiagnosis", "disabilityMkb10")}
                </div>

                <label class="sanatorium-wide-field"><span>Жалобы</span>${textarea("complaints", fieldValue("complaints"))}</label>
                <label class="sanatorium-wide-field"><span>Анамнез заболевания</span>${textarea("anamnesis", fieldValue("anamnesis"))}</label>
                <label class="sanatorium-wide-field">
                  <span>Данные клинических, лабораторных, рентгенологических и других исследований (с датами)</span>
                  ${textarea("researchResults", fieldValue("researchResults"), "ОАК от …\nБ/Х: глюкоза …; холестерин …\nОАМ от …\nФЛГ от …\nЭКГ от …")}
                </label>
              </section>

              <section class="sanatorium-card-page sanatorium-card-page--decision">
                <h3>Направление и заключение 070/у</h3>
                <div class="sanatorium-code-grid">
                  <label><span>Код субъекта РФ</span>${textInput("subjectCode", fieldValue("subjectCode"))}</label>
                  <label><span>Климат в месте проживания (код)</span>${textInput("climateCode", fieldValue("climateCode"))}</label>
                  <label><span>Климатический фактор (код)</span>${textInput("climateFactorCode", fieldValue("climateFactorCode"))}</label>
                  <label><span>Код меры социальной поддержки</span>${textInput("supportMeasureCode", fieldValue("supportMeasureCode"))}</label>
                </div>

                <fieldset class="sanatorium-radio-fieldset">
                  <legend>Сопровождение</legend>
                  <label><input type="radio" name="accompaniment" value="1" ${accompaniment === "1" ? "checked" : ""} /> Да — 1</label>
                  <label><input type="radio" name="accompaniment" value="2" ${accompaniment !== "1" ? "checked" : ""} /> Нет — 2</label>
                </fieldset>

                <label class="sanatorium-wide-field"><span>Диагноз заболевания, для лечения которого пациент направляется в санаторно-курортную организацию</span>${textarea("referralDiagnosis", fieldValue("referralDiagnosis", fieldValue("diagnosis")))}</label>
                <label class="sanatorium-wide-field sanatorium-wide-field--compact"><span>МКБ-10 диагноза направления</span>${textInput("referralMkb10", fieldValue("referralMkb10", fieldValue("mkb10")))}</label>
                <label class="sanatorium-wide-field sanatorium-wide-field--compact"><span>Предпочтительное место лечения</span>${textInput("preferredTreatmentPlace", fieldValue("preferredTreatmentPlace", fieldValue("sanatoriumName")))}</label>

                <fieldset class="sanatorium-season-fieldset">
                  <legend>Рекомендуемые сезоны лечения</legend>
                  ${renderCheckboxField("seasonWinter", !!fields.seasonWinter, "Зима")}
                  ${renderCheckboxField("seasonSpring", !!fields.seasonSpring, "Весна")}
                  ${renderCheckboxField("seasonSummer", !!fields.seasonSummer, "Лето")}
                  ${renderCheckboxField("seasonAutumn", !!fields.seasonAutumn, "Осень")}
                </fieldset>

                <label class="sanatorium-wide-field sanatorium-wide-field--compact">
                  <span>Условия лечения</span>
                  <select class="doctor-classic-select" name="treatmentType">
                    <option value="1" ${treatmentType !== "2" ? "selected" : ""}>1 — в условиях санаторно-курортной организации</option>
                    <option value="2" ${treatmentType === "2" ? "selected" : ""}>2 — амбулаторно</option>
                  </select>
                </label>

                <label class="sanatorium-wide-field"><span>Дополнительные сведения</span>${textarea("additionalInformation", fieldValue("additionalInformation"))}</label>

                <div class="sanatorium-subsection sanatorium-signers">
                  <h4>Подписи</h4>
                  <label><span>Лечащий врач</span>${textInput("attendingDoctorName", attendingDoctorName)}</label>
                  <label><span>Должность врача-специалиста</span>${textInput("attendingDoctorPosition", fieldValue("attendingDoctorPosition"))}</label>
                  <label><span>Заведующий отделением / председатель врачебной комиссии</span>${textInput("chairmanName", chairmanName)}</label>
                  ${renderCheckboxField("stampApplied", !!fields.stampApplied, "Печать поставлена")}
                </div>

                <label class="sanatorium-wide-field"><span>Примечание</span>${textarea("note", fieldValue("note"))}</label>
              </section>
            </div>

            <div class="chairman-actions sanatorium-chairman-actions">
              <button type="submit" class="chairman-action-btn">Сохранить</button>
              <button type="button" class="chairman-action-btn" data-doctor-exam-close>Отмена</button>
            </div>
          </form>
        </div>
      </div>
    `;
  }

  function renderCertificate082ChairmanClassic(template, exam, client, chairmanInfo) {
    const fields = exam.fields || {};
    const fullName = client?.fullName || client?.name || client?.fio || "Клиент";
    const birthDate = fields.birthDate || client?.birthDate || window.formatApiDate?.(client?.rawApiClient?.birth_date) || "";
    const healthOptions = [
      "Здоров",
      "Не здоров",
      "Годен",
      "Не годен",
      "Практически здоров",
      "I группа здоровья",
      "II группа здоровья",
      "III группа здоровья",
      "IV группа здоровья",
      "V группа здоровья",
    ];
    const currentHealthStatus = String(fields.healthStatus || fields.conclusion || "Здоров");
    const selectOptions = healthOptions.includes(currentHealthStatus)
      ? healthOptions
      : [currentHealthStatus, ...healthOptions];
    const resultRow = (label, name, value = "") => `
      <label class="certificate082-result-row">
        <span>${escapeHtml(label)}</span>
        <textarea class="doctor-classic-textarea certificate082-result-input" name="${escapeHtml(name)}">${escapeHtml(value)}</textarea>
      </label>
    `;

    return `
      <div class="doctor-classic-backdrop" data-doctor-exam-modal>
        <div class="chairman-window certificate082-chairman-window">
          <div class="doctor-classic-titlebar">
            <div class="doctor-classic-title doctor-classic-title--stacked">
              <span>${escapeHtml(chairmanInfo.label || "Председатель: справка 082у")}</span>
              <small>${escapeHtml(chairmanInfo.templateName || "Справка 082у")}</small>
            </div>
            <button type="button" class="doctor-classic-close" data-doctor-exam-close>×</button>
          </div>

          <form
            class="chairman-form chairman-form--certificate082 certificate082-chairman-form"
            data-doctor-exam-form
            data-exam-id="${escapeHtml(exam.id)}"
            data-doctor-role-id="${escapeHtml(template.id)}"
            data-chairman-form-type="certificate082"
          >
            <div class="certificate082-patient-row">
              <label>
                <span>Дата рождения</span>
                <input class="doctor-classic-input" type="text" name="birthDate" data-date-mask value="${escapeHtml(birthDate)}" />
              </label>
              <label class="certificate082-patient-row__fio">
                <span>Ф.И.О.</span>
                <input class="doctor-classic-input doctor-classic-input--fio" type="text" name="patientFullName" value="${escapeHtml(fullName)}" readonly />
              </label>
              <div class="certificate082-patient-flags">
                ${renderCheckboxField("hasGlasses", !!fields.hasGlasses, "очки")}
                ${renderCheckboxField("hasHearingAid", !!fields.hasHearingAid, "слуховой аппарат")}
              </div>
            </div>

            <label class="certificate082-requirements">
              <span>Мед. требования</span>
              <div class="chairman-requirements-control">
                <textarea class="doctor-classic-textarea certificate082-requirements__input" name="medicalRequirements" data-medical-requirements-input>${escapeHtml(fields.medicalRequirements ?? "")}</textarea>
                <button type="button" class="chairman-requirements-picker-btn" data-medical-requirements-open title="Выбрать из сохранённых" aria-label="Выбрать из сохранённых">...</button>
              </div>
            </label>

            <section class="certificate082-results" aria-label="Результаты обследований">
              ${resultRow("ФЛГ", "fluorography", fields.fluorography ?? "")}
              ${resultRow("ЭКГ", "ekgConclusion", fields.ekgConclusion || fields.ekg || "")}
              ${resultRow("СПИД", "hivResult", fields.hivResult ?? "")}
              ${resultRow("Гепатиты", "hepatitisResult", fields.hepatitisResult ?? "")}
              ${resultRow("Страна", "country", fields.country ?? "")}
            </section>

            <label class="certificate082-health-status">
              <span>По состоянию здоровья</span>
              <select class="doctor-classic-select" name="healthStatus">
                ${selectOptions.map((option) => `<option value="${escapeHtml(option)}" ${option === currentHealthStatus ? "selected" : ""}>${escapeHtml(option)}</option>`).join("")}
              </select>
            </label>

            <input type="hidden" name="conclusion" value="${escapeHtml(currentHealthStatus)}" data-certificate082-conclusion />

            <div class="chairman-actions certificate082-actions">
              <button type="submit" class="chairman-action-btn">Сохранить</button>
              <button type="button" class="chairman-action-btn" data-doctor-exam-close>Отмена</button>
            </div>
          </form>
        </div>
      </div>
    `;
  }

  function renderChairmanClassic(template, exam, client) {
    const fields = exam.fields || {};
    const fullName = client?.fullName || client?.name || client?.fio || "Клиент";
    const birthDate = fields.birthDate || client?.birthDate || window.formatApiDate?.(client?.rawApiClient?.birth_date) || "";
    const emptyLegacyValue = (value, legacyValues = []) => {
      const normalized = String(value ?? "");
      return legacyValues.includes(normalized) ? "" : normalized;
    };
    const chairmanInfo = window.getChairmanFormInfo?.(exam, client) || {};
    const chairmanType = chairmanInfo.type || "default";
    if (["certificate070", "certificate072"].includes(chairmanType)) {
      return renderSanatoriumChairmanClassic(template, exam, client, chairmanInfo);
    }
    if (chairmanType === "certificate082") {
      return renderCertificate082ChairmanClassic(template, exam, client, chairmanInfo);
    }
    const keepEkgFieldsManual = ["lmk", "prof"].includes(chairmanType);
    const ekgValue = emptyLegacyValue(fields.ekg, ['Медицинский центр ООО "ЦМО "ЮЛМЕД" ЭКГ от 07.04.2025']);
    const examDateValue = fields.examDate ?? "";
    const ekgDate = extractRuDate(ekgValue) || extractRuDate(examDateValue);
    const rawStoredEkgConclusionValue = emptyLegacyValue(fields.ekgConclusion, [
      "Ритм синусовый, ЧСС , нормальная электрическая позиция сердца, ЭКГ-комплексы без особенностей от 07.04.2025",
    ]);
    const storedEkgConclusionValue =
      chairmanType === "guard" &&
      String(rawStoredEkgConclusionValue).trim().startsWith(`${AUTO_EKG_CONCLUSION_PREFIX} от `)
        ? ""
        : rawStoredEkgConclusionValue;
    const ekgConclusionValue =
      keepEkgFieldsManual || String(storedEkgConclusionValue).trim()
        ? storedEkgConclusionValue
        : buildAutoEkgConclusion(ekgDate, chairmanType);
    const noteValue = emptyLegacyValue(fields.note, ["прио/"]);
    const fieldOptions = (key) => template.fields.find((field) => field.key === key)?.options || [];
    const isDriverChairmanFlow = chairmanInfo.printMode === "driver-flow";
    const hideDriverDetails = [
      "sport",
      "pool",
      "gto",
      "certificate072",
      "certificate086",
      "certificate095",
      "semt196",
      "gsu",
      "gostaina",
      "guard",
    ].includes(chairmanType);
    const renderChairmanSelect = (name, value, options) => {
      const currentValue = String(value ?? "");
      const selectOptions = currentValue && !options.includes(currentValue) ? [...options, currentValue] : options;

      return `
        <select class="doctor-classic-select" name="${escapeHtml(name)}">
          ${selectOptions
            .map(
              (option) => `
                <option value="${escapeHtml(option)}" ${option === currentValue ? "selected" : ""}>
                  ${escapeHtml(option)}
                </option>
              `,
            )
            .join("")}
        </select>
      `;
    };

    const chairmanTitle = chairmanInfo.label || template.name;
    const templateLabel = chairmanInfo.templateName || "шаблон будет выбран по услуге";

    return `
      <div class="doctor-classic-backdrop" data-doctor-exam-modal>
        <div class="chairman-window">
          <div class="doctor-classic-titlebar">
            <div class="doctor-classic-title doctor-classic-title--stacked">
              <span>${escapeHtml(chairmanTitle)}</span>
              <small>${escapeHtml(templateLabel)}</small>
            </div>
            <button type="button" class="doctor-classic-close" data-doctor-exam-close>×</button>
          </div>

          <form
            class="chairman-form chairman-form--${escapeHtml(chairmanType)}"
            data-doctor-exam-form
            data-exam-id="${escapeHtml(exam.id)}"
            data-doctor-role-id="${escapeHtml(template.id)}"
            data-chairman-form-type="${escapeHtml(chairmanType)}"
          >
            <div class="chairman-form-context">
              <strong>${escapeHtml(chairmanTitle)}</strong>
              <span>${escapeHtml(chairmanInfo.note || "")}</span>
            </div>

            <div class="chairman-top">
              <div class="chairman-top-left">
                <div class="chairman-mini-row">
                  <label class="chairman-mini-label">дата рождения</label>
                  <input class="doctor-classic-input" type="text" name="birthDate" data-date-mask value="${escapeHtml(birthDate)}" />
                </div>
              </div>

              <div class="chairman-top-main">
                <div class="chairman-main-row">
                  <label class="chairman-main-label">Ф.И.О.</label>
                  <input class="doctor-classic-input doctor-classic-input--fio" type="text" name="patientFullName" value="${escapeHtml(fullName)}" readonly />
                </div>

                <div class="chairman-main-row chairman-main-row--requirements">
                  <label class="chairman-main-label">Мед. требования:</label>
                  <div class="chairman-requirements-control">
                    <textarea class="doctor-classic-textarea chairman-textarea chairman-textarea--big" name="medicalRequirements" data-medical-requirements-input>${escapeHtml(fields.medicalRequirements ?? "")}</textarea>
                    <button
                      type="button"
                      class="chairman-requirements-picker-btn"
                      data-medical-requirements-open
                      title="Выбрать из сохраненных"
                      aria-label="Выбрать из сохраненных"
                    >...</button>
                  </div>
                </div>
              </div>

              <div class="chairman-top-right">
                ${renderCheckboxField("hasGlasses", !!fields.hasGlasses, "очки")}
                ${renderCheckboxField("hasHearingAid", !!fields.hasHearingAid, "слух аппарат")}
              </div>
            </div>

            <div class="chairman-middle">
              <div class="chairman-row">
                <label class="chairman-row-label">ЭКГ:</label>
                <input class="doctor-classic-input" type="text" name="ekg" value="${escapeHtml(ekgValue)}" />
              </div>

              <div class="chairman-row chairman-row--ekg-conclusion">
                <label class="chairman-row-label">Заключение ЭКГ:</label>
                <textarea class="doctor-classic-textarea chairman-textarea chairman-textarea--small" name="ekgConclusion">${escapeHtml(ekgConclusionValue)}</textarea>
                <div class="chairman-blood">
                  <div class="chairman-blood-row">
                    <label>Группа крови</label>
                    ${renderChairmanSelect("bloodGroup", fields.bloodGroup ?? "0 (I)", fieldOptions("bloodGroup"))}
                  </div>
                  <div class="chairman-blood-row">
                    <label>резус-фактор</label>
                    ${renderChairmanSelect("rhesusFactor", fields.rhesusFactor ?? "Rh(+)", fieldOptions("rhesusFactor"))}
                  </div>
                  <div class="chairman-blood-row">
                    <label>кровь - откуда данные</label>
                    <input class="doctor-classic-input" type="text" name="bloodSource" value="${escapeHtml(fields.bloodSource ?? "")}" />
                  </div>
                </div>
              </div>

              <div class="chairman-row">
                <label class="chairman-row-label">Флюорография:</label>
                <input class="doctor-classic-input" type="text" name="fluorography" value="${escapeHtml(fields.fluorography ?? "")}" />
              </div>

              <div class="chairman-flags">
                ${renderCheckboxField("vaccinationRefusal", !!fields.vaccinationRefusal, "Подписан отказ от прививок")}
                ${renderCheckboxField("needsKekReferral", !!fields.needsKekReferral, "Нуждается в направлении на КЭК")}
              </div>

              <div class="chairman-meta-grid">
                <div class="chairman-meta-item">
                  <label>Дата экзамена:</label>
                  <input class="doctor-classic-input" type="text" name="examDate" value="${escapeHtml(examDateValue)}" />
                </div>
                <div class="chairman-meta-item">
                  <label>№ Логотипа:</label>
                  <input class="doctor-classic-input" type="text" name="logotypeNumber" value="${escapeHtml(fields.logotypeNumber ?? "")}" />
                </div>
                <div class="chairman-meta-item">
                  <label>№ Атт.комиссии:</label>
                  <input class="doctor-classic-input" type="text" name="commissionNumber" value="${escapeHtml(fields.commissionNumber ?? "")}" />
                </div>
                <div class="chairman-meta-item">
                  <label>МКБ10:</label>
                  <input class="doctor-classic-input" type="text" name="mkb10" value="${escapeHtml(fields.mkb10 ?? "")}" />
                </div>
              </div>

              <div class="chairman-row chairman-row--diagnosis">
                <label class="chairman-row-label">Диагноз:</label>
                <textarea class="doctor-classic-textarea chairman-textarea chairman-textarea--diagnosis" name="diagnosis">${escapeHtml(fields.diagnosis ?? "")}</textarea>
              </div>
            </div>

            <div class="chairman-bottom">
              <div class="chairman-conclusion-left">
                <div class="chairman-conclusion-title">Заключение:</div>

                <div class="chairman-inline-controls">
                  <label>Срок:</label>
                  <select class="doctor-classic-select doctor-classic-select--small" name="validity">
                    ${(template.fields.find((f) => f.key === "validity")?.options || [])
                      .map(
                        (option) => `
                          <option value="${escapeHtml(option)}" ${option === (fields.validity ?? "") ? "selected" : ""}>
                            ${escapeHtml(option)}
                          </option>
                        `,
                      )
                      .join("")}
                  </select>

                  <label>орган.</label>
                  <select class="doctor-classic-select" name="organ">
                    ${(template.fields.find((f) => f.key === "organ")?.options || [])
                      .map(
                        (option) => `
                          <option value="${escapeHtml(option)}" ${option === (fields.organ ?? "") ? "selected" : ""}>
                            ${escapeHtml(option)}
                          </option>
                        `,
                      )
                      .join("")}
                  </select>
                </div>

                <div class="doctor-classic-radio-group chairman-radio-group">
                  <label class="doctor-classic-radio">
                    <input type="radio" name="conclusion" value="Годен" ${(fields.conclusion ?? "Годен") === "Годен" ? "checked" : ""} />
                    <span>Годен</span>
                  </label>
                  <label class="doctor-classic-radio">
                    <input type="radio" name="conclusion" value="Не годен" ${(fields.conclusion ?? "") === "Не годен" ? "checked" : ""} />
                    <span>Не годен</span>
                  </label>
                </div>
              </div>

              ${hideDriverDetails ? "" : `
              <div class="chairman-conclusion-right">
                <div class="chairman-columns">
                  <div class="chairman-column">
                    <div class="chairman-column-title">Категории</div>
                    ${renderCheckboxField("categoryA", !!fields.categoryA, "A")}
                    ${renderCheckboxField("categoryB", !!fields.categoryB, "B")}
                    ${renderCheckboxField("categoryC", !!fields.categoryC, "C")}
                    ${renderCheckboxField("categoryD", !!fields.categoryD, "D")}
                    ${renderCheckboxField("categoryBE", !!(fields.categoryBE || fields.categoryE), "BE")}
                    ${renderCheckboxField("categoryCE", !!(fields.categoryCE || fields.categoryE), "CE")}
                    ${renderCheckboxField("categoryDE", !!(fields.categoryDE || fields.categoryE), "DE")}
                    ${renderCheckboxField("categoryTram", !!fields.categoryTram, "Tm")}
                    ${renderCheckboxField("categoryTrolleybus", !!fields.categoryTrolleybus, "Tb")}
                    ${renderCheckboxField("categoryM", !!fields.categoryM, "M")}
                    ${renderCheckboxField("categoryA1", !!fields.categoryA1, "A1")}
                    ${renderCheckboxField("categoryB1", !!fields.categoryB1, "B1")}
                    ${renderCheckboxField("categoryC1", !!fields.categoryC1, "C1")}
                    ${renderCheckboxField("categoryD1", !!fields.categoryD1, "D1")}
                    ${renderCheckboxField("categoryC1E", !!fields.categoryC1E, "C1E")}
                    ${renderCheckboxField("categoryD1E", !!fields.categoryD1E, "D1E")}
                    ${renderCheckboxField("categoryTractor", !!fields.categoryTractor, "тракторы (п.8.)")}
                    ${renderCheckboxField("categoryBoat", !!fields.categoryBoat, "лайнеры и катера (п.9)")}
                    ${isDriverChairmanFlow ? "" : renderCheckboxField("categorySailing", !!fields.categorySailing, "парусный спорт")}
                  </div>

                  <div class="chairman-column">
                    <div class="chairman-column-title">Показания:</div>
                    ${renderCheckboxField("indicationManual", !!fields.indicationManual, "с ручн.управлением")}
                    ${renderCheckboxField("indicationAutomatic", !!fields.indicationAutomatic, "с автоматом")}
                    ${renderCheckboxField("indicationAcoustic", !!fields.indicationAcoustic, "с акустикой")}
                    ${renderCheckboxField("indicationGlasses", !!fields.indicationGlasses, "очки/линзы")}
                    ${renderCheckboxField("indicationHearingAid", !!fields.indicationHearingAid, "слуховой аппарат")}
                    ${renderCheckboxField("indicationNoHiring", !!fields.indicationNoHiring, "без найма")}
                    ${renderCheckboxField("indicationOneYear", !!fields.indicationOneYear, "на год")}
                  </div>

                  <div class="chairman-column">
                    <div class="chairman-column-title">Ограничения:</div>
                    ${renderCheckboxField("restrictionAM", !!fields.restrictionAM, "AM")}
                    ${renderCheckboxField("restrictionBBE", !!fields.restrictionBBE, "BBE")}
                    ${renderCheckboxField("restrictionCCE", !!fields.restrictionCCE, "CCE")}
                    ${renderCheckboxField("restrictionNoHands", !!fields.restrictionNoHands, "Без руки")}
                    ${renderCheckboxField("restrictionNoLegs", !!fields.restrictionNoLegs, "Без ноги")}
                  </div>
                </div>
              </div>
              `}

              <div class="chairman-actions">
                <button type="submit" class="chairman-action-btn">Сохранить</button>
                <button type="button" class="chairman-action-btn" data-doctor-exam-close>Отмена</button>
              </div>
            </div>

            ${isDriverChairmanFlow || hideDriverDetails ? "" : `
              <div class="chairman-footer">
                ${renderCheckboxField("periodicProf", !!fields.periodicProf, "Периодический проф")}
                ${renderCheckboxField("stampApplied", !!fields.stampApplied, "Печать поставлена")}
              </div>
            `}

            <div class="chairman-note">
              <label>Примечание:</label>
              <textarea class="doctor-classic-textarea chairman-textarea chairman-textarea--note" name="note">${escapeHtml(noteValue)}</textarea>
            </div>
          </form>
        </div>
      </div>
    `;
  }

    function renderPsychiatristClassic(template, exam, client) {
    const fields = exam.fields || {};
    const fullName = client?.fullName || client?.name || client?.fio || "Клиент";
    const birthDate = fields.birthDate || client?.birthDate || "";
    const address = fields.address || client?.address || "";
    const activeTab = fields.tab || "Анамнез";

    function tabClass(tabName) {
      return activeTab === tabName ? "psy-tab psy-tab--active" : "psy-tab";
    }

    return `
      <div class="doctor-classic-backdrop" data-doctor-exam-modal>
        <div class="psy-window">
          <div class="doctor-classic-titlebar">
            <div class="doctor-classic-title">${escapeHtml(template.name)}</div>
            <button type="button" class="doctor-classic-close" data-doctor-exam-close>×</button>
          </div>

          <form
            class="psy-form"
            data-doctor-exam-form
            data-exam-id="${escapeHtml(exam.id)}"
            data-doctor-role-id="${escapeHtml(template.id)}"
          >
            <div class="psy-top">
              <div class="psy-row psy-row--fio">
                <div class="psy-label">Ф.И.О.</div>
                <div class="psy-field-main">
                  <input
                    class="doctor-classic-input doctor-classic-input--fio"
                    type="text"
                    name="patientFullName"
                    value="${escapeHtml(fullName)}"
                    readonly
                  />
                </div>
              </div>

              <div class="psy-row psy-row--meta-grid">
                <div class="psy-meta-item">
                  <label class="psy-small-label">Дата рождения</label>
                  <input
                    class="doctor-classic-input"
                    type="text"
                    name="birthDate"
                    value="${escapeHtml(birthDate)}"
                  />
                </div>

                <div class="psy-meta-item psy-meta-item--address">
                  <label class="psy-small-label">Адрес</label>
                  <input
                    class="doctor-classic-input"
                    type="text"
                    name="address"
                    value="${escapeHtml(address)}"
                  />
                </div>

                <div class="psy-meta-item">
                  <label class="psy-small-label">№ п/п</label>
                  <input
                    class="doctor-classic-input"
                    type="text"
                    name="serialNumber"
                    value="${escapeHtml(fields.serialNumber ?? "")}"
                  />
                </div>
              </div>

              <div class="psy-row psy-row--complaints">
                <div class="psy-complaints-left">
                  <label class="psy-small-label">Жалобы</label>
                  <select class="doctor-classic-select" name="complaintsPreset">
                    ${(template.fields.find((f) => f.key === "complaintsPreset")?.options || [])
                      .map(
                        (option) => `
                          <option value="${escapeHtml(option)}" ${
                            option === (fields.complaintsPreset ?? "") ? "selected" : ""
                          }>
                            ${escapeHtml(option)}
                          </option>
                        `,
                      )
                      .join("")}
                  </select>
                </div>

                <div class="psy-complaints-right">
                  <label class="psy-small-label">Текст жалоб</label>
                  <input
                    class="doctor-classic-input"
                    type="text"
                    name="complaints"
                    value="${escapeHtml(fields.complaints ?? "")}"
                  />
                </div>
              </div>

              <div class="psy-row psy-row--tabs">
                <div class="psy-tabs">
                  <button type="button" class="${tabClass("Анамнез")}" data-psy-tab="Анамнез">Анамнез</button>
                  <button type="button" class="${tabClass("Психическое состояние")}" data-psy-tab="Психическое состояние">Психическое состояние</button>
                  <button type="button" class="${tabClass("Алкоголь")}" data-psy-tab="Алкоголь">Алкоголь</button>
                  <button type="button" class="${tabClass("Диагноз")}" data-psy-tab="Диагноз">Диагноз</button>
                  <input type="hidden" name="tab" value="${escapeHtml(activeTab)}" />
                </div>
              </div>
            </div>

            <div class="psy-main-layout">
              <div class="psy-content">
                <div class="psy-body">
                  <div class="psy-panel ${activeTab === "Анамнез" ? "" : "hidden"}" data-psy-panel="Анамнез">
                    <div class="psy-grid psy-grid--two">
                      <div class="psy-field">
                        <label>Наследственность</label>
                        <input
                          class="doctor-classic-input"
                          type="text"
                          name="anamnesisHeredity"
                          value="${escapeHtml(fields.anamnesisHeredity ?? "")}"
                        />
                      </div>

                      <div class="psy-field">
                        <label>Перенесенные травмы, заболевания</label>
                        <input
                          class="doctor-classic-input"
                          type="text"
                          name="anamnesisDiseases"
                          value="${escapeHtml(fields.anamnesisDiseases ?? "")}"
                        />
                      </div>

                      <div class="psy-field">
                        <label>Номер справки ПНД</label>
                        <input
                          class="doctor-classic-input"
                          type="text"
                          name="anamnesisPndNumber"
                          value="${escapeHtml(fields.anamnesisPndNumber ?? "")}"
                        />
                      </div>

                      <div class="psy-field">
                        <label>Номер справки НД</label>
                        <input
                          class="doctor-classic-input"
                          type="text"
                          name="anamnesisNdNumber"
                          value="${escapeHtml(fields.anamnesisNdNumber ?? "")}"
                        />
                      </div>
                    </div>
                  </div>

                  <div class="psy-panel ${activeTab === "Психическое состояние" ? "" : "hidden"}" data-psy-panel="Психическое состояние">
                    <div class="psy-grid psy-grid--two">
                      <div class="psy-field">
                        <label>Ориентировка</label>
                        <input class="doctor-classic-input" type="text" name="mentalOrientation" value="${escapeHtml(fields.mentalOrientation ?? "")}" />
                      </div>

                      <div class="psy-field">
                        <label>Настроение</label>
                        <input class="doctor-classic-input" type="text" name="mentalMood" value="${escapeHtml(fields.mentalMood ?? "")}" />
                      </div>

                      <div class="psy-field">
                        <label>На вопросы отвечает</label>
                        <input class="doctor-classic-input" type="text" name="mentalAnswers" value="${escapeHtml(fields.mentalAnswers ?? "")}" />
                      </div>

                      <div class="psy-field">
                        <label>Галлюцинации</label>
                        <input class="doctor-classic-input" type="text" name="mentalHallucinations" value="${escapeHtml(fields.mentalHallucinations ?? "")}" />
                      </div>

                      <div class="psy-field">
                        <label>Память</label>
                        <input class="doctor-classic-input" type="text" name="mentalMemory" value="${escapeHtml(fields.mentalMemory ?? "")}" />
                      </div>

                      <div class="psy-field">
                        <label>Интеллект</label>
                        <input class="doctor-classic-input" type="text" name="mentalIntellect" value="${escapeHtml(fields.mentalIntellect ?? "")}" />
                      </div>

                      <div class="psy-field psy-field--full">
                        <label>Примечание</label>
                        <textarea class="doctor-classic-textarea psy-textarea" name="mentalNote">${escapeHtml(fields.mentalNote ?? "")}</textarea>
                      </div>
                    </div>
                  </div>

                  <div class="psy-panel ${activeTab === "Алкоголь" ? "" : "hidden"}" data-psy-panel="Алкоголь">
                    <div class="psy-grid psy-grid--two">
                      <div class="psy-field">
                        <label>Как часто алкоголизируется</label>
                        <input class="doctor-classic-input" type="text" name="alcoholFrequency" value="${escapeHtml(fields.alcoholFrequency ?? "")}" />
                      </div>

                      <div class="psy-field">
                        <label>Состояние языка</label>
                        <input class="doctor-classic-input" type="text" name="alcoholTongue" value="${escapeHtml(fields.alcoholTongue ?? "")}" />
                      </div>

                      <div class="psy-field">
                        <label>Какие напитки предпочитает</label>
                        <input class="doctor-classic-input" type="text" name="alcoholPreference" value="${escapeHtml(fields.alcoholPreference ?? "")}" />
                      </div>

                      <div class="psy-field">
                        <label>Зрачки</label>
                        <input class="doctor-classic-input" type="text" name="alcoholPupils" value="${escapeHtml(fields.alcoholPupils ?? "")}" />
                      </div>

                      <div class="psy-field">
                        <label>Макс. количество выпитого за раз</label>
                        <input class="doctor-classic-input" type="text" name="alcoholMaxDose" value="${escapeHtml(fields.alcoholMaxDose ?? "")}" />
                      </div>

                      <div class="psy-field">
                        <label>Реакция на свет</label>
                        <input class="doctor-classic-input" type="text" name="alcoholLightReaction" value="${escapeHtml(fields.alcoholLightReaction ?? "")}" />
                      </div>

                      <div class="psy-field">
                        <label>Самочувствие на след. день</label>
                        <input class="doctor-classic-input" type="text" name="alcoholNextDay" value="${escapeHtml(fields.alcoholNextDay ?? "")}" />
                      </div>

                      <div class="psy-field">
                        <label>Тремор</label>
                        <input class="doctor-classic-input" type="text" name="alcoholTremor" value="${escapeHtml(fields.alcoholTremor ?? "")}" />
                      </div>

                      <div class="psy-field psy-field--full">
                        <label>Были ли случаи употребления спиртного несколько дней подряд</label>
                        <input class="doctor-classic-input" type="text" name="alcoholMultiDay" value="${escapeHtml(fields.alcoholMultiDay ?? "")}" />
                      </div>

                      <div class="psy-field psy-field--full">
                        <label>Употреблял ли психотропные препараты</label>
                        <input class="doctor-classic-input" type="text" name="alcoholPsychotropic" value="${escapeHtml(fields.alcoholPsychotropic ?? "")}" />
                      </div>

                      <div class="psy-field psy-field--full">
                        <label>Употреблял ли наркотики</label>
                        <input class="doctor-classic-input" type="text" name="alcoholDrugs" value="${escapeHtml(fields.alcoholDrugs ?? "")}" />
                      </div>
                    </div>
                  </div>

                  <div class="psy-panel ${activeTab === "Диагноз" ? "" : "hidden"}" data-psy-panel="Диагноз">
                    <div class="psy-grid psy-grid--single">
                      <div class="psy-field">
                        <label>Диагноз</label>
                        <input
                          class="doctor-classic-input"
                          type="text"
                          name="diagnosisShort"
                          value="${escapeHtml(fields.diagnosisShort ?? "")}"
                        />
                      </div>

                      <div class="psy-field">
                        <label>Выдано заключение</label>
                        <textarea class="doctor-classic-textarea psy-issued-textarea" name="issuedConclusion">${escapeHtml(fields.issuedConclusion ?? "")}</textarea>
                      </div>

                      <div class="psy-footer-box">
                        <div class="psy-footer-title">Заключение</div>

                        <div class="psy-conclusion-inline">
                          <label>Срок:</label>
                          <select class="doctor-classic-select doctor-classic-select--small" name="validity">
                            ${(template.fields.find((f) => f.key === "validity")?.options || [])
                              .map(
                                (option) => `
                                  <option value="${escapeHtml(option)}" ${option === (fields.validity ?? "") ? "selected" : ""}>
                                    ${escapeHtml(option)}
                                  </option>
                                `,
                              )
                              .join("")}
                          </select>
                        </div>

                        <div class="doctor-classic-radio-group chairman-radio-group">
                          <label class="doctor-classic-radio">
                            <input type="radio" name="conclusion" value="Годен" ${(fields.conclusion ?? "Годен") === "Годен" ? "checked" : ""} />
                            <span>Годен</span>
                          </label>
                          <label class="doctor-classic-radio">
                            <input type="radio" name="conclusion" value="Не годен" ${(fields.conclusion ?? "") === "Не годен" ? "checked" : ""} />
                            <span>Не годен</span>
                          </label>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="psy-note-block">
                  <label>Примечание</label>
                  <textarea class="doctor-classic-textarea psy-note-textarea" name="note">${escapeHtml(fields.note ?? "")}</textarea>
                </div>
              </div>

              <div class="psy-sidebar">
                <button type="submit" class="doctor-classic-sidebtn">Сохранить</button>
                <button type="button" class="doctor-classic-sidebtn" data-doctor-exam-close>Отмена</button>
                <button type="button" class="doctor-classic-sidebtn doctor-classic-sidebtn--danger" data-doctor-exam-delete>удалить врача</button>

                <div class="psy-sidebar-meta">
                  <div class="psy-sidebar-meta__row">
                    <label>МКБ10</label>
                    <input
                      class="doctor-classic-input"
                      type="text"
                      name="mkb10"
                      value="${escapeHtml(fields.mkb10 ?? "")}"
                    />
                  </div>
                </div>
              </div>
            </div>
          </form>
        </div>
      </div>
    `;
  }

  function renderDefaultModal(template, exam, client) {
    const fullName = client?.fullName || client?.name || client?.fio || "Клиент";

    return `
      <div class="doctor-exam-modal-backdrop" data-doctor-exam-modal>
        <div class="doctor-exam-modal">
          <div class="doctor-exam-modal__header">
            <div>
              <div class="doctor-exam-modal__title">${escapeHtml(template.name)}</div>
              <div class="doctor-exam-modal__subtitle">${escapeHtml(fullName)}</div>
            </div>

            <button type="button" class="doctor-exam-modal__close" data-doctor-exam-close>×</button>
          </div>

          <form
            class="doctor-exam-form"
            data-doctor-exam-form
            data-exam-id="${escapeHtml(exam.id)}"
            data-doctor-role-id="${escapeHtml(template.id)}"
          >
            <div class="doctor-exam-form__grid">
              ${(template.fields || [])
                .map((field) => {
                  if (field.key === "complaintsPreset") return "";

                  const value = exam.fields?.[field.key] ?? "";

                  if (field.type === "textarea") {
                    return `
                      <div class="doctor-exam-field">
                        <label class="doctor-exam-label">${escapeHtml(field.label)}</label>
                        <textarea class="doctor-exam-textarea" name="${escapeHtml(field.key)}" rows="4">${escapeHtml(value)}</textarea>
                      </div>
                    `;
                  }

                  if (field.type === "select") {
                    return `
                      <div class="doctor-exam-field">
                        <label class="doctor-exam-label">${escapeHtml(field.label)}</label>
                        <select class="doctor-exam-select" name="${escapeHtml(field.key)}">
                          ${(field.options || [])
                            .map(
                              (option) => `
                                <option value="${escapeHtml(option)}" ${option === value ? "selected" : ""}>
                                  ${escapeHtml(option)}
                                </option>
                              `,
                            )
                            .join("")}
                        </select>
                      </div>
                    `;
                  }

                  if (field.type === "radio") {
                    return `
                      <div class="doctor-exam-field">
                        <label class="doctor-exam-label">${escapeHtml(field.label)}</label>
                        <div class="doctor-exam-radio-group">
                          ${(field.options || [])
                            .map(
                              (option) => `
                                <label class="doctor-exam-radio">
                                  <input
                                    type="radio"
                                    name="${escapeHtml(field.key)}"
                                    value="${escapeHtml(option)}"
                                    ${option === value ? "checked" : ""}
                                  />
                                  <span>${escapeHtml(option)}</span>
                                </label>
                              `,
                            )
                            .join("")}
                        </div>
                      </div>
                    `;
                  }

                  if (field.type === "checkbox") {
                    return `
                      <div class="doctor-exam-field">
                        <label class="doctor-exam-label">${escapeHtml(field.label)}</label>
                        <label class="chairman-checkbox">
                          <input type="checkbox" name="${escapeHtml(field.key)}" ${value ? "checked" : ""} />
                          <span>${escapeHtml(field.label)}</span>
                        </label>
                      </div>
                    `;
                  }

                  return `
                    <div class="doctor-exam-field">
                      <label class="doctor-exam-label">${escapeHtml(field.label)}</label>
                      <input class="doctor-exam-input" type="text" name="${escapeHtml(field.key)}" value="${escapeHtml(value)}" />
                    </div>
                  `;
                })
                .join("")}
            </div>

            <div class="doctor-exam-form__actions">
              <button type="button" class="doctor-exam-btn doctor-exam-btn--secondary" data-doctor-exam-close>Отмена</button>
              <button type="submit" class="doctor-exam-btn doctor-exam-btn--primary">Сохранить</button>
            </div>
          </form>
        </div>
      </div>
    `;
  }

  function collectFormData(form, template) {
    const result = {};
    const missingControl = Symbol("missingControl");
    const readInputValue = (input) => {
      if (!input) return "";
      if (input.type === "radio") {
        const checked = form.querySelector(`input[name="${input.name}"]:checked`);
        return checked ? checked.value : "";
      }
      if (input.type === "checkbox") {
        return !!input.checked;
      }
      return input.value ?? "";
    };
    const readNamedValue = (name, fieldType = "") => {
      const controls = getNamedControls(form.elements[name]).filter(Boolean);
      if (!controls.length) return missingControl;
      if (fieldType === "radio") {
        return form.querySelector(`input[name="${escapeCssAttributeValue(name)}"]:checked`)?.value || "";
      }
      if (fieldType === "checkbox") {
        return controls.length > 1
          ? controls.filter((input) => input.checked).map((input) => input.value)
          : Boolean(controls[0].checked);
      }
      return readInputValue(controls[0]);
    };

    (template.fields || []).forEach((field) => {
      const value = readNamedValue(field.key, field.type);
      if (value !== missingControl) result[field.key] = value;
    });

    form.querySelectorAll("input[name], textarea[name], select[name]").forEach((input) => {
      if (!input.name || Object.prototype.hasOwnProperty.call(result, input.name)) {
        return;
      }
      result[input.name] = readInputValue(input);
    });

    if (form.dataset.doctorRoleId === "chairman") {
      rememberMedicalRequirementValue(result.medicalRequirements);
    }

    return result;
  }

  function bindDoctorExamModal() {
    const modal = document.querySelector("[data-doctor-exam-modal]");
    if (!modal) return;

    const suppressDoctorCellReopen = () => {
      window.__suppressDoctorCellClickUntil = Date.now() + 400;
    };

    modal.addEventListener("click", (event) => {
      event.stopPropagation();
    });

    modal.addEventListener("mousedown", (event) => {
      event.stopPropagation();
    });

    modal.addEventListener("mouseup", (event) => {
      event.stopPropagation();
    });

    modal.addEventListener("pointerdown", (event) => {
      event.stopPropagation();
    });

    modal.addEventListener("pointerup", (event) => {
      event.stopPropagation();
    });

    modal.querySelectorAll("[data-doctor-exam-close]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        suppressDoctorCellReopen();
        window.setTimeout(() => {
          window.closeDoctorExamCard();
        }, 0);
      });
    });

    modal.querySelectorAll("[data-doctor-exam-delete]").forEach((button) => {
      button.textContent = "удалить врача";

      button.addEventListener("click", async () => {
        const form = modal.querySelector("[data-doctor-exam-form]");
        const examId = form?.dataset.examId;
        if (!examId) return;
        if (!window.confirm("Удалить карточку врача?")) return;
        const deleted = await window.deleteDoctorExam?.(examId);
        if (deleted) {
          window.closeDoctorExamCard();
        }
      });
    });

    const form = modal.querySelector("[data-doctor-exam-form]");
    if (!form) return;

    if (["certificate070", "certificate072"].includes(form.dataset.chairmanFormType || "")) {
      const quickInputs = Array.from(form.querySelectorAll("[data-sanatorium-quick-target]"));
      quickInputs.forEach((quickInput) => {
        const target = getFirstNamedControl(form.elements[quickInput.dataset.sanatoriumQuickTarget]);
        if (!target) return;

        const copyQuickValueToTarget = () => {
          if (target.value === quickInput.value) return;
          target.value = quickInput.value;
          dispatchPresetFieldEvents(target);
        };
        const copyTargetValueToQuick = () => {
          if (quickInput.value !== target.value) quickInput.value = target.value;
        };
        quickInput.addEventListener("input", copyQuickValueToTarget);
        quickInput.addEventListener("change", copyQuickValueToTarget);
        target.addEventListener("input", copyTargetValueToQuick);
        target.addEventListener("change", copyTargetValueToQuick);
      });

      const updateQuickSeasonButtons = () => {
        const seasonNames = ["seasonWinter", "seasonSpring", "seasonSummer", "seasonAutumn"];
        const checkedNames = seasonNames.filter((name) => getFirstNamedControl(form.elements[name])?.checked);
        form.querySelectorAll("[data-sanatorium-quick-season]").forEach((button) => {
          const seasonName = button.dataset.sanatoriumQuickSeason;
          button.classList.toggle(
            "is-active",
            seasonName === "all" ? checkedNames.length === seasonNames.length : checkedNames.includes(seasonName),
          );
        });
      };
      form.querySelectorAll("[data-sanatorium-quick-season]").forEach((button) => {
        button.addEventListener("click", () => {
          const seasonName = button.dataset.sanatoriumQuickSeason;
          const targets = seasonName === "all"
            ? ["seasonWinter", "seasonSpring", "seasonSummer", "seasonAutumn"]
            : [seasonName];
          const shouldCheck = seasonName === "all"
            ? !targets.every((name) => getFirstNamedControl(form.elements[name])?.checked)
            : !getFirstNamedControl(form.elements[seasonName])?.checked;
          targets.forEach((name) => {
            const checkbox = getFirstNamedControl(form.elements[name]);
            if (!checkbox || checkbox.checked === shouldCheck) return;
            checkbox.checked = shouldCheck;
            dispatchPresetFieldEvents(checkbox);
          });
          updateQuickSeasonButtons();
        });
      });
      ["seasonWinter", "seasonSpring", "seasonSummer", "seasonAutumn"].forEach((name) => {
        const checkbox = getFirstNamedControl(form.elements[name]);
        checkbox?.addEventListener("change", updateQuickSeasonButtons);
      });
      updateQuickSeasonButtons();
    }

    if (form.dataset.doctorRoleId === "chairman") {
      if (form.dataset.chairmanFormType === "certificate082") {
        const healthStatus = form.elements.healthStatus;
        const conclusion = form.querySelector("[data-certificate082-conclusion]");
        const syncHealthConclusion = () => {
          if (conclusion && healthStatus) conclusion.value = healthStatus.value;
        };
        healthStatus?.addEventListener("change", syncHealthConclusion);
        syncHealthConclusion();
      }

      const medicalRequirementsInput = form.querySelector("[data-medical-requirements-input]");
      if (medicalRequirementsInput) {
        let medicalRequirementsRememberTimer = null;
        const rememberCurrentRequirements = () => rememberMedicalRequirementValue(medicalRequirementsInput.value);
        const rememberCurrentRequirementsSoon = () => {
          window.clearTimeout(medicalRequirementsRememberTimer);
          medicalRequirementsRememberTimer = window.setTimeout(rememberCurrentRequirements, 250);
        };
        const openRequirementsPicker = (event) => {
          event.preventDefault();
          event.stopPropagation();
          rememberCurrentRequirements();
          openMedicalRequirementsPicker(medicalRequirementsInput);
        };
        const medicalRequirementsOpenButton = form.querySelector("[data-medical-requirements-open]");
        medicalRequirementsOpenButton?.addEventListener("click", openRequirementsPicker);
        medicalRequirementsInput.addEventListener("click", openRequirementsPicker);
        medicalRequirementsInput.addEventListener("focus", openRequirementsPicker);
        medicalRequirementsInput.addEventListener("input", rememberCurrentRequirementsSoon);
        medicalRequirementsInput.addEventListener("change", rememberCurrentRequirements);
        medicalRequirementsInput.addEventListener("blur", rememberCurrentRequirements);
      }

      form.querySelectorAll(".chairman-checkbox, .chairman-checkbox input").forEach((element) => {
        ["click", "mousedown", "mouseup", "pointerdown", "pointerup"].forEach((eventName) => {
          element.addEventListener(eventName, (event) => {
            event.stopPropagation();
          });
        });
      });

      if (!["lmk", "prof"].includes(form.dataset.chairmanFormType || "")) {
        const syncAutoEkgConclusion = () => {
          const chairmanType = form.dataset.chairmanFormType || "";
          const conclusionInput = getFirstNamedControl(form.elements.ekgConclusion);
          if (!conclusionInput) return;
          const currentValue = String(conclusionInput.value || "").trim();
          if (currentValue && !isAutoEkgConclusion(currentValue, chairmanType)) return;
          const ekgInput = getFirstNamedControl(form.elements.ekg);
          const examDateInput = getFirstNamedControl(form.elements.examDate);
          const ekgDate =
            extractRuDate(ekgInput?.value) ||
            extractRuDate(examDateInput?.value);
          conclusionInput.value = buildAutoEkgConclusion(ekgDate, chairmanType);
        };
        const examDateInput = getFirstNamedControl(form.elements.examDate);
        const ekgInput = getFirstNamedControl(form.elements.ekg);
        examDateInput?.addEventListener("input", syncAutoEkgConclusion);
        examDateInput?.addEventListener("change", syncAutoEkgConclusion);
        ekgInput?.addEventListener("input", syncAutoEkgConclusion);
        ekgInput?.addEventListener("change", syncAutoEkgConclusion);
      }

    }

    window.attachDateMask?.(form);

    const saveDraftFromCurrentForm = () => {
      const examId = form.dataset.examId;
      const template = window.getDoctorTemplate(form.dataset.doctorRoleId);
      if (!examId || !template) return;
      const values = collectFormData(form, template);
      window.saveDoctorExamDraft?.(examId, values);
    };

    form.querySelectorAll("input, textarea, select").forEach((field) => {
      field.addEventListener("input", saveDraftFromCurrentForm);
      field.addEventListener("change", saveDraftFromCurrentForm);
    });

    form.querySelectorAll('button[type="submit"]').forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        form.requestSubmit();
      });
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      const examId = form.dataset.examId;
      const doctorRoleId = form.dataset.doctorRoleId;
      const template = window.getDoctorTemplate(doctorRoleId);
      if (!template) return;

      const values = collectFormData(form, template);
      rememberMedicalRequirementValue(values.medicalRequirements);
      suppressDoctorCellReopen();
      const submitButtons = Array.from(form.querySelectorAll('button[type="submit"]'));
      submitButtons.forEach((button) => {
        button.disabled = true;
      });
      try {
        const saved = await window.saveDoctorExam(examId, values);
        if (saved) {
          window.closeDoctorExamCard();
        }
      } finally {
        submitButtons.forEach((button) => {
          button.disabled = false;
        });
      }
    });

    // Применение пресета жалоб: при смене select[name=complaintsPreset] подставляем
    // соответствующие значения полей из window.doctorPresets.
    const presetSelect = form.querySelector('select[name="complaintsPreset"]');
    if (presetSelect) {
      presetSelect.addEventListener("change", () => {
        const doctorRoleId = form.dataset.doctorRoleId;
        const presetName = presetSelect.value;
        const presets = (window.doctorPresets || {})[doctorRoleId];
        const preset = findDoctorPreset(presets, presetName);
        if (!preset) {
          notifyMissingDoctorPreset(doctorRoleId, presetName, presets);
          return;
        }

        Object.entries(preset).forEach(([fieldKey, value]) => {
          applyPresetFieldValue(form, fieldKey, value);
        });
      });
    }

    modal.querySelectorAll("[data-psy-tab]").forEach((button) => {
      button.addEventListener("click", async () => {
        const localForm = modal.querySelector("[data-doctor-exam-form]");
        if (!localForm) return;

        const hiddenTabInput = localForm.elements.tab;
        if (hiddenTabInput) {
          hiddenTabInput.value = button.dataset.psyTab || "Анамнез";
        }

        const doctorRoleId = localForm.dataset.doctorRoleId;
        const examId = localForm.dataset.examId;
        const template = window.getDoctorTemplate(doctorRoleId);
        if (!template) return;

        const values = collectFormData(localForm, template);
        await window.saveDoctorExam(examId, values);

        const state = window.appState?.doctorExamModal;
        if (state?.isOpen) {
          window.openDoctorExamCard({
            clientId: state.clientId,
            visitId: state.visitId,
            doctorRoleId: state.doctorRoleId,
          });
        }
      });
    });

    setTimeout(() => {
      const inputs = modal.querySelectorAll("input, textarea, select");

      inputs.forEach((el) => {
        if (el.name !== "patientFullName") {
          el.removeAttribute("readonly");
        }
        el.removeAttribute("disabled");

        el.addEventListener("click", (e) => e.stopPropagation());
        el.addEventListener("mousedown", (e) => e.stopPropagation());
        el.addEventListener("focus", (e) => e.stopPropagation());
      });

      const first = modal.querySelector(
        'select, input:not([readonly]):not([type="radio"]), textarea'
      );

      if (first) {
        first.focus();
      }
    }, 50);
  }

  function renderDoctorExamModal() {
    const modalState = window.appState?.doctorExamModal;
    if (!modalState || !modalState.isOpen) return "";

    const { clientId, visitId, doctorRoleId } = modalState;

    const template = window.getDoctorTemplate(doctorRoleId);
    if (!template) return "";

    const exam = window.getDoctorExam(clientId, visitId, doctorRoleId);
    if (!exam) return "";

    const clientPool = window.getClientPool?.() || window.data?.clients || [];
    const client = clientPool.find((item) => String(item.id) === String(clientId)) || null;

    setTimeout(bindDoctorExamModal, 0);

    if (template.layout === "phthisiatristClassic") {
      return renderPhthisiatristClassic(template, exam, client);
    }

    if (template.layout === "therapistClassic") {
      return renderTherapistClassic(template, exam, client);
    }

    if (template.layout === "otolaryngologistClassic") {
      return renderOtolaryngologistClassic(template, exam, client);
    }

    if (template.layout === "ophthalmologistClassic") {
      return renderOphthalmologistClassic(template, exam, client);
    }

    if (template.layout === "uzistClassic") {
      return renderUzistClassic(template, exam, client);
    }

    if (template.layout === "chairmanClassic") {
      return renderChairmanClassic(template, exam, client);
    }

    if (template.layout === "psychiatristClassic") {
      return renderPsychiatristClassic(template, exam, client);
    }

    return renderDefaultModal(template, exam, client);
  }

  window.renderDoctorExamModal = renderDoctorExamModal;
})();
