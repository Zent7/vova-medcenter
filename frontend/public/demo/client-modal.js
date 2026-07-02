let clientModalSelectedServices = new Set();
let clientModalServiceDetails = {};
let clientModalSubmitAction = "save";

const CLIENT_DRIVER_DEFAULT_CATEGORIES = ["A", "B", "C", "D", "BE", "M"];
const CLIENT_DRIVER_LIMITATIONS = [
  "Категории A, M, A1, B1",
  "Категории B, BE, B1",
  "Категории C, CE, D, DE, Tm, Tb, C1, D1, C1E, D1E",
];
const CLIENT_DRIVER_INDICATIONS = [
  "С ручным упр-ем",
  "С автоматич. трансмиссией",
  "Акустич. парковочная система",
  "ТС мед. изд. для коррекции зрения",
  "ТС мед. изд. для компенсации потери слуха",
];
const CLIENT_ADDRESS_STORAGE_KEY = "vova-medcenter-address-suggestions-v1";
const CLIENT_ISSUED_BY_STORAGE_KEY = "vova-medcenter-issued-by-suggestions-v1";
const CLIENT_RECENT_FIELDS_STORAGE_KEY = "vova-medcenter-client-recent-fields-v1";
const CLIENT_DEFAULT_COUNTRY = "Россия";
const CLIENT_ISSUED_BY_PRESETS = ["УФМС", "ГУ МВД", "МВД", "ОВД"];
const CLIENT_ADDRESS_PRESETS = [
  { city: "Санкт-Петербург", subject: "Санкт-Петербург", district: "" },
  { city: "Кудрово", subject: "Ленинградская область", district: "Всеволожский район" },
  { city: "Мурино", subject: "Ленинградская область", district: "Всеволожский район" },
  { city: "Янино-1", subject: "Ленинградская область", district: "Всеволожский район" },
  { city: "Всеволожск", subject: "Ленинградская область", district: "Всеволожский район" },
  { city: "Шушары", subject: "Санкт-Петербург", district: "Пушкинский район" },
  { city: "Пушкин", subject: "Санкт-Петербург", district: "Пушкинский район" },
  { city: "Колпино", subject: "Санкт-Петербург", district: "Колпинский район" },
  { city: "Петергоф", subject: "Санкт-Петербург", district: "Петродворцовый район" },
];

function formatClientNameInputValue(value = "") {
  return String(value || "").replace(/[^\s-]+/gu, (part) => {
    const [first = "", ...rest] = Array.from(part);
    return first.toLocaleUpperCase("ru-RU") + rest.join("").toLocaleLowerCase("ru-RU");
  });
}

function bindClientNameCapitalization(form) {
  if (!form) return;
  form.querySelectorAll('input[name="lastName"], input[name="firstName"], input[name="middleName"]').forEach((input) => {
    const format = () => {
      const nextValue = formatClientNameInputValue(input.value);
      if (input.value === nextValue) return;
      const selectionStart = input.selectionStart ?? nextValue.length;
      input.value = nextValue;
      input.setSelectionRange(selectionStart, selectionStart);
    };
    input.addEventListener("input", format);
    input.addEventListener("blur", format);
    format();
  });
}

function loadClientAddressSuggestions() {
  try {
    const parsed = JSON.parse(window.localStorage?.getItem(CLIENT_ADDRESS_STORAGE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveClientAddressSuggestion(entry = {}) {
  const city = String(entry.city || "").trim();
  if (!city) return;
  const nextEntry = {
    city,
    subject: String(entry.subject || "").trim(),
    district: String(entry.district || "").trim(),
    street: String(entry.street || "").trim(),
  };
  const existing = loadClientAddressSuggestions().filter((item) => String(item.city || "").toLowerCase() !== city.toLowerCase());
  window.localStorage?.setItem(CLIENT_ADDRESS_STORAGE_KEY, JSON.stringify([nextEntry, ...existing].slice(0, 60)));
}

function loadClientIssuedBySuggestions() {
  try {
    const parsed = JSON.parse(window.localStorage?.getItem(CLIENT_ISSUED_BY_STORAGE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed.map((item) => String(item || "").trim()).filter(Boolean) : [];
  } catch {
    return [];
  }
}

function saveClientIssuedBySuggestion(value = "") {
  const nextValue = String(value || "").trim();
  if (!nextValue) return;
  const existing = loadClientIssuedBySuggestions().filter((item) => item.toLowerCase() !== nextValue.toLowerCase());
  window.localStorage?.setItem(CLIENT_ISSUED_BY_STORAGE_KEY, JSON.stringify([nextValue, ...existing].slice(0, 80)));
}

function getClientIssuedBySuggestionsFromClients() {
  const clients = [...(data?.backendClients || []), ...(data?.clients || [])];
  return clients
    .map((client) => {
      const raw = client?.rawApiClient || client || {};
      return String(
        raw.document_issued_by ||
          raw.legacy_payload_json?.WhoGive ||
          raw.legacy_payload_json?.["qdfMain.WhoGive"] ||
          client?.documentIssuedBy ||
          "",
      ).trim();
    })
    .filter(Boolean);
}

function getClientIssuedByOptions() {
  const byValue = new Map();
  [...loadClientIssuedBySuggestions(), ...getClientIssuedBySuggestionsFromClients(), ...CLIENT_ISSUED_BY_PRESETS].forEach((value) => {
    const normalized = String(value || "").trim();
    if (!normalized) return;
    const key = normalized.toLowerCase();
    if (!byValue.has(key)) byValue.set(key, normalized);
  });
  return [...byValue.values()].slice(0, 120);
}

function loadClientRecentFields() {
  try {
    const parsed = JSON.parse(window.localStorage?.getItem(CLIENT_RECENT_FIELDS_STORAGE_KEY) || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function getClientRecentField(name) {
  const values = loadClientRecentFields()[name];
  return Array.isArray(values) ? String(values[0] || "").trim() : "";
}

function rememberClientRecentFields(fields = {}) {
  const recent = loadClientRecentFields();
  Object.entries(fields).forEach(([name, value]) => {
    const normalized = String(value || "").trim();
    if (!normalized) return;
    const existing = Array.isArray(recent[name]) ? recent[name] : [];
    recent[name] = [normalized, ...existing.filter((item) => String(item || "").trim().toLowerCase() !== normalized.toLowerCase())].slice(0, 80);
  });
  window.localStorage?.setItem(CLIENT_RECENT_FIELDS_STORAGE_KEY, JSON.stringify(recent));
}

function uniqueClientTextOptions(values = []) {
  const byValue = new Map();
  values.forEach((value) => {
    const normalized = String(value || "").trim();
    if (!normalized) return;
    const key = normalized.toLowerCase();
    if (!byValue.has(key)) byValue.set(key, normalized);
  });
  return [...byValue.values()].slice(0, 120);
}

function parseClientAddressSuggestion(addressText = "") {
  const parts = String(addressText || "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  if (!parts.length) return null;

  const isCountryValue = (value = "") => {
    const normalized = String(value || "")
      .trim()
      .toLowerCase()
      .replace(/\./g, "");
    return ["россия", "рф", "российская федерация"].includes(normalized);
  };
  const hasSubjectMarker = (value = "") => /обл\.?|область|край|респ\.?|республика|автоном|ао\b|округ|санкт-петербург|спб|москва|севастополь/i.test(value);
  const hasDistrictMarker = (value = "") => /район|р-н/i.test(value);
  const hasCityMarker = (value = "") => /(^|\s)(г\.|гор\.|город)\s*|санкт-петербург|спб|москва|севастополь/i.test(value);
  const hasStreetMarker = (value = "") => /(^|\s)(ул\.|улица|пр-?кт|просп\.?|проспект|пер\.|переулок|наб\.|шоссе|б-р|бул\.?|бульвар)\s*/i.test(value);
  const hasHouseMarker = (value = "") => /(^|\s)(д\.|дом)\s*/i.test(value);
  const hasBuildingMarker = (value = "") => /корпус|корп\.?|к\.\s*/i.test(value);
  const hasFlatMarker = (value = "") => /(^|\s)(кв\.|квартира)\s*/i.test(value);
  const stripMarker = (value = "", pattern) => String(value || "").replace(pattern, "").trim();

  if (isCountryValue(parts[0])) {
    return {
      country: parts[0] || CLIENT_DEFAULT_COUNTRY,
      subject: parts[1] || "",
      district: parts[2] || "",
      city: parts[3] || "",
      street: parts[4] || "",
      house: stripMarker(parts[5] || "", /(^|\s)(д\.|дом)\s*/i),
      building: stripMarker(parts[6] || "", /(^|\s)(корпус|корп\.?|к\.)\s*/i),
      flat: stripMarker(parts[7] || "", /(^|\s)(кв\.|квартира)\s*/i),
    };
  }

  const subject = parts.find(hasSubjectMarker) || "";
  const district = parts.find(hasDistrictMarker) || "";
  const city = parts.find(hasCityMarker) || parts.find((part) => part && part !== subject && part !== district && !hasStreetMarker(part) && !hasHouseMarker(part)) || "";
  const street = parts.find(hasStreetMarker) || "";
  const house = parts.find(hasHouseMarker) || "";
  const building = parts.find(hasBuildingMarker) || "";
  const flat = parts.find(hasFlatMarker) || "";

  return {
    country: CLIENT_DEFAULT_COUNTRY,
    subject,
    district,
    city,
    street,
    house: stripMarker(house, /(^|\s)(д\.|дом)\s*/i),
    building: stripMarker(building, /(^|\s)(корпус|корп\.?|к\.)\s*/i),
    flat: stripMarker(flat, /(^|\s)(кв\.|квартира)\s*/i),
  };
}

function getClientAddressSuggestionsFromClients() {
  const clients = [...(data?.backendClients || []), ...(data?.clients || [])];
  return clients
    .map((client) => {
      const raw = client?.rawApiClient || {};
      return parseClientAddressSuggestion(client?.registration || raw.registration_text || raw.address_text || "");
    })
    .filter((item) => item?.city);
}

function getClientTextFieldOptions(name, presets = []) {
  const recent = loadClientRecentFields()[name] || [];
  const clients = [...(data?.backendClients || []), ...(data?.clients || [])];
  const values = clients.map((client) => {
    const raw = client?.rawApiClient || client || {};
    if (name === "documentType") return raw.document_type || client?.documentType || "";
    if (name === "agent") return raw.agent || raw.legacy_payload_json?.agent || client?.agent || "";
    if (name === "profession") return raw.profession || raw.legacy_payload_json?.profession || client?.profession || "";
    if (name === "workPlace") return raw.work_place || raw.legacy_payload_json?.work_place || client?.workPlace || "";
    if (name === "organization") return raw.organization || raw.legacy_payload_json?.organization || client?.organization || "";
    return "";
  });
  return uniqueClientTextOptions([...recent, ...values, ...presets]);
}

function getClientAddressFieldOptions(name) {
  const recent = loadClientRecentFields()[name] || [];
  const saved = loadClientAddressSuggestions();
  const fromClients = getClientAddressSuggestionsFromClients();
  const fromPresets = CLIENT_ADDRESS_PRESETS;
  return uniqueClientTextOptions([...recent, ...saved, ...fromClients, ...fromPresets].map((item) => item?.[name]));
}

function getClientAddressOptions() {
  const saved = loadClientAddressSuggestions();
  const byCity = new Map();
  [...saved, ...getClientAddressSuggestionsFromClients(), ...CLIENT_ADDRESS_PRESETS].forEach((item) => {
    const city = String(item.city || "").trim();
    if (!city || byCity.has(city.toLowerCase())) return;
    byCity.set(city.toLowerCase(), item);
  });
  return Array.from(byCity.values());
}

function renderClientAddressDatalists() {
  const options = getClientAddressOptions();
  const streetOptions = [...loadClientAddressSuggestions(), ...getClientAddressSuggestionsFromClients()]
    .map((item) => String(item.street || "").trim())
    .filter(Boolean)
    .filter((value, index, list) => list.indexOf(value) === index);
  const subjectOptions = getClientAddressFieldOptions("subject");
  const districtOptions = getClientAddressFieldOptions("district");
  const issuedByOptions = getClientIssuedByOptions();
  const documentTypeOptions = getClientTextFieldOptions("documentType", ["Паспорт РФ", "Другое"]);
  const agentOptions = getClientTextFieldOptions("agent");
  const professionOptions = getClientTextFieldOptions("profession");
  const workPlaceOptions = getClientTextFieldOptions("workPlace");
  const organizationOptions = getClientTextFieldOptions("organization");
  return `
    <datalist id="clientDocumentTypeSuggestions">
      ${documentTypeOptions.map((value) => `<option value="${escapeHtml(value)}"></option>`).join("")}
    </datalist>

    <datalist id="clientCitySuggestions">
      ${options.map((item) => `<option value="${escapeHtml(item.city)}">${escapeHtml([item.subject, item.district].filter(Boolean).join(", "))}</option>`).join("")}
    </datalist>

    <datalist id="clientSubjectSuggestions">
      ${subjectOptions.map((value) => `<option value="${escapeHtml(value)}"></option>`).join("")}
    </datalist>

    <datalist id="clientDistrictSuggestions">
      ${districtOptions.map((value) => `<option value="${escapeHtml(value)}"></option>`).join("")}
    </datalist>

    <datalist id="clientStreetSuggestions">
      ${streetOptions.map((street) => `<option value="${escapeHtml(street)}"></option>`).join("")}
    </datalist>

    <datalist id="clientIssuedBySuggestions">

      ${issuedByOptions.map((value) => `<option value="${escapeHtml(value)}"></option>`).join("")}

    </datalist>

    <datalist id="clientAgentSuggestions">
      ${agentOptions.map((value) => `<option value="${escapeHtml(value)}"></option>`).join("")}
    </datalist>

    <datalist id="clientProfessionSuggestions">
      ${professionOptions.map((value) => `<option value="${escapeHtml(value)}"></option>`).join("")}
    </datalist>

    <datalist id="clientWorkPlaceSuggestions">
      ${workPlaceOptions.map((value) => `<option value="${escapeHtml(value)}"></option>`).join("")}
    </datalist>

    <datalist id="clientOrganizationSuggestions">
      ${organizationOptions.map((value) => `<option value="${escapeHtml(value)}"></option>`).join("")}
    </datalist>
  `;
}

function bindClientAddressAutocomplete(form, { defaultCountry = true } = {}) {
  const countryInput = form?.elements.country;
  const cityInput = form?.elements.city;
  const subjectInput = form?.elements.subject;
  const districtInput = form?.elements.district;
  if (!cityInput || !subjectInput || !districtInput) return;

  if (defaultCountry && countryInput && !String(countryInput.value || "").trim()) {
    countryInput.value = CLIENT_DEFAULT_COUNTRY;
  }

  const applyPreset = () => {
    const city = String(cityInput.value || "").trim().toLowerCase();
    const preset = getClientAddressOptions().find((item) => String(item.city || "").trim().toLowerCase() === city);
    if (!preset) {
      if (subjectInput.dataset.autofilled === "true") subjectInput.value = "";
      if (districtInput.dataset.autofilled === "true") districtInput.value = "";
      delete subjectInput.dataset.autofilled;
      delete districtInput.dataset.autofilled;
      return;
    }

    subjectInput.value = preset.subject || "";
    districtInput.value = preset.district || "";
    subjectInput.dataset.autofilled = "true";
    districtInput.dataset.autofilled = "true";
  };

  cityInput.addEventListener("input", applyPreset);
  cityInput.addEventListener("change", applyPreset);
  cityInput.addEventListener("blur", applyPreset);

  const saveCurrentAddress = () => {
    saveClientAddressSuggestion({
      subject: form.elements.subject?.value,
      district: form.elements.district?.value,
      city: form.elements.city?.value,
      street: form.elements.street?.value,
    });
  };
  ["subject", "district", "city", "street"].forEach((name) => {
    const input = form.elements[name];
    input?.addEventListener("change", saveCurrentAddress);
    input?.addEventListener("blur", saveCurrentAddress);
  });
}

function getActiveClientServiceGroups() {
  return serviceGroups
    .filter((group) => group.isActive !== false)
    .slice()
    .sort((a, b) => (a.sortOrder || 0) - (b.sortOrder || 0));
}

function getVisibleClientServices(groupId) {
  const visibleServices = structuredServices
    .filter((service) => service.isActive !== false)
    .filter((service) => String(service.groupId) === String(groupId))
    .filter((service) => {
      const normalizedName = String(service.name || "").trim().toLowerCase();
      return !normalizedName.includes("дубл");
    })
    .slice();

  const uniqueVisibleServices = [];
  const seenServiceNames = new Set();

  visibleServices.forEach((service) => {
    const normalizedName = String(service.name || "").trim().toLowerCase();
    if (!normalizedName || seenServiceNames.has(normalizedName)) return;
    seenServiceNames.add(normalizedName);
    uniqueVisibleServices.push(service);
  });

  return uniqueVisibleServices;
}

function getClientModalSelectedServicesFromDom() {
  actionModalContent.querySelectorAll('#serviceSelectorContainer input[name="services"]').forEach((input) => {
    if (input.checked) {
      clientModalSelectedServices.add(input.value);
    } else {
      clientModalSelectedServices.delete(input.value);
    }
  });
  return Array.from(clientModalSelectedServices);
}

function getClientSelectedDriverService(selectedServices = []) {
  return selectedServices
    .map((name) => getServerServiceByName(name) || structuredServices.find((service) => service.name === name))
    .find((service) => service && isDriverService(service)) || null;
}

function getClientDriverCategoriesFromForm() {
  const categoryInputs = Array.from(actionModalContent.querySelectorAll('input[name="clientDriverCategory"]'));
  if (!categoryInputs.length) return CLIENT_DRIVER_DEFAULT_CATEGORIES.slice();
  const checked = categoryInputs.filter((input) => input.checked)
    .map((input) => input.value);
  return checked;
}

function getClientDriverFlagsFromForm(fieldName) {



  return Array.from(actionModalContent.querySelectorAll(`input[name="${fieldName}"]:checked`))



    .map((input) => input.value)



    .filter(Boolean);



}

function renderClientClassicCheckbox(name, value, label, checked = false) {
  return `
    <label class="client-classic-checkbox">
      <span>${escapeHtml(label)}</span>
      <input type="checkbox" name="${escapeHtml(name)}" value="${escapeHtml(value)}" ${checked ? "checked" : ""} />
    </label>
  `;
}

function renderClientDriverClassicPanel(selectedServices = [], selectedCategories = CLIENT_DRIVER_DEFAULT_CATEGORIES, driverDetail = {}) {
  const selectedDriverService = getClientSelectedDriverService(selectedServices);
  if (!selectedDriverService) return "";

  const normalizedCategories = Array.isArray(selectedCategories)
    ? (typeof normalizeDriverCategories === "function"
        ? normalizeDriverCategories(selectedCategories)
        : DRIVER_CATEGORY_OPTIONS.filter((item) => selectedCategories.includes(item)))
    : CLIENT_DRIVER_DEFAULT_CATEGORIES.slice();



  const selectedLimitations = Array.isArray(driverDetail.limitations) ? driverDetail.limitations : [];



  const selectedIndications = Array.isArray(driverDetail.indications) ? driverDetail.indications : [];



  const boatFitChecked = Boolean(driverDetail.boatFit);

  return `
    <div class="client-driver-classic">
      <div class="client-driver-tabs">
        <button type="button">Основное</button>
        <button type="button" class="active">Водительская</button>
        <button type="button">Тракторная</button>
      </div>

      <div class="client-driver-layout">
        <div class="client-driver-doctors">
          ${["Терапевт", "Офтальмолог", "Невролог", "Оториноларинголог", "Инструментальное исследование"]
            .map(
              (label) => `
                <label class="client-driver-doctor-field">
                  <span>${label}</span>
                  <select>
                    <option>-</option>
                  </select>
                </label>
              `,
            )
            .join("")}
          <label class="client-driver-doctor-field">
            <span>Лабораторные исследования</span>
            <input value="Не установлено" />
          </label>
        </div>

        <div class="client-driver-categories">
          <div class="client-driver-category-row client-driver-category-row--top">
            ${["A", "B", "C", "D"].map((category) => renderClientClassicCheckbox("clientDriverCategory", category, category, normalizedCategories.includes(category))).join("")}
          </div>
          <div class="client-driver-category-row">
            ${["BE", "CE", "DE"].map((category) => renderClientClassicCheckbox("clientDriverCategory", category, category, normalizedCategories.includes(category))).join("")}
          </div>
          <div class="client-driver-category-row">
            ${["Tm", "Tb", "M"].map((category) => renderClientClassicCheckbox("clientDriverCategory", category, category, normalizedCategories.includes(category))).join("")}



          </div>



          <div class="client-driver-category-row">



            ${["A1", "B1", "C1", "D1", "C1E", "D1E"].map((category) => renderClientClassicCheckbox("clientDriverCategory", category, category, normalizedCategories.includes(category))).join("")}
          </div>
        </div>

        <div class="client-driver-box client-driver-box--limits">
          <strong>Мед. ограничения к упр-ию ТС</strong>
          ${CLIENT_DRIVER_LIMITATIONS.map((item) => renderClientClassicCheckbox("clientDriverLimit", item, item, selectedLimitations.includes(item))).join("")}
          <span class="client-driver-red-dot">•</span>
        </div>

        <div class="client-driver-box client-driver-box--indications">
          <strong>Мед. показания к упр-ию ТС</strong>
          ${CLIENT_DRIVER_INDICATIONS.map((item) => renderClientClassicCheckbox("clientDriverIndication", item, item, selectedIndications.includes(item))).join("")}
        </div>
      </div>

      <div class="client-driver-footer">
        <label class="client-classic-checkbox client-classic-checkbox--inline">
          <span>Годен к упр-ю маломер. судами</span>
          <input type="checkbox" name="clientDriverBoatFit" ${boatFitChecked ? "checked" : ""} />
        </label>
        <label class="client-driver-chief">
          <span>Гл.врач</span>
          <input value="Сибирцев Вячеслав Александрович" />
        </label>
      </div>
    </div>
  `;
}

function refreshClientDriverPanel() {
  const container = document.getElementById("clientDriverPanelContainer");
  if (!container) return;
  const selectedServices = getClientModalSelectedServicesFromDom();
  const selectedCategories = getClientDriverCategoriesFromForm();



  const selectedDriverService = getClientSelectedDriverService(selectedServices);



  const selectedDriverDetail = selectedDriverService



    ? clientModalServiceDetails[getClientServiceDetailKey(selectedDriverService)] || {}



    : {};
  container.innerHTML = renderClientDriverClassicPanel(selectedServices, selectedCategories, selectedDriverDetail);
  bindClientDriverCategoryCheckboxes();
}

function bindClientDriverCategoryCheckboxes() {
  actionModalContent.querySelectorAll('input[name="clientDriverCategory"]').forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const selectedServices = getClientModalSelectedServicesFromDom();
      const container = document.getElementById("clientDriverPanelContainer");
      if (container) {
        container.innerHTML = renderClientDriverClassicPanel(selectedServices, getClientDriverCategoriesFromForm());
        bindClientDriverCategoryCheckboxes();
      }
      refreshClientPaymentPanel({ driverCategoriesChanged: true });
    });
  });
}

function getClientServiceItemsByNames(selectedServices = []) {
  return selectedServices
    .map((name) => getServerServiceByName(name) || structuredServices.find((service) => service.name === name))
    .filter(Boolean);
}

function getClientServiceDetailKey(service) {
  return String(getServiceToken(service) || service?.name || "");
}

function getDefaultServiceUnitPrice(service) {
  if (service && isDriverService(service)) {
    return getDriverCategoryPrice(normalizeDriverCategories(getClientDriverCategoriesFromForm()));
  }
  return Number(service?.price || 0);
}

function syncClientPaymentRowsFromDom() {
  actionModalContent.querySelectorAll("[data-client-payment-service]").forEach((row) => {
    const serviceKey = row.dataset.clientPaymentService;
    if (!serviceKey) return;
    const current = clientModalServiceDetails[serviceKey] || {};
    clientModalServiceDetails[serviceKey] = {
      ...current,
      unitPrice: Number(row.querySelector('[name="clientServicePrice"]')?.value || 0),
      paymentType: row.querySelector('[name="clientServicePaymentType"]')?.value || current.paymentType || "cash",
      comment: row.querySelector('[name="clientServiceComment"]')?.value || "",
    };
  });
}

function getClientServiceDraftDetail(service) {
  const key = getClientServiceDetailKey(service);
  const existing = clientModalServiceDetails[key] || {};
  const defaultUnitPrice = getDefaultServiceUnitPrice(service);
  return {
    ...existing,
    unitPrice: Number(existing.unitPrice ?? defaultUnitPrice ?? 0),
    paymentType: existing.paymentType || "cash",
    comment: existing.comment || "",
  };
}

function getClientPaymentRowsTotal() {
  return Array.from(actionModalContent.querySelectorAll('[name="clientServicePrice"]'))
    .reduce((sum, input) => sum + Number(input.value || 0), 0);
}

function updateClientPaymentTotal() {
  const totalNode = document.getElementById("clientPaymentTotalValue");
  const total = getClientPaymentRowsTotal();
  if (totalNode) totalNode.textContent = Number(total || 0).toLocaleString("ru-RU");
}

function renderClientPaymentRows(selectedServices = []) {
  const serviceItems = getClientServiceItemsByNames(selectedServices);
  if (!serviceItems.length) {
    return "";
  }

  const rows = serviceItems.map((service) => {
    const serviceKey = getClientServiceDetailKey(service);
    const detail = getClientServiceDraftDetail(service);
    return `
      <div class="client-payment-row" data-client-payment-service="${escapeHtml(serviceKey)}">
        <div class="client-payment-row__service">
          <span>${escapeHtml(service.name)}</span>
          <button type="button" class="client-payment-row__remove" data-remove-client-service="${escapeHtml(service.name)}" aria-label="Удалить услугу ${escapeHtml(service.name)}">×</button>
        </div>
        <label class="field">
          <span>Цена</span>
          <input name="clientServicePrice" type="number" min="0" step="0.01" value="${Number(detail.unitPrice || 0)}" />
        </label>
        <label class="field">
          <span>Оплата</span>
          <select name="clientServicePaymentType">
            <option value="cash" ${detail.paymentType === "cash" ? "selected" : ""}>нал</option>
            <option value="invoice" ${detail.paymentType === "invoice" || detail.paymentType === "card" ? "selected" : ""}>безнал</option>
          </select>
        </label>
        <label class="field client-payment-row__comment">
          <span>Комментарий</span>
          <input name="clientServiceComment" value="${escapeHtml(detail.comment || "")}" placeholder="скидка, договоренность" />
        </label>
      </div>
    `;
  }).join("");

  return `
    <div class="client-payment-block">
      <div class="client-payment-block__head">
        <strong>Выбранные услуги</strong>
        <span>Итого: <b id="clientPaymentTotalValue">0</b> ₽</span>
      </div>
      <div class="client-payment-list">${rows}</div>
    </div>
  `;
}

function bindClientPaymentRows() {
  actionModalContent.querySelectorAll("[data-client-payment-service]").forEach((row) => {
    row.querySelectorAll("input, select").forEach((input) => {
      input.addEventListener("input", () => {
        syncClientPaymentRowsFromDom();
        if (input.name === "clientServicePrice") updateClientPaymentTotal();
      });
      input.addEventListener("change", () => {
        syncClientPaymentRowsFromDom();
        if (input.name === "clientServicePrice") updateClientPaymentTotal();
      });
    });
  });

  actionModalContent.querySelectorAll("[data-remove-client-service]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      removeClientSelectedService(button.dataset.removeClientService || "");
    });
  });

  updateClientPaymentTotal();
}




function removeClientSelectedService(serviceName = "") {
  const normalizedName = String(serviceName || "").trim();
  if (!normalizedName) return;

  syncClientPaymentRowsFromDom();
  clientModalSelectedServices.delete(normalizedName);
  const removedService = getServerServiceByName(normalizedName) || structuredServices.find((service) => service.name === normalizedName);
  delete clientModalServiceDetails[String(removedService ? getClientServiceDetailKey(removedService) : normalizedName)];
  actionModalContent.querySelectorAll('#serviceSelectorContainer input[name="services"]').forEach((input) => {
    if (input.value === normalizedName) input.checked = false;
  });

  const selectedNow = Array.from(clientModalSelectedServices);
  const selector = document.getElementById("serviceSelectorContainer");
  if (selector) {
    selector.outerHTML = `<div id="serviceSelectorContainer">${renderClientServiceSelector(selectedNow)}</div>`;
    bindClientServiceGroupButtons();
  }

  const driverContainer = document.getElementById("clientDriverPanelContainer");
  if (driverContainer) {
    driverContainer.innerHTML = renderClientDriverClassicPanel(selectedNow, getClientDriverCategoriesFromForm());
    bindClientDriverCategoryCheckboxes();
  }

  const paymentContainer = document.getElementById("clientPaymentContainer");
  if (paymentContainer) {
    paymentContainer.innerHTML = renderClientPaymentRows(selectedNow);
    bindClientPaymentRows();
  }
}

function refreshClientPaymentPanel({ driverCategoriesChanged = false } = {}) {
  syncClientPaymentRowsFromDom();
  const selectedServices = getClientModalSelectedServicesFromDom();
  const selectedDriverService = getClientSelectedDriverService(selectedServices);
  if (driverCategoriesChanged && selectedDriverService) {
    const driverKey = getClientServiceDetailKey(selectedDriverService);
    const current = clientModalServiceDetails[driverKey] || {};
    clientModalServiceDetails[driverKey] = {
      ...current,
      unitPrice: getDefaultServiceUnitPrice(selectedDriverService),
    };
  }
  const container = document.getElementById("clientPaymentContainer");
  if (!container) return;
  container.innerHTML = renderClientPaymentRows(selectedServices);
  bindClientPaymentRows();
}

function buildClientServiceDetails(selectedServices = []) {
  syncClientPaymentRowsFromDom();
  const details = {};
  const serviceItems = getClientServiceItemsByNames(selectedServices);
  serviceItems.forEach((service) => {
    const serviceId = getClientServiceDetailKey(service);
    const draft = getClientServiceDraftDetail(service);
    details[serviceId] = {
      unitPrice: Number(draft.unitPrice || 0),
      paymentType: draft.paymentType || "cash",
      comment: draft.comment || "",
    };
  });

  const selectedDriverService = getClientSelectedDriverService(selectedServices);
  if (selectedDriverService) {
    const categories = normalizeDriverCategories(getClientDriverCategoriesFromForm());
    const indications = getClientDriverFlagsFromForm("clientDriverIndication");
    const limitations = getClientDriverFlagsFromForm("clientDriverLimit");
    const boatFit = Boolean(actionModalContent.querySelector('input[name="clientDriverBoatFit"]')?.checked);
    const serviceId = getClientServiceDetailKey(selectedDriverService);
    details[serviceId] = {
      ...(details[serviceId] || {}),
      categories,
      indications,
      limitations,
      boatFit,
      unitPrice: Number(details[serviceId]?.unitPrice ?? getDriverCategoryPrice(categories)),
      autoDoctorRoles: getDriverRoleCodes(categories),
    };
  }

  return details;
}

function getClientVisitPaymentSummary(selectedServices = [], serviceDetails = {}, baseComment = "") {
  const serviceItems = getClientServiceItemsByNames(selectedServices);
  const firstPaymentType = serviceItems
    .map((service) => serviceDetails[getClientServiceDetailKey(service)]?.paymentType)
    .find(Boolean) || "cash";
  const comments = serviceItems
    .map((service) => {
      const comment = serviceDetails[getClientServiceDetailKey(service)]?.comment;
      return comment ? `${service.name}: ${comment}` : "";
    })
    .filter(Boolean);
  return {
    paymentType: firstPaymentType,
    comment: [String(baseComment || "").trim(), ...comments].filter(Boolean).join("; "),
  };
}

function getClientServiceIdsByNames(selectedServices = []) {
  return selectedServices
    .map((name) => getServerServiceByName(name))
    .filter(Boolean)
    .map((service) => getServiceToken(service));
}

function renderClientServiceSelector(selectedServices = []) {
  const selectedSet = new Set(selectedServices);
  const groups = getActiveClientServiceGroups();
  const availableGroupIds = new Set(groups.map((group) => String(group.id)));
  const fallbackGroupId = groups.length ? String(groups[0].id) : "";
  const currentGroup = availableGroupIds.has(String(appState.clientServiceGroupFilter || ""))
    ? String(appState.clientServiceGroupFilter)
    : fallbackGroupId;

  appState.clientServiceGroupFilter = currentGroup;

  const visibleServices = currentGroup ? getVisibleClientServices(currentGroup) : [];

  return `
    <div class="client-services-block">
      <div class="client-services-block__title">Услуги</div>

      <div class="sketch-doctors sketch-doctors--top" style="margin-bottom:12px;">
        ${groups
          .map(
            (group) => `
              <button
                type="button"
                class="doctor-pill ${String(currentGroup) === String(group.id) ? "active" : ""}"
                data-client-service-group="${group.id}"
              >
                ${escapeHtml(group.name)}
              </button>
            `,
          )
          .join("")}
      </div>

      <div class="client-services-list">
        ${
          visibleServices.length
            ? visibleServices
                .map(
                  (service) => `
                    <label class="${selectedSet.has(service.name) ? "client-service-chip client-service-chip--active" : "client-service-chip"}">
                      <input
                        type="checkbox"
                        name="services"
                        value="${escapeHtml(service.name)}"
                        ${selectedSet.has(service.name) ? "checked" : ""}
                      />
                      <span>${escapeHtml(service.name)}</span>
                      ${selectedSet.has(service.name) ? '<span class="client-service-chip__check" aria-hidden="true"></span>' : ""}
                    </label>
                  `,
                )
                .join("")
            : '<div class="muted">В этой группе услуг пока нет</div>'
        }
      </div>
    </div>
  `;
}

function bindClientServiceGroupButtons() {
  actionModalContent.querySelectorAll('#serviceSelectorContainer input[name="services"]').forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const selectedNow = getClientModalSelectedServicesFromDom();
      const container = document.getElementById("serviceSelectorContainer");
      if (container) {
        container.outerHTML = `<div id="serviceSelectorContainer">${renderClientServiceSelector(selectedNow)}</div>`;
        bindClientServiceGroupButtons();
      }
      refreshClientDriverPanel();
      refreshClientPaymentPanel();
    });
  });

  actionModalContent.querySelectorAll("[data-client-service-group]").forEach((button) => {
    button.addEventListener("click", () => {
      const selectedNow = getClientModalSelectedServicesFromDom();

      appState.clientServiceGroupFilter = button.dataset.clientServiceGroup;

      const container = document.getElementById("serviceSelectorContainer");
      if (container) {
        container.outerHTML = `<div id="serviceSelectorContainer">${renderClientServiceSelector(selectedNow)}</div>`;
      }

      bindClientServiceGroupButtons();
      refreshClientDriverPanel();
      refreshClientPaymentPanel();
    });
  });
}

function openClientModal(clientId = null, options = {}) {
  const encounterMode = options && typeof options === "object" ? options.encounterMode === true : false;
  const selectedClient = window.getSelectedClient?.();
  const editingClient = clientId
    ? selectedClient && String(selectedClient.id) === String(clientId)
      ? selectedClient
      : window.getClientPool?.().find((client) => String(client.id) === String(clientId)) ||
        data.clients.find((client) => String(client.id) === String(clientId))
    : null;
  const raw = editingClient ? editingClient.fullName : appState.clientSearch.trim();
  const parts = raw.split(/\s+/).filter(Boolean);
  const [lastName = "", firstName = "", middleName = ""] = parts;
  const sortedGroups = getActiveClientServiceGroups();
  const initialAddress = parseClientAddressSuggestion(
    editingClient?.registration ||
    editingClient?.rawApiClient?.registration_text ||
    editingClient?.rawApiClient?.address_text ||
    "",
  ) || {};

  if (!appState.clientServiceGroupFilter || !sortedGroups.some((group) => String(group.id) === String(appState.clientServiceGroupFilter))) {
    appState.clientServiceGroupFilter = sortedGroups.length ? String(sortedGroups[0].id) : "";
  }

  const initialVisit = !encounterMode && editingClient ? window.getCurrentVisitForClient?.(editingClient.id) : null;
  const initialSelectedServices = encounterMode ? [] : (editingClient?.services || []);
  clientModalSelectedServices = new Set(initialSelectedServices);
  clientModalServiceDetails = { ...(initialVisit?.serviceDetails || {}) };
  clientModalSubmitAction = "save";
  const modalTitle = encounterMode
    ? "Новое обращение"
    : (editingClient ? "Изменить клиента" : "Новый клиент");
  const heroTitle = encounterMode
    ? "Новое обращение в журнале"
    : (editingClient ? "Обновление данных пациента" : "Новый пациент в журнале");
  const heroBadge = encounterMode
    ? "Обращение"
    : (editingClient ? "Редактирование" : "Создание");
  const primarySubmitLabel = encounterMode ? "Сохранить обращение" : "ОК";
  const defaultGender = editingClient?.gender || editingClient?.sex || editingClient?.rawApiClient?.sex || "";
  const rawClientDocument = editingClient?.rawApiClient || {};
  const initialDocumentType =
    rawClientDocument.document_type ||
    String(editingClient?.document || "").split(" ").slice(0, 2).join(" ").trim() ||
    "";
  const resolvedInitialDocumentType = initialDocumentType || (editingClient ? "" : "Паспорт РФ");
  const documentTextMatch = String(editingClient?.document || "").match(/(\d{2}\s?\d{2})\s+(\d{6})/);
  const initialDocumentSeries = rawClientDocument.document_series || documentTextMatch?.[1] || "";
  const initialDocumentNumber = rawClientDocument.document_number || documentTextMatch?.[2] || "";
  const initialDocumentIssuedDate = rawClientDocument.document_issued_date
    ? (typeof formatApiDate === "function" ? formatApiDate(rawClientDocument.document_issued_date) : String(rawClientDocument.document_issued_date))
    : "";
  const initialDocumentIssuedBy =
    rawClientDocument.document_issued_by ||
    rawClientDocument.legacy_payload_json?.WhoGive ||
    rawClientDocument.legacy_payload_json?.["qdfMain.WhoGive"] ||
    editingClient?.documentIssuedBy ||
    "";
  const initialEmail = editingClient?.email || rawClientDocument.email || "";
  const initialProfession =
    editingClient?.profession ||
    rawClientDocument.profession ||
    rawClientDocument.legacy_payload_json?.profession ||
    "";
  const initialWorkPlace =
    editingClient?.workPlace ||
    rawClientDocument.work_place ||
    rawClientDocument.legacy_payload_json?.work_place ||
    "";
  const initialOrganization =
    editingClient?.organization ||
    rawClientDocument.organization ||
    rawClientDocument.legacy_payload_json?.organization ||
    "";

  openActionModal(
    modalTitle,
    `
      <form class="client-create-form" id="clientCreateForm">
        <div class="client-create-shell">
        <section class="client-create-section client-create-section--accent">
          <div class="client-create-section__head">
            <div>
              <span class="client-create-section__eyebrow">Карточка клиента</span>
              <strong>${heroTitle}</strong>
            </div>
            <span class="client-create-section__badge">${heroBadge}</span>
          </div>
        <div class="client-create-grid client-create-grid--names">
          <label class="field">
            <span>Фамилия</span>
            <input name="lastName" value="${escapeHtml(lastName)}" autocapitalize="words" />
          </label>
          <label class="field">
            <span>Имя</span>
            <input name="firstName" value="${escapeHtml(firstName)}" autocapitalize="words" />
          </label>
          <label class="field">
            <span>Отчество</span>
            <input name="middleName" value="${escapeHtml(middleName)}" autocapitalize="words" />
          </label>
        </div>

        <div class="client-create-grid client-create-grid--top">
          <label class="field">
            <span>Дата рождения</span>
            <input name="birthDate" data-date-mask value="${escapeHtml(editingClient?.birthDate || "")}" />
          </label>
          <label class="field">
            <span>Пол</span>
            <select name="gender">
              <option value="" ${defaultGender ? "" : "selected"}></option>
              <option ${defaultGender === "муж" || defaultGender === "M" ? "selected" : ""}>муж</option>
              <option ${defaultGender === "жен" || defaultGender === "F" ? "selected" : ""}>жен</option>
            </select>
          </label>
        </div>

        </section>

        <section class="client-create-section">
          <div class="client-create-section__head">
            <div>
              <span class="client-create-section__eyebrow">Документы и адрес</span>
              <strong>Идентификация пациента</strong>
            </div>
          </div>
        <div class="client-create-grid client-create-grid--document">
          <label class="field">
            <span>Документ</span>
            <select name="documentType">
              <option value="" ${resolvedInitialDocumentType ? "" : "selected"}></option>
              <option ${resolvedInitialDocumentType === "Паспорт РФ" ? "selected" : ""}>Паспорт РФ</option>
              <option ${resolvedInitialDocumentType === "Другое" ? "selected" : ""}>Другое</option>
            </select>
          </label>
          <label class="field">
            <span>Серия</span>
            <input name="passportSeries" value="${escapeHtml(initialDocumentSeries)}" />
          </label>
          <label class="field">
            <span>Номер</span>
            <input name="passportNumber" value="${escapeHtml(initialDocumentNumber)}" />
          </label>
          <label class="field">
            <span>Дата выдачи</span>
            <input name="passportDate" data-date-mask value="${escapeHtml(initialDocumentIssuedDate)}" />
          </label>
          <label class="field field--wide">
            <span>Кем выдан</span>
            <input name="issuedBy" value="${escapeHtml(initialDocumentIssuedBy)}" list="clientIssuedBySuggestions" />
          </label>
        </div>

        <div class="client-create-grid client-create-grid--address">
          ${renderClientAddressDatalists()}
          <label class="field">
            <span>Страна</span>
            <input name="country" value="${escapeHtml(initialAddress.country || (!editingClient ? CLIENT_DEFAULT_COUNTRY : ""))}" />
          </label>
          <label class="field">
            <span>Субъект РФ</span>
            <input name="subject" value="${escapeHtml(initialAddress.subject || "")}" list="clientSubjectSuggestions" />
          </label>
          <label class="field">
            <span>Район</span>
            <input name="district" value="${escapeHtml(initialAddress.district || "")}" list="clientDistrictSuggestions" />
          </label>
          <label class="field">
            <span>Город</span>
            <input name="city" value="${escapeHtml(initialAddress.city || "")}" list="clientCitySuggestions" />
          </label>
          <label class="field">
            <span>Улица</span>
            <input name="street" value="${escapeHtml(initialAddress.street || "")}" list="clientStreetSuggestions" />
          </label>
          <label class="field">
            <span>Дом</span>
            <input name="house" value="${escapeHtml(initialAddress.house || "")}" />
          </label>
          <label class="field">
            <span>Корпус</span>
            <input name="building" value="${escapeHtml(initialAddress.building || "")}" />
          </label>
          <label class="field">
            <span>Кв.</span>
            <input name="flat" value="${escapeHtml(initialAddress.flat || "")}" />
          </label>
        </div>

        </section>

        <section class="client-create-section">
          <div class="client-create-section__head">
            <div>
              <span class="client-create-section__eyebrow">Контакты и работа</span>
              <strong>Связь и контекст пациента</strong>
            </div>
          </div>
        <div class="client-create-grid client-create-grid--contacts">
          <label class="field">
            <span>Телефон</span>
            <input name="phone" value="${escapeHtml(editingClient ? editingClient.phone || "" : "+7 ")}" />
          </label>
          <label class="field">
            <span>E-mail</span>
            <input name="email" value="${escapeHtml(initialEmail)}" />
          </label>
          <label class="field">
            <span>СНИЛС</span>
            <input name="snils" value="${escapeHtml(editingClient?.snils || "")}" />
          </label>
          <label class="field">
            <span>Агент</span>
            <input name="agent" value="${escapeHtml(editingClient?.agent || "")}" list="clientAgentSuggestions" />
          </label>
        </div>

        <div class="client-create-grid client-create-grid--contacts">
          <label class="field">
            <span>Профессия</span>
            <input name="profession" value="${escapeHtml(initialProfession)}" list="clientProfessionSuggestions" />
          </label>
          <label class="field">
            <span>Место работы</span>
            <input name="workPlace" value="${escapeHtml(initialWorkPlace)}" list="clientWorkPlaceSuggestions" />
          </label>
          <label class="field">
            <span>Организация</span>
            <input name="organization" value="${escapeHtml(initialOrganization)}" list="clientOrganizationSuggestions" />
          </label>
        </div>

        <label class="field">
          <span>Комментарий</span>
          <textarea name="comment" rows="2">${escapeHtml(editingClient?.note || "")}</textarea>
        </label>

        </section>

        <section class="client-create-section">
          <div class="client-create-section__head">
            <div>
              <span class="client-create-section__eyebrow">Услуги и оформление</span>
              <strong>Выбор сценария обслуживания</strong>
            </div>
          </div>
        <div id="serviceSelectorContainer">
          ${renderClientServiceSelector(initialSelectedServices)}
        </div>
        <div id="clientDriverPanelContainer">
          ${renderClientDriverClassicPanel(initialSelectedServices)}
        </div>
        <div id="clientPaymentContainer">
          ${renderClientPaymentRows(initialSelectedServices)}
        </div>

        </section>

        <div class="client-create-actions">
          <button type="button" class="ghost-button" id="cancelClientCreate">Отмена</button>
          <button type="submit" class="ghost-button" name="clientSubmitAction" value="contract">${encounterMode ? "Сохранить + договор" : "ОК + договор"}</button>
          <button type="submit" class="primary-button">${primarySubmitLabel}</button>
        </div>
        </div>
      </form>
    `,
  );

  const form = document.getElementById("clientCreateForm");
  const cancel = document.getElementById("cancelClientCreate");
  const contractSubmitButton = form?.querySelector('[name="clientSubmitAction"][value="contract"]');
  const defaultSubmitButton = form?.querySelector('.primary-button[type="submit"], .primary-button:not([type])');

  if (form) {
    attachDateMask(form);
    form.querySelectorAll(".field").forEach((field) => {
      if (!field.querySelector("input, select, textarea")) field.remove();
    });
    bindClientNameCapitalization(form);
    bindClientAddressAutocomplete(form, { defaultCountry: Boolean(editingClient) });

    form.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) {
        return;
      }

      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (target.tagName === "TEXTAREA" || target.tagName === "BUTTON") return;
      if (target.closest("#serviceSelectorContainer, #clientDriverPanelContainer, #clientPaymentContainer")) return;

      const focusableFields = Array.from(
        form.querySelectorAll(
          'input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled])',
        ),
      ).filter((element) => {
        if (!(element instanceof HTMLElement)) return false;
        if (element.tagName === "TEXTAREA") return false;
        if (element.closest("#serviceSelectorContainer, #clientDriverPanelContainer, #clientPaymentContainer")) {
          return false;
        }
        return element.offsetParent !== null;
      });

      const currentIndex = focusableFields.indexOf(target);
      if (currentIndex < 0) return;

      event.preventDefault();
      const nextField = focusableFields[currentIndex + 1];
      if (nextField instanceof HTMLElement) {
        nextField.focus();
        if (typeof nextField.select === "function" && nextField.tagName === "INPUT") {
          nextField.select();
        }
      }
    });
  }

  bindClientServiceGroupButtons();
  bindClientDriverCategoryCheckboxes();
  bindClientPaymentRows();

  cancel?.addEventListener("click", () => {
    actionModal.classList.add("hidden");
  });

  contractSubmitButton?.addEventListener("click", () => {
    clientModalSubmitAction = "contract";
  });

  defaultSubmitButton?.addEventListener("click", () => {
    clientModalSubmitAction = "save";
  });

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const shouldOpenContract = clientModalSubmitAction === "contract" || event.submitter?.value === "contract";
    const formData = new FormData(form);
    ["lastName", "firstName", "middleName"].forEach((fieldName) => {
      formData.set(fieldName, formatClientNameInputValue(formData.get(fieldName)));
    });
    const encounterDateText = String(
      editingClient?.encounterDate || editingClient?.lastVisit || formatDateTime(new Date()),
    ).trim();
    const center = appState.centerFilter === "all" ? "Медцентр 1" : appState.centerFilter;
    const fullName = [formData.get("lastName"), formData.get("firstName"), formData.get("middleName")]
      .map((value) => String(value || "").trim())
      .filter(Boolean)
      .join(" ");
    const selectedServiceValues = getClientModalSelectedServicesFromDom()
      .map((value) => String(value).trim())
      .filter(Boolean);
    const selectedServiceIds = getClientServiceIdsByNames(selectedServiceValues);
    const serviceDetails = buildClientServiceDetails(selectedServiceValues);
    const paymentSummary = getClientVisitPaymentSummary(selectedServiceValues, serviceDetails, formData.get("comment"));
    const visitAmount = window.calculateVisitAmountByIds
      ? window.calculateVisitAmountByIds(selectedServiceIds, serviceDetails)
      : window.calculateVisitAmount?.(selectedServiceValues);
    const formSex = String(formData.get("gender") || "").toLowerCase().startsWith("ж") ? "F" : "M";

    const isCreated = !editingClient;

    let targetClient =
      editingClient ||
      {
        id: `draft-${Date.now()}`,
        patientNumber: "",
      };

    Object.assign(targetClient, {
      fullName: fullName || "Новый клиент",
      birthDate: String(formData.get("birthDate") || "").trim(),
      sex: formSex,
      gender: formSex,
      phone: String(formData.get("phone") || "").trim(),
      profession: String(formData.get("profession") || "").trim(),
      workPlace: String(formData.get("workPlace") || "").trim(),
      organization: String(formData.get("organization") || "").trim(),
      center: editingClient?.center || center,
      document: [
        String(formData.get("documentType") || "").trim(),
        String(formData.get("passportSeries") || "").trim(),
        String(formData.get("passportNumber") || "").trim(),
      ]
        .filter(Boolean)
        .join(" "),
      snils: String(formData.get("snils") || "").trim(),
      agent: String(formData.get("agent") || "").trim(),
      note:
        String(formData.get("comment") || "").trim() ||
        (String(formData.get("city") || "").trim() || String(formData.get("street") || "").trim()
          ? `Адрес: ${String(formData.get("city") || "").trim()}, ${String(formData.get("street") || "").trim()}`.trim()
          : ""),
      encounterDate: encounterDateText,
      lastVisit: encounterDateText,
      services: selectedServiceValues,
    });

    try {
      const addressText = [
        formData.get("country"),
        formData.get("subject"),
        formData.get("district"),
        formData.get("city"),
        formData.get("street"),
        formData.get("house"),
        formData.get("building"),
        formData.get("flat"),
      ]
        .map((value) => String(value || "").trim())
        .filter(Boolean)
        .join(", ");
      saveClientAddressSuggestion({
        subject: formData.get("subject"),
        district: formData.get("district"),
        city: formData.get("city"),
        street: formData.get("street"),
      });
      saveClientIssuedBySuggestion(formData.get("issuedBy"));
      rememberClientRecentFields({
        documentType: formData.get("documentType"),
        issuedBy: formData.get("issuedBy"),
        country: formData.get("country"),
        subject: formData.get("subject"),
        district: formData.get("district"),
        city: formData.get("city"),
        street: formData.get("street"),
        agent: formData.get("agent"),
        profession: formData.get("profession"),
        workPlace: formData.get("workPlace"),
        organization: formData.get("organization"),
      });
      const backendId = editingClient?.backendId || (editingClient?.rawApiClient ? editingClient.id : null);
      if (!window.apiRequest) throw new Error("Backend API недоступен");
      const savedClient = await window.apiRequest?.(backendId ? `/clients/${backendId}` : "/clients", {
        method: backendId ? "PUT" : "POST",
        body: JSON.stringify({
          last_name: String(formData.get("lastName") || "").trim() || "Без фамилии",
          first_name: String(formData.get("firstName") || "").trim() || "Без имени",
          middle_name: String(formData.get("middleName") || "").trim() || null,
          birth_date: window.parseRuDateToIso?.(formData.get("birthDate")) || "1900-01-01",
          sex: formSex,
          phone: String(formData.get("phone") || "").trim() || null,
          email: String(formData.get("email") || "").trim() || null,
          document_type: String(formData.get("documentType") || "").trim() || null,
          document_series: String(formData.get("passportSeries") || "").trim() || null,
          document_number: String(formData.get("passportNumber") || "").trim() || null,
          document_issued_by: String(formData.get("issuedBy") || "").trim() || null,
          document_issued_date: window.parseRuDateToIso?.(formData.get("passportDate"), "") || null,
          snils: String(formData.get("snils") || "").trim() || null,
          address_text: addressText || null,
          profession: String(formData.get("profession") || "").trim() || null,
          work_place: String(formData.get("workPlace") || "").trim() || null,
          organization: String(formData.get("organization") || "").trim() || null,
          encounter_date_text: encounterDateText || null,
          notes: String(formData.get("comment") || "").trim() || null,
          registration_text: addressText || null,
          legacy_payload_json: {
            source: "demo-client-modal",
            services: selectedServiceValues,
            agent: String(formData.get("agent") || "").trim() || null,
            profession: String(formData.get("profession") || "").trim() || null,
            work_place: String(formData.get("workPlace") || "").trim() || null,
            organization: String(formData.get("organization") || "").trim() || null,
          },
        }),
      });
      if (savedClient) {
        const savedMapped = window.upsertClientInMemory?.(savedClient);
        if (savedMapped) {
          Object.assign(savedMapped, {
            ...targetClient,
            id: savedClient.id,
            backendId: savedClient.id,
            patientNumber: savedClient.patient_number,
            cardNumber: savedClient.card_number || targetClient.cardNumber || (savedClient.patient_number ? String(savedClient.patient_number).padStart(7, "0") : ""),
            agent: String(formData.get("agent") || "").trim() || savedMapped.agent || "",
            profession: String(formData.get("profession") || "").trim() || savedMapped.profession || "",
            workPlace: String(formData.get("workPlace") || "").trim() || savedMapped.workPlace || "",
            organization: String(formData.get("organization") || "").trim() || savedMapped.organization || "",
            sex: savedClient.sex || formSex,
            gender: savedClient.sex || formSex,
            rawApiClient: savedClient,
          });
          targetClient = savedMapped;
          targetClient = window.showClientInDashboardResults?.(targetClient, {
            resetSearch: isCreated,
            refresh: false,
          }) || targetClient;
        }
      }
    } catch (error) {
      console.warn("Client backend save failed", error);
      showToast(window.humanizeApiError?.(error, "Backend не сохранил клиента") || "Backend не сохранил клиента");
      return;
    }

    if (isCreated && !data.clients.some((client) => String(client.id) === String(targetClient.id))) {
      targetClient.__demoCreated = true;
      data.clients.unshift(targetClient);
    }

    appState.selectedClientId = targetClient.id;
    appState.clientSearch = isCreated ? "" : targetClient.fullName || fullName;
    data.backendSearch = appState.clientSearch.trim();
    window.markClientChanged?.(targetClient, isCreated);

    const shouldCreateOrUpdateVisit = isCreated || encounterMode || selectedServiceValues.length;
    const currentVisit =
      shouldCreateOrUpdateVisit
        ? window.createVisitForClientIfNeeded?.(targetClient.id, {
            serviceNames: selectedServiceValues,
            serviceIds: selectedServiceIds,
            serviceDetails,
            clientSex: formSex,
            amount: visitAmount,
            paymentType: paymentSummary.paymentType,
            comment: paymentSummary.comment,
            forceNew: encounterMode,
          })
        : window.getCurrentVisitForClient?.(targetClient.id);
    if (currentVisit && currentVisit.status !== "closed") {
      const visitPatch = {
        serviceNames: selectedServiceValues,
        serviceIds: selectedServiceIds,
        serviceDetails,
        clientSex: formSex,
        amount: visitAmount ?? currentVisit.amount,
        paymentType: paymentSummary.paymentType,
        comment: paymentSummary.comment,
      };
      const syncedVisit = isCreated
        ? Object.assign(currentVisit, visitPatch)
        : window.updateVisit?.(currentVisit.id, visitPatch);
      const effectiveVisit = syncedVisit || Object.assign(currentVisit, visitPatch);
      const effectiveEncounterDate = String(effectiveVisit?.visitDate || encounterDateText || "").trim();
      if (effectiveEncounterDate) {
        targetClient.encounterDate = effectiveEncounterDate;
        targetClient.lastVisit = effectiveEncounterDate;
        if (targetClient.rawApiClient) {
          targetClient.rawApiClient.encounter_date_text = effectiveEncounterDate;
        }
      }
      const backendSyncedVisit = await window.syncVisitToBackend?.(effectiveVisit, targetClient);
      if (backendSyncedVisit?.backendId) {
        effectiveVisit.backendId = backendSyncedVisit.backendId;
      }
      await window.ensureRequiredDoctorExamsForVisit?.(targetClient, effectiveVisit, { syncToBackend: Boolean(effectiveVisit?.backendId) });
      await window.loadDashboardDoctorStatuses?.([targetClient], { render: true });
      targetClient = window.showClientInDashboardResults?.(targetClient, {
        resetSearch: false,
        refresh: true,
      }) || targetClient;
      window.persistDemoState?.();
    }

    actionModal.classList.add("hidden");
    if (shouldOpenContract) {
      appState.page = "blanks";
    }
    renderApp();
    if (shouldOpenContract) {
      await window.openDemoDocument?.("contract", { autoOpenFile: true });
      return;
    }
    showToast(
      encounterMode
        ? "Обращение сохранено"
        : (editingClient ? `Клиент ${fullName || "клиент"} обновлен` : `Клиент ${fullName || "Новый клиент"} добавлен`),
    );
  });
}

window.openClientModal = openClientModal;
window.renderClientServiceSelector = renderClientServiceSelector;
