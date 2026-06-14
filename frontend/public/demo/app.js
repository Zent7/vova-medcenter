const API_BASE_URL = window.DEMO_API_BASE_URL || "http://127.0.0.1:8000/api/v1";


function getLocalDateInputValue(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

const appState = {
  page: "dashboard",
  dashboardPage: 1,
  auth: {
    accessToken: "",
    userName: "",
    roleCode: "",
    roleName: "",
  },
  selectedClientId: null,
  centerFilter: "all",
  clientSearch: "",
  clientEncounterDate: "",
  clientEncounterDateFrom: "",
  clientEncounterDateTo: getLocalDateInputValue(),
  serviceGroupFilter: "all",
  visitServiceGroupFilter: "all",
  visitServiceSearch: "",
  cashDateFrom: getLocalDateInputValue(),
  cashDateTo: getLocalDateInputValue(),
  reportDateFrom: getLocalDateInputValue(),
  reportDateTo: getLocalDateInputValue(),
  calendarFilter: "active",
  calendarServiceGroupFilter: "all",
  blanksTab: "overview",
  blanksFormOpen: false,
  blanksFilterStatus: "all",
  blanksFilterBatchId: "all",
  blanksSearch: "",
  restoreInputId: null,
  activeVisitId: null,
  doctorExamModal: {
    isOpen: false,
    clientId: null,
    visitId: null,
    doctorRoleId: null,
  },
};

const demoParams = new URLSearchParams(window.location.search);
if (demoParams.get("employeeAuth") === "chairman") {
  appState.page = "employee";
  appState.auth = {
    accessToken: "demo-token-2",
    userName: "Председатель комиссии",
    roleCode: "chairman",
    roleName: "Председатель",
  };
}

let serviceGroups = [];
let doctorRoles = [];
let structuredServices = [];

const data = {
  serviceCatalog:
    structuredServices.length
      ? structuredServices
          .filter((service) => service.isActive !== false)
          .slice()
          .map((service) => service.name)
      : [
          "Справка водительская",
          "Справка в бассейн",
          "Медосмотр",
          "ЭКГ",
          "Флюорография",
          "Психиатр",
          "Нарколог",
          "Терапевт",
          "Офтальмолог",
          "ЛОР",
        ],
  clients: [],
  visits: [],
  documents: [],
  doctorExams: [],
  mkb10History: [],
  backendClients: [],
  backendClientsLoaded: false,
  dashboardDoctorStatuses: {},
  dashboardDoctorStatusesLoading: false,
  dashboardDoctorStatusesError: "",
  dashboardDoctorStatusesRequestId: 0,
  backendSearch: "",
  backendSearchLoading: false,
  backendSearchError: "",
  centers: [],
  centersLoaded: false,
  centersLoadingPromise: null,
  serverServices: [],
  serverServicesLoaded: false,
  documentTemplates: [],
  documentTemplatesLoaded: false,
  generatedDocuments: [],
  documentJournals: [],
  spoiledBlanks: [],
  blanksTypes: [],
  blanksStats: [],
  blanksBatches: [],
  blanksForms: [],
  blanksLoading: false,
  blanksLoaded: false,
  blanksError: "",
  blanksFormError: "",
  blanksFormSaving: false,
  patientConsents: [],
  medicalRecords: [],
  medicalRecordEntries: [],
  medicalRecordEditMode: false,
  medicalRecordSaving: false,
  medicalRecordSaveError: "",
  workflowDataLoaded: false,
  workflowDataLoading: false,
  workflowDataError: "",
  recallItems: [],
  recallItemsLoaded: false,
  recallItemsLoading: false,
  recallItemsError: "",
  importFileName: "",
  importFileBase64: "",
  importPreview: null,
  importLoading: false,
  importError: "",
  importSuccess: "",
  clientOverrides: {},
  doctorDirectory: {},
  servicesDirty: false,
  staffUsers: [],
  staffRoles: [],
  staffLoading: false,
  staffError: "",
  staffCreateError: "",
  lastCreatedStaffUser: null,
  reportSummary: null,
  reportLoading: false,
  reportError: "",
};

let clientSearchTimer = null;
let clientSearchRequestId = 0;
let clientSearchAbortController = null;
let clientRowClickTimer = null;
const DASHBOARD_PAGE_SIZE = 50;
const CLIENT_ROW_SINGLE_CLICK_DELAY = 300;

const DEMO_STORAGE_KEY = "vova-medcenter-demo-state-v2";
const COLUMN_WIDTHS_STORAGE_KEY = "vova-medcenter-column-widths-v1";
const SELECTION_STORAGE_KEY = "vova-medcenter-selection-v1";
const MEDICAL_RECORD_PANEL_HEIGHT_KEY = "vova-medcenter-medical-record-height-v1";

function getMedicalRecordPanelHeight() {
  try {
    const raw = window.localStorage?.getItem(MEDICAL_RECORD_PANEL_HEIGHT_KEY);
    const parsed = Number.parseInt(String(raw || ""), 10);
    if (Number.isFinite(parsed)) {
      return Math.min(520, Math.max(160, parsed));
    }
  } catch (error) {
    console.warn("Не удалось прочитать высоту медкарты", error);
  }
  return 280;
}

function persistMedicalRecordPanelHeight(height) {
  try {
    const normalized = Math.min(520, Math.max(160, Math.round(Number(height) || 280)));
    window.localStorage?.setItem(MEDICAL_RECORD_PANEL_HEIGHT_KEY, String(normalized));
  } catch (error) {
    console.warn("Не удалось сохранить высоту медкарты", error);
  }
}

function initializeFallbackServiceCatalog() {
  const fallback = window.servicesData;
  if (!fallback || !Array.isArray(fallback.services)) return;

  const fallbackRoleCodes = {
    1: "therapist",
    2: "psychiatrist",
    3: "psychiatrist-narcologist",
    4: "neurologist",
    5: "otolaryngologist",
    6: "gynecologist",
    7: "ophthalmologist",
    8: "dermatologist",
    9: "dentist",
    10: "surgeon",
    11: "phthisiatrist",
    12: "uzist",
    13: "chairman",
  };

  serviceGroups = Array.isArray(fallback.serviceGroups)
    ? fallback.serviceGroups.map((group) => ({
        ...group,
        code: group.code || `legacy-group-${group.id}`,
      }))
    : [];
  doctorRoles = Array.isArray(fallback.doctorRoles)
    ? fallback.doctorRoles.map((role) => ({
        ...role,
        code: role.code || fallbackRoleCodes[Number(role.id)] || String(role.id),
      }))
    : [];

  if (!doctorRoles.some((role) => String(role.id) === "13")) {
    doctorRoles.push({
      id: 13,
      code: "chairman",
      name: "Председатель",
      sortOrder: 130,
      isActive: true,
    });
  }

  data.serverServices = fallback.services.map((service) => ({
    ...service,
    backendId: service.backendId || service.id,
    legacySourceId: service.legacySourceId || service.legacy_source_id || service.id,
    recallAfterDays: service.recallAfterDays || null,
    doctorRoleIds: Array.isArray(service.doctorRoleIds) ? service.doctorRoleIds : [],
  }));
  structuredServices = data.serverServices.slice();
  data.serverServicesLoaded = true;
  refreshServiceCatalog();
}

loadColumnWidths();
initializeFallbackServiceCatalog();
applyPersistedDemoState();

const pageTitle = document.getElementById("page-title");
const navRoot = document.getElementById("nav");
const contentRoot = document.getElementById("content");
const loginModal = document.getElementById("loginModal");
const authStatusLabel = document.getElementById("authStatusLabel");
const actionModal = document.getElementById("actionModal");
const actionModalTitle = document.getElementById("actionModalTitle");
const actionModalContent = document.getElementById("actionModalContent");
const centerSelect = document.getElementById("centerSelect");
const toast = document.getElementById("toast");

const navItems = [
  { id: "dashboard", label: "Главная" },
  { id: "chart", label: "Амбулаторная карта", toast: "Открыта амбулаторная карта" },
  { id: "calendar", label: "Календарь", toast: "Открыт календарь сроков" },
  { id: "doctors", label: "Врачи", toast: "Открыт раздел: Врачи" },
  { id: "services", label: "Услуги", toast: "Открыт раздел: Услуги" },
  { id: "blanks", label: "Бланки", toast: "Открыт раздел: Бланки" },
  { id: "templates", label: "Шаблоны", toast: "Открыт раздел: Шаблоны" },
  { id: "upload", label: "Загрузка клиентов", toast: "Открыта загрузка клиентов" },
  { id: "employee", label: "Сотрудник", toast: "Открыт блок: Сотрудник" },
  { id: "cash", label: "Касса", toast: "Открыт блок: Касса" },
  { id: "xml", label: "XML", toast: "Открыт блок: XML" },
  { id: "reports", label: "Отчеты", toast: "Открыт блок: Отчеты" },
  { id: "harmfulness", label: "Пункты вредности", toast: "Открыт блок: Пункты вредности" },
];

function canManageEmployeeWorkspace() {
  return appState.auth.roleCode === "chairman";
}

function canAccessReportsWorkspace() {
  return appState.auth.roleCode === "chairman";
}

function ensureDemoAuthConsistency() {
  if (appState.auth.roleCode === "chairman" && !appState.auth.accessToken) {
    appState.auth.accessToken = "demo-token-2";
    appState.auth.userName = appState.auth.userName || "Председатель комиссии";
    appState.auth.roleName = appState.auth.roleName || "Председатель";
  }
}

const columnKeys = [
  "encounterDate",
  "fio",
  "birth",
  "registration",
  "category",
  "reference",
  "gynecologist",
  "stomatologist",
  "dermatologist",
  "neurologist",
  "surgeon",
  "otolaryngologist",
  "ophthalmologist",
  "therapist",
  "psychiatrist",
  "infectionist",
  "phthisiatrician",
  "uzist",
  "chairman",
  "note",
  "cardNumber",
  "organization",
  "agent",
];

const doctorRoleByExcelColumn = {
  gynecologist: "gynecologist",
  stomatologist: "dentist",
  dermatologist: "dermatologist",
  neurologist: "neurologist",
  surgeon: "surgeon",
  otolaryngologist: "otolaryngologist",
  ophthalmologist: "ophthalmologist",
  therapist: "therapist",
  psychiatrist: "psychiatrist",
  infectionist: "infectionist",
  phthisiatrician: "phthisiatrist",
  uzist: "uzist",
  chairman: "chairman",
};

const DRIVER_SERVICE_LEGACY_IDS = new Set([8, 29]);
const TRACTOR_SERVICE_LEGACY_IDS = new Set([7]);
const GIMS_SERVICE_LEGACY_IDS = new Set([37]);
const LMK_SERVICE_LEGACY_IDS = new Set([18, 19]);
const PROF_SERVICE_LEGACY_IDS = new Set([16]);
const CERTIFICATE_SERVICE_LEGACY_IDS = new Set([2, 3, 4, 5, 9, 10, 11, 12, 24, 30, 31, 32, 38, 39]);
const SPORT_SERVICE_LEGACY_IDS = new Set([4, 5]);
const EKG_SERVICE_LEGACY_IDS = new Set([6, 20, 21, 27]);
const SPORT_SERVICE_NAMES = new Set([
  "справка для участия в соревнованиях",
  "справка спорт + экг",
  "справка для спорта",
  "спортивная справка",
]);
const CHAIRMAN_FORM_CONFIGS = {
  driver: {
    type: "driver",
    label: "Председатель: водительская комиссия",
    templateType: "driver",
    printMode: "driver-flow",
    note: "Используется водительский шаблон и бланк водительской комиссии.",
  },
  tractor: {
    type: "tractor",
    label: "Председатель: тракторная/071У комиссия",
    templateType: "071",
    printMode: "document",
    note: "Подтягивается шаблон 071У или тракторной справки.",
  },
  gims: {
    type: "gims",
    label: "Председатель: ГИМС",
    templateType: "gims",
    printMode: "document",
    note: "Подтягивается шаблон ГИМС.",
  },
  lmk: {
    type: "lmk",
    label: "Председатель: ЛМК",
    templateType: "lmk",
    printMode: "document",
    note: "Подтягивается шаблон ЛМК.",
  },
  prof: {
    type: "prof",
    label: "Председатель: профосмотр 29Н",
    templateType: "prof",
    printMode: "document",
    note: "Подтягиваются шаблоны заключения 29Н и выписки.",
  },
  marine: {
    type: "marine",
    label: "Председатель: морская комиссия",
    templateType: "marine",
    printMode: "document",
    note: "Подтягивается морской сертификат.",
  },
  drug: {
    type: "drug",
    label: "Председатель: drug/alcohol test",
    templateType: "drug",
    printMode: "document",
    note: "Подтягивается шаблон drug/alcohol test.",
  },
  sport: {
    type: "sport",
    label: "Председатель: спортивная справка",
    templateType: "sport",
    printMode: "document",
    note: "Подтягивается спортивный шаблон.",
  },
  ekg: {
    type: "ekg",
    label: "ЭКГ",
    templateType: "ekg",
    printMode: "service-card",
    note: "Открывается отдельная карточка ЭКГ без водительских категорий.",
  },
  certificate086: {
    type: "certificate086",
    label: "Председатель: справка 086у",
    templateType: "086",
    printMode: "document",
    note: "Подтягивается шаблон справки 086у.",
  },
  certificate070: {
    type: "certificate070",
    label: "Председатель: справка 070у",
    templateType: "070",
    printMode: "document",
    note: "Подтягивается шаблон справки 070у.",
  },
  certificate072: {
    type: "certificate072",
    label: "Председатель: санаторно-курортная карта 072у",
    templateType: "072",
    printMode: "document",
    note: "Подтягивается шаблон 072у.",
  },
  certificate082: {
    type: "certificate082",
    label: "Председатель: справка 082у",
    templateType: "082",
    printMode: "document",
    note: "Подтягивается шаблон справки 082у.",
  },
  certificate095: {
    type: "certificate095",
    label: "Председатель: справка 095у",
    templateType: "095",
    printMode: "document",
    note: "Подтягивается шаблон справки 095у.",
  },
  gsu: {
    type: "gsu",
    label: "Председатель: справка 001 ГСУ",
    templateType: "gsu",
    printMode: "document",
    note: "Подтягивается шаблон справки 001 ГСУ.",
  },
  gostaina: {
    type: "gostaina",
    label: "Председатель: справка гостайна",
    templateType: "gostaina",
    printMode: "document",
    note: "Подтягивается шаблон справки для гостайны.",
  },
  gto: {
    type: "gto",
    label: "Председатель: справка ГТО",
    templateType: "gto",
    printMode: "document",
    note: "Подтягивается шаблон справки ГТО.",
  },
  pool: {
    type: "pool",
    label: "Председатель: справка в бассейн",
    templateType: "pool",
    printMode: "document",
    note: "Подтягивается шаблон справки в бассейн.",
  },
  guard: {
    type: "guard",
    label: "Председатель: справка ЧОД/охрана",
    templateType: "guard",
    printMode: "document",
    note: "Подтягивается шаблон справки для охраны.",
  },
  certificate: {
    type: "certificate",
    label: "Председатель: справка",
    templateType: "medical",
    printMode: "document",
    note: "Шаблон подбирается по выбранной услуге.",
  },
  default: {
    type: "default",
    label: "Председатель комиссии",
    templateType: "driver",
    printMode: "driver-flow",
    note: "Если тип услуги не определен, используется общий сценарий председателя.",
  },
};
const DRIVER_BASE_CATEGORIES = new Set(["A", "B", "M", "A1", "B1"]);
const DRIVER_DEFAULT_CATEGORIES = ["A", "B", "C", "D", "BE", "M"];
const DRIVER_CATEGORY_OPTIONS = ["A", "B", "C", "D", "BE", "CE", "DE", "Tm", "Tb", "M", "A1", "B1", "C1", "D1", "C1E", "D1E"];
const DRIVER_CATEGORY_ADVANCED_ROLES = ["therapist", "ophthalmologist", "neurologist", "otolaryngologist", "chairman"];
const DRIVER_CATEGORY_BASE_ROLES = ["therapist", "ophthalmologist", "chairman"];
const DRIVER_CATEGORY_DOCTOR_RULES = new Map([
  ["A", ["therapist", "ophthalmologist", "chairman"]],
  ["B", ["therapist", "ophthalmologist", "chairman"]],
  ["AB", ["therapist", "ophthalmologist", "chairman"]],
  ["ABE", ["therapist", "ophthalmologist", "neurologist", "otolaryngologist", "chairman"]],
  ["ABC", ["therapist", "ophthalmologist", "neurologist", "otolaryngologist", "chairman"]],
  ["ABCD", ["therapist", "ophthalmologist", "neurologist", "otolaryngologist", "chairman"]],
  ["ABCDE", ["therapist", "ophthalmologist", "neurologist", "otolaryngologist", "chairman"]],
  ["BC", ["therapist", "ophthalmologist", "neurologist", "otolaryngologist", "chairman"]],
  ["BD", ["therapist", "ophthalmologist", "neurologist", "otolaryngologist", "chairman"]],
  ["BCDE", ["therapist", "ophthalmologist", "neurologist", "otolaryngologist", "chairman"]],
  ["BCD", ["therapist", "ophthalmologist", "neurologist", "otolaryngologist", "chairman"]],
  ["BE", ["therapist", "ophthalmologist", "neurologist", "otolaryngologist", "chairman"]],
  ["BCE", ["therapist", "ophthalmologist", "neurologist", "otolaryngologist", "chairman"]],
  ["ABCDE,TB,TM", ["therapist", "ophthalmologist", "neurologist", "otolaryngologist", "chairman"]],
  ["BCE,TB,TM", ["therapist", "ophthalmologist", "neurologist", "otolaryngologist", "chairman"]],
  ["ABC,TB,TM", ["therapist", "ophthalmologist", "neurologist", "otolaryngologist", "chairman"]],
]);
const OPERATOR_SERVICE_PRIORITY_BY_LEGACY_ID = new Map([
  [8, 1],
  [29, 2],
  [18, 3],
  [19, 4],
  [7, 5],
  [37, 6],
  [12, 7],
  [2, 8],
  [11, 9],
  [4, 10],
  [5, 11],
  [3, 12],
  [27, 13],
  [30, 14],
  [24, 15],
  [31, 16],
  [10, 17],
  [32, 18],
  [38, 19],
]);

function getOperatorServicePriority(service) {
  return OPERATOR_SERVICE_PRIORITY_BY_LEGACY_ID.get(Number(service?.legacySourceId)) || 1000;
}

function compareServicesForOperator(a, b) {
  const priorityDiff = getOperatorServicePriority(a) - getOperatorServicePriority(b);
  if (priorityDiff !== 0) return priorityDiff;
  if ((a.groupId || 0) !== (b.groupId || 0)) return (a.groupId || 0) - (b.groupId || 0);
  return (a.sortOrder || 0) - (b.sortOrder || 0);
}

function showToast(message) {
  if (!toast) return;
  toast.textContent = repairDemoText(message);
  toast.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add("hidden"), 2400);
}

async function copyTextToClipboard(value, successMessage = "Скопировано") {
  const text = String(value || "").trim();
  if (!text) {
    showToast("Нечего копировать");
    return false;
  }

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
    showToast(successMessage);
    return true;
  } catch (error) {
    showToast("Не удалось скопировать");
    return false;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function displayTableValue(value, fallback = "—") {
  const text = value === null || value === undefined || value === "" ? fallback : String(value);
  return text;
}

function renderCopyableValue(value, label, options = {}) {
  const text = String(value || "").trim();
  const fallback = options.fallback || "не указано";
  const displayValue = text || fallback;
  const className = options.className || "copyable-value";
  const copyLabel = label || "значение";
  const title = text ? `Скопировать ${copyLabel}` : `${copyLabel} не указано`;
  const copyMessage = options.copyMessage || `${copyLabel} скопировано`;
  const keyboardAttrs = options.keyboard === false ? "" : ' tabindex="0" role="button"';
  return `
    <strong
      class="${className}${text ? "" : ` ${className}--empty`}"
      title="${escapeHtml(title)}"
      ${text ? `${keyboardAttrs} data-copy-value="${escapeHtml(text)}" data-copy-message="${escapeHtml(copyMessage)}"` : ""}
    >
      <span>${escapeHtml(displayValue)}</span>
      ${text ? '<i aria-hidden="true">коп.</i>' : ""}
    </strong>
  `;
}

function resolveAdmissionCategoryValue(categoryValue, services) {
  const directValue = String(categoryValue || "").trim();
  if (directValue) return directValue;
  const serviceNames = Array.isArray(services)
    ? services.map((service) => String(service || "").trim()).filter(Boolean)
    : [];
  return serviceNames.join(", ");
}

const _repairDemoTextMap = {
    "Р вЂњР В»Р В°Р Р†Р Р…Р В°РЎРЏ": "Главная",
    "Р вЂ™РЎР‚Р В°РЎвЂЎР С‘": "Врачи",
    "Р Р€РЎРѓР В»РЎС“Р С–Р С‘": "Услуги",
    "Р вЂР В»Р В°Р Р…Р С”Р С‘": "Бланки",
    "Р РЃР В°Р В±Р В»Р С•Р Р…РЎвЂ№": "Шаблоны",
    "Р вЂ”Р В°Р С–РЎР‚РЎС“Р В·Р С”Р В° РЎРѓР С—РЎР‚Р В°Р Р†Р С”Р С‘": "Загрузка справки",
    "Р РЋР С•РЎвЂљРЎР‚РЎС“Р Т‘Р Р…Р С‘Р С”": "Сотрудник",
    "Р С™Р В°РЎРѓРЎРѓР В°": "Касса",
    "Р С›РЎвЂљРЎвЂЎР ВµРЎвЂљРЎвЂ№": "Отчеты",
    "РџСѓРЅРєС‚С‹ Р Р†РЎР‚Р ВµР Т‘Р Р…Р С•РЎРѓРЎвЂљР С‘": "Пункты вредности",
    "Р“РёРЅРµРєРѕР»РѕРі": "Гинеколог",
    "Р РЋРЎвЂљР С•Р СР В°РЎвЂљР С•Р В»Р С•Р С–": "Стоматолог",
    "Р вЂќР ВµРЎР‚Р СР В°РЎвЂљР С•Р В»Р С•Р С–": "Дерматолог",
    "Р СњР ВµР Р†РЎР‚Р С•Р В»Р С•Р С–": "Невролог",
    "Р ТђР С‘РЎР‚РЎС“РЎР‚Р С–": "Хирург",
    "Р С›РЎвЂљР С•Р В»Р В°РЎР‚Р С‘Р Р…Р С–Р С•Р В»Р С•Р С–": "Отоларинголог",
    "Р С›РЎвЂћРЎвЂљР В°Р В»РЎРЉР СР С•Р В»Р С•Р С–": "Офтальмолог",
    "Р СћР ВµРЎР‚Р В°Р С—Р ВµР Р†РЎвЂљ": "Терапевт",
    "Р СџРЎРѓР С‘РЎвЂ¦Р С‘Р В°РЎвЂљРЎР‚": "Психиатр",
    "Р ВР Р…РЎвЂћР ВµР С”РЎвЂ Р С‘Р С•Р Р…Р С‘РЎРѓРЎвЂљ": "Инфекционист",
    "Р В¤РЎвЂљР С‘Р В·Р С‘Р В°РЎвЂљРЎР‚": "Фтизиатр",
    "Р Р€Р В·Р С‘РЎРѓРЎвЂљ": "Узист",
    "Р СџРЎР‚Р ВµР Т‘РЎРѓР ВµР Т‘Р В°РЎвЂљР ВµР В»РЎРЉ": "Председатель",
    "Р В¤Р ВР С›": "ФИО",
    "Р вЂќР В°РЎвЂљР В° РЎР‚Р С•Р В¶Р Т‘Р ВµР Р…Р С‘РЎРЏ": "Дата рождения",
    "Р В Р ВµР С–Р С‘РЎРѓРЎвЂљРЎР‚Р В°РЎвЂ Р С‘РЎРЏ": "Регистрация",
    "Р С™Р В°РЎвЂљР ВµР С–Р С•РЎР‚Р С‘Р С‘ Рё РЎС“РЎРѓР В»Р С•Р Р†Р С‘РЎРЏ Р Т‘Р С•Р С—РЎС“РЎРѓР С”Р В°": "Категории и условия допуска",
    "Р СџРЎР‚Р С‘Р СР ВµРЎвЂЎР В°Р Р…Р С‘РЎРЏ": "Примечания",
    "Р вЂќР В°РЎвЂљР В° Р С•Р В±РЎР‚Р В°РЎвЂ°Р ВµР Р…Р С‘РЎРЏ": "Дата обращения",
    "Р СњР С•Р СР ВµРЎР‚ Р С”Р В°РЎР‚РЎвЂљРЎвЂ№": "Номер карты",
    "РћСЂРіР°РЅРёР·Р°С†РёСЏ": "Организация",
    "Р СљР С™Р вЂ10": "МКБ10",
    "Р В Р ВµР В°Р В»РЎРЉР Р…Р В°РЎРЏ Р Т‘Р В°РЎвЂљР В°": "Реальная дата",
    "Р С—Р С•Р С‘РЎРѓР С”": "поиск",
    "Р вЂќР С•Р В±Р В°Р Р†Р С‘РЎвЂљРЎРЉ": "Добавить",
    "Р ВР В·Р СР ВµР Р…Р С‘РЎвЂљРЎРЉ": "Изменить",
    "Р С›РЎвЂљР С”РЎР‚РЎвЂ№РЎвЂљРЎРЉ РЎвЂћР С•РЎР‚Р СРЎС“": "Открыть форму",
    "Р В¤Р С•РЎР‚Р СРЎвЂ№ Р Р…Р ВµРЎвЂљ": "Формы нет",
    "Р ВР Р…РЎвЂћР С•РЎР‚Р СР В°РЎвЂ Р С‘РЎРЏ Р С• РєР»РёРµРЅС‚Рµ": "Информация о клиенте",
    "Р С™Р В°РЎР‚РЎвЂљР С•РЎвЂЎР С”Р С‘ Р Р†РЎР‚Р В°РЎвЂЎР ВµР в„–": "Карточки врачей",
    "Р Р€РЎРѓР В»РЎС“Р С–Р С‘ РЅРµ Р Р†РЎвЂ№Р В±РЎР‚Р В°Р Р…РЎвЂ№": "Услуги не выбраны",
    "Р вЂ™Р С•Р В·Р СР С•Р В¶Р Р…РЎвЂ№Р Вµ Р Т‘РЎС“Р В±Р В»Р С‘": "Возможные дубли",
    "Р СџР С• РЎвЂљР ВµР С”РЎС“РЎвЂ°Р ВµР СРЎС“ РЎвЂћР С‘Р В»РЎРЉРЎвЂљРЎР‚РЎС“ РєР»РёРµРЅС‚РѕРІ РЅРµ Р Р…Р В°Р в„–Р Т‘Р ВµР Р…Р С•": "Введите фамилию, телефон, дату рождения или документ. Без поиска список не грузится специально, чтобы база работала быстро.",
    "Р вЂ™РЎвЂ№Р В±Р ВµРЎР‚Р С‘ РєР»РёРµРЅС‚Р° РёР· РЎРѓР С—Р С‘РЎРѓР С”Р В° РЎРѓР Р†Р ВµРЎР‚РЎвЂ¦РЎС“": "Сначала найди клиента через строку поиска. После выбора тут появятся карточка клиента, кнопка изменения, услуги и карточки врачей.",
    "в„–": "№",
    "В·": "·",
  };

const _repairDemoTextRegex = new RegExp(
  Object.keys(_repairDemoTextMap).map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"),
  "g",
);

function repairDemoText(value) {
  const str = String(value ?? "");
  if (!str) return str;
  return str.replace(_repairDemoTextRegex, (m) => _repairDemoTextMap[m] ?? m);
}

function loadPersistedDemoState() {
  try {
    const raw = window.localStorage?.getItem(DEMO_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (error) {
    console.warn("Не удалось прочитать сохранение демки", error);
    return null;
  }
}

function applyPersistedDemoState() {
  const saved = loadPersistedDemoState();
  if (!saved || typeof saved !== "object") return;

  data.clientOverrides = saved.clientOverrides && typeof saved.clientOverrides === "object"
    ? saved.clientOverrides
    : {};
  data.doctorDirectory = saved.doctorDirectory && typeof saved.doctorDirectory === "object"
    ? saved.doctorDirectory
    : {};
  data.lastCreatedStaffUser = saved.lastCreatedStaffUser && typeof saved.lastCreatedStaffUser === "object"
    ? saved.lastCreatedStaffUser
    : null;

  Object.values(data.clientOverrides).forEach((clientPatch) => {
    const existing = data.clients.find((client) => String(client.id) === String(clientPatch.id));
    if (existing) Object.assign(existing, clientPatch);
  });

  if (Array.isArray(saved.createdClients)) {
    saved.createdClients
      .filter((client) => !data.clients.some((item) => String(item.id) === String(client.id)))
      .reverse()
      .forEach((client) => data.clients.unshift(client));
  }

  if (Array.isArray(saved.structuredServices) && Array.isArray(structuredServices)) {
    structuredServices.splice(0, structuredServices.length, ...saved.structuredServices);
    data.servicesDirty = true;
    refreshServiceCatalog();
  }

  if (Array.isArray(saved.mkb10History)) data.mkb10History = saved.mkb10History;
  if (Array.isArray(saved.visits)) {
    data.visits = saved.visits;
  }
  if (saved.activeVisitId) appState.activeVisitId = saved.activeVisitId;

  const savedAppState = saved.appState && typeof saved.appState === "object" ? saved.appState : {};
  const savedAuth = saved.auth && typeof saved.auth === "object" ? saved.auth : {};
  appState.page = "dashboard";
  if (typeof savedAuth.accessToken === "string") appState.auth.accessToken = savedAuth.accessToken;
  if (typeof savedAuth.userName === "string") appState.auth.userName = savedAuth.userName;
  if (typeof savedAuth.roleCode === "string") appState.auth.roleCode = savedAuth.roleCode;
  if (typeof savedAuth.roleName === "string") appState.auth.roleName = savedAuth.roleName;
  if (savedAppState.selectedClientId !== undefined && savedAppState.selectedClientId !== null) {
    appState.selectedClientId = savedAppState.selectedClientId;
  }
  if (typeof savedAppState.centerFilter === "string") appState.centerFilter = savedAppState.centerFilter;
  appState.clientSearch = "";
  if (typeof savedAppState.clientEncounterDate === "string") appState.clientEncounterDate = savedAppState.clientEncounterDate;
  if (typeof savedAppState.clientEncounterDateFrom === "string") {
    appState.clientEncounterDateFrom = savedAppState.clientEncounterDateFrom;
  }
  if (typeof savedAppState.clientEncounterDateTo === "string" && savedAppState.clientEncounterDateTo.trim()) {
    appState.clientEncounterDateTo = savedAppState.clientEncounterDateTo;
  }
  if (appState.clientEncounterDate && !appState.clientEncounterDateFrom && !appState.clientEncounterDateTo) {
    appState.clientEncounterDateFrom = appState.clientEncounterDate;
    appState.clientEncounterDateTo = appState.clientEncounterDate;
  }
  if (Number.isFinite(savedAppState.dashboardPage) && savedAppState.dashboardPage > 0) {
    appState.dashboardPage = savedAppState.dashboardPage;
  }
  if (typeof savedAppState.serviceGroupFilter === "string") appState.serviceGroupFilter = savedAppState.serviceGroupFilter;
  if (typeof savedAppState.visitServiceGroupFilter === "string") {
    appState.visitServiceGroupFilter = savedAppState.visitServiceGroupFilter;
  }
  if (typeof savedAppState.visitServiceSearch === "string") appState.visitServiceSearch = savedAppState.visitServiceSearch;
  if (typeof savedAppState.cashDateFrom === "string" && savedAppState.cashDateFrom) {
    appState.cashDateFrom = savedAppState.cashDateFrom;
  }
  if (typeof savedAppState.cashDateTo === "string" && savedAppState.cashDateTo) {
    appState.cashDateTo = savedAppState.cashDateTo;
  }
  if (typeof savedAppState.reportDateFrom === "string" && savedAppState.reportDateFrom) {
    appState.reportDateFrom = savedAppState.reportDateFrom;
  }
  if (typeof savedAppState.reportDateTo === "string" && savedAppState.reportDateTo) {
    appState.reportDateTo = savedAppState.reportDateTo;
  }
  if (typeof savedAppState.calendarFilter === "string" && savedAppState.calendarFilter) {
    appState.calendarFilter = savedAppState.calendarFilter;
  }
  if (typeof savedAppState.calendarServiceGroupFilter === "string") {
    appState.calendarServiceGroupFilter = savedAppState.calendarServiceGroupFilter;
  }
  if (typeof savedAppState.blanksTab === "string" && savedAppState.blanksTab) {
    appState.blanksTab = savedAppState.blanksTab;
  }
  if (typeof savedAppState.blanksFormOpen === "boolean") {
    appState.blanksFormOpen = savedAppState.blanksFormOpen;
  }
  if (typeof savedAppState.blanksFilterStatus === "string" && savedAppState.blanksFilterStatus) {
    appState.blanksFilterStatus = savedAppState.blanksFilterStatus;
  }
  if (typeof savedAppState.blanksFilterBatchId === "string" && savedAppState.blanksFilterBatchId) {
    appState.blanksFilterBatchId = savedAppState.blanksFilterBatchId;
  }
  if (typeof savedAppState.blanksSearch === "string") {
    appState.blanksSearch = savedAppState.blanksSearch;
  }
  if (savedAppState.restoreInputId !== undefined) appState.restoreInputId = savedAppState.restoreInputId;
  if (savedAppState.activeVisitId !== undefined) appState.activeVisitId = savedAppState.activeVisitId;
  appState.doctorExamModal = {
    isOpen: false,
    clientId: null,
    visitId: null,
    doctorRoleId: null,
  };
  ensureDemoAuthConsistency();
}

function persistDemoState() {
  try {
    const selectedClient = getSelectedClient();
    const activeVisit = selectedClient ? getCurrentVisitForClient(selectedClient.id) : null;
    window.localStorage?.setItem(
      SELECTION_STORAGE_KEY,
      JSON.stringify({
        selectedClientId: selectedClient?.backendId || selectedClient?.id || null,
        activeEncounterId: activeVisit?.backendId || null,
        clientSearch: "",
        savedAt: new Date().toISOString(),
      }),
    );
  } catch (error) {
    console.warn("Failed to persist workplace selection", error);
  }
  try {
    const payload = {
      createdClients: data.clients.filter((client) => client.__demoCreated),
      clientOverrides: data.clientOverrides || {},
      doctorDirectory: data.doctorDirectory || {},
      visits: getPersistableVisits(),
      mkb10History: data.mkb10History || [],
      activeVisitId: appState.activeVisitId,
      lastCreatedStaffUser: data.lastCreatedStaffUser || null,
      auth: {
        accessToken: appState.auth.accessToken || "",
        userName: appState.auth.userName || "",
        roleCode: appState.auth.roleCode || "",
        roleName: appState.auth.roleName || "",
      },
      appState: {
        page: appState.page,
        selectedClientId: appState.selectedClientId,
        centerFilter: appState.centerFilter,
        clientSearch: "",
        clientEncounterDate: appState.clientEncounterDate,
        clientEncounterDateFrom: appState.clientEncounterDateFrom,
        clientEncounterDateTo: appState.clientEncounterDateTo,
        dashboardPage: appState.dashboardPage,
        serviceGroupFilter: appState.serviceGroupFilter,
        visitServiceGroupFilter: appState.visitServiceGroupFilter,
        visitServiceSearch: appState.visitServiceSearch,
        cashDateFrom: appState.cashDateFrom,
        cashDateTo: appState.cashDateTo,
        reportDateFrom: appState.reportDateFrom,
        reportDateTo: appState.reportDateTo,
        calendarFilter: appState.calendarFilter,
        calendarServiceGroupFilter: appState.calendarServiceGroupFilter,
        blanksTab: appState.blanksTab,
        blanksFormOpen: appState.blanksFormOpen,
        blanksFilterStatus: appState.blanksFilterStatus,
        blanksFilterBatchId: appState.blanksFilterBatchId,
        blanksSearch: appState.blanksSearch,
        restoreInputId: appState.restoreInputId,
        activeVisitId: appState.activeVisitId,
        doctorExamModal: appState.doctorExamModal,
      },
      structuredServices: data.servicesDirty ? structuredServices : undefined,
      savedAt: new Date().toISOString(),
    };

    window.localStorage?.setItem(DEMO_STORAGE_KEY, JSON.stringify(payload));
  } catch (error) {
    console.warn("Не удалось сохранить демо-данные", error);
    showToast("Не удалось сохранить демо-данные: лимит браузера");
  }
}

function getPersistableVisits() {
  ensureVisitsStore();
  return data.visits.map((visit) => {
    const {
      __backendSyncPromise,
      __backendSyncing,
      ...persistableVisit
    } = visit;
    return persistableVisit;
  });
}

function markClientChanged(client, isCreated = false) {
  if (!client) return;
  if (isCreated) client.__demoCreated = true;
  data.clientOverrides = data.clientOverrides || {};
  data.clientOverrides[client.id] = { ...client };
  persistDemoState();
}

function refreshServiceCatalog() {
  const source = data.serverServicesLoaded ? data.serverServices : [];
  data.serviceCatalog = source
    .filter((service) => service.isActive !== false)
    .slice()
    .map((service) => service.name);
}

function markServicesChanged() {
  data.servicesDirty = true;
  refreshServiceCatalog();
  persistDemoState();
}

function loadColumnWidths() {
  try {
    const raw = window.localStorage?.getItem(COLUMN_WIDTHS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    window.__columnWidths = parsed && typeof parsed === "object" ? parsed : {};
  } catch (error) {
    console.warn("Не удалось прочитать ширину колонок", error);
    window.__columnWidths = {};
  }
}

function persistColumnWidths() {
  try {
    window.localStorage?.setItem(COLUMN_WIDTHS_STORAGE_KEY, JSON.stringify(window.__columnWidths || {}));
  } catch (error) {
    console.warn("Не удалось сохранить ширину колонок", error);
  }
}

function ensureVisitsStore() {
  if (!data.visits) data.visits = [];
  if (!data.documents) data.documents = [];
  if (!data.doctorExams) data.doctorExams = [];
}

function generateId(prefix = "id") {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
}
function rememberMkb10Value(value) {
  const normalized = String(value || "").trim().toUpperCase();
  if (!normalized) return;

  if (!Array.isArray(data.mkb10History)) {
    data.mkb10History = [];
  }

  if (!data.mkb10History.includes(normalized)) {
    data.mkb10History.push(normalized);
    data.mkb10History.sort((a, b) => a.localeCompare(b, "ru"));
  }
}

function getDoctorTemplates() {
  return Array.isArray(window.doctorTemplates) ? window.doctorTemplates : [];
}

function getDoctorTemplate(doctorRoleId) {
  return getDoctorTemplates().find((item) => item.id === doctorRoleId) || null;
}

let _clientPoolCache = null;

function getClientPool() {
  if (_clientPoolCache) return _clientPoolCache;
  const sourceClients = [...(data.clients || []), ...(data.backendClients || [])];
  const uniqueClients = [];
  const seen = new Set();

  sourceClients.forEach((client) => {
    const key = String(client?.backendId || client?.id || "");
    if (!key || seen.has(key)) return;
    seen.add(key);
    uniqueClients.push(client);
  });

  _clientPoolCache = uniqueClients;
  return uniqueClients;
}

function invalidateClientPool() {
  _clientPoolCache = null;
}

function getSelectedClient() {
  return getClientPool().find((client) => String(client.id) === String(appState.selectedClientId)) || null;
}

function getServiceByName(name) {
  return data.serverServices.find((service) => service.name === name) || null;
}

function getServiceById(serviceId) {
  return data.serverServices.find((service) => String(service.backendId || service.id) === String(serviceId)) || null;
}

function getServiceToken(service) {
  return String(service?.backendId || service?.id || "");
}

function getSelectedVisitServiceIds(visit) {
  if (!visit) return [];
  if (Array.isArray(visit.serviceIds) && visit.serviceIds.length) {
    return Array.from(
      new Set(
        visit.serviceIds
          .map((id) => String(id))
          .filter(Boolean),
      ),
    );
  }
  return Array.from(
    new Set(
      (visit.serviceNames || [])
        .map((name) => getServerServiceByName(name))
        .filter(Boolean)
        .map((service) => getServiceToken(service))
        .filter(Boolean),
    ),
  );
}

function getVisitServiceDetails(visit) {
  if (!visit || !visit.serviceDetails || typeof visit.serviceDetails !== "object") return {};
  return visit.serviceDetails;
}

function getSortedServiceGroups() {
  return serviceGroups
    .filter((group) => group.isActive !== false)
    .slice()
    .sort((a, b) => (a.sortOrder || 0) - (b.sortOrder || 0));
}

function getSortedServices() {
  const source = data.serverServicesLoaded ? data.serverServices : [];
  return source
    .filter((service) => service.isActive !== false)
    .slice();
}

function calculateVisitAmount(serviceNames = []) {
  return serviceNames.reduce((total, name) => total + Number(getServiceByName(name)?.price || 0), 0);
}

function calculateVisitAmountByIds(serviceIds = [], serviceDetails = {}) {
  return serviceIds.reduce((total, serviceId) => {
    const service = getServiceById(serviceId);
    const detail = serviceDetails[String(serviceId)] || {};
    const price = Number(detail.unitPrice ?? service?.price ?? 0);
    return total + price;
  }, 0);
}

function roundMoney(value) {
  return Math.round((Number(value) || 0) * 100) / 100;
}

function getVisitPaymentTotals(services = [], amount = 0, fallbackPaymentType = "") {
  const totals = services.reduce((result, service) => {
    const label = formatPaymentTypeLabel(service.paymentType);
    const value = Number(service.paidPrice || 0);
    if (label === "нал") {
      result.cash += value;
    } else {
      result.nonCash += value;
    }
    return result;
  }, { cash: 0, nonCash: 0 });

  const normalizedAmount = roundMoney(amount);
  const sourceTotal = roundMoney(totals.cash + totals.nonCash);
  if (Math.abs(sourceTotal - normalizedAmount) < 0.01) {
    return {
      cash: roundMoney(totals.cash),
      nonCash: roundMoney(totals.nonCash),
    };
  }

  if (sourceTotal > 0) {
    const cash = roundMoney((totals.cash / sourceTotal) * normalizedAmount);
    return {
      cash,
      nonCash: roundMoney(normalizedAmount - cash),
    };
  }

  return formatPaymentTypeLabel(fallbackPaymentType) === "нал"
    ? { cash: normalizedAmount, nonCash: 0 }
    : { cash: 0, nonCash: normalizedAmount };
}

function isDriverService(service) {
  return DRIVER_SERVICE_LEGACY_IDS.has(Number(service?.legacySourceId ?? service?.id));
}

function isTractorService(service) {
  return TRACTOR_SERVICE_LEGACY_IDS.has(Number(service?.legacySourceId ?? service?.id));
}

function isGimsService(service) {
  return GIMS_SERVICE_LEGACY_IDS.has(Number(service?.legacySourceId ?? service?.id));
}

function isLmkService(service) {
  return LMK_SERVICE_LEGACY_IDS.has(Number(service?.legacySourceId ?? service?.id));
}

function isProfService(service) {
  return PROF_SERVICE_LEGACY_IDS.has(Number(service?.legacySourceId));
}

function getServiceGroup(service) {
  return serviceGroups.find((group) => String(group.id) === String(service?.groupId || service?.category_id || ""));
}

function isCertificateService(service) {
  const legacyId = Number(service?.legacySourceId ?? service?.legacy_source_id ?? service?.id);
  const group = getServiceGroup(service);
  const groupCode = String(group?.code || "").trim().toLowerCase();
  const groupName = String(group?.name || "").trim().toLowerCase();
  const normalizedName = String(service?.name || "").trim().toLowerCase();
  return (
    CERTIFICATE_SERVICE_LEGACY_IDS.has(legacyId) ||
    groupCode === "legacy-group-7" ||
    groupName === "справки" ||
    normalizedName.includes("справк")
  );
}

function isSportService(service) {
  const legacyId = Number(service?.legacySourceId ?? service?.legacy_source_id);
  const normalizedName = String(service?.name || "").trim().toLowerCase();
  return SPORT_SERVICE_LEGACY_IDS.has(legacyId) || SPORT_SERVICE_NAMES.has(normalizedName);
}

function isStandaloneEkgService(service) {
  const legacyId = Number(service?.legacySourceId ?? service?.legacy_source_id);
  const normalizedName = String(service?.name || "").trim().toLowerCase();
  return (
    EKG_SERVICE_LEGACY_IDS.has(legacyId) ||
    (normalizedName.includes("экг") && !normalizedName.includes("спорт"))
  );
}

function getServicesForVisit(visit) {
  return getSelectedVisitServiceIds(visit)
    .map((serviceId) => getServiceById(serviceId))
    .filter(Boolean);
}

function getChairmanFormTypeForVisit(visit) {
  const services = getServicesForVisit(visit);
  const serviceText = [
    ...(Array.isArray(visit?.serviceNames) ? visit.serviceNames : []),
    ...services.map((service) => service.name),
  ]
    .join(" ")
    .toLowerCase();

  if (services.some(isDriverService) || serviceText.includes("водител")) return "driver";
  if (services.some(isGimsService) || serviceText.includes("гимс")) return "gims";
  if (services.some(isLmkService) || serviceText.includes("лмк")) return "lmk";
  if (services.some(isProfService) || serviceText.includes("профосмотр") || serviceText.includes("29н")) return "prof";
  if (services.some(isTractorService) || serviceText.includes("трактор") || serviceText.includes("071")) return "tractor";
  if (serviceText.includes("драг") || serviceText.includes("drug") || serviceText.includes("alcohol")) return "drug";
  if (serviceText.includes("морск") || serviceText.includes("marine") || serviceText.includes("seafar")) return "marine";
  if (serviceText.includes("гто") || serviceText.includes("1144")) return "gto";
  if (serviceText.includes("басс")) return "pool";
  if (services.some(isSportService) || serviceText.includes("спорт")) return "sport";
  if (services.some(isStandaloneEkgService) || serviceText.includes("экг")) return "ekg";
  if (serviceText.includes("070") || serviceText.includes("путевк")) return "certificate070";
  if (serviceText.includes("072") || serviceText.includes("санатор")) return "certificate072";
  if (serviceText.includes("082") || serviceText.includes("границ")) return "certificate082";
  if (serviceText.includes("086")) return "certificate086";
  if (serviceText.includes("095")) return "certificate095";
  if (serviceText.includes("001") || serviceText.includes("гсу") || serviceText.includes("госслуж")) return "gsu";
  if (serviceText.includes("989") || serviceText.includes("гостайн") || serviceText.includes("гос.тайн")) return "gostaina";
  if (serviceText.includes("чод") || serviceText.includes("охран")) return "guard";
  if (services.some(isCertificateService)) return "certificate";
  return "default";
}

function getChairmanFormConfigForVisit(visit) {
  const type = getChairmanFormTypeForVisit(visit);
  return CHAIRMAN_FORM_CONFIGS[type] || CHAIRMAN_FORM_CONFIGS.default;
}

function getChairmanFormInfo(examOrVisit = null, client = null) {
  const visit = examOrVisit?.visitId
    ? data.visits.find((item) => String(item.id) === String(examOrVisit.visitId))
    : examOrVisit;
  const resolvedClient = client || (visit ? getClientPool().find((item) => String(item.id) === String(visit.clientId)) : getSelectedClient());
  const config = getChairmanFormConfigForVisit(visit);
  const template = data.documentTemplatesLoaded ? pickDocumentTemplate(config.templateType, visit, resolvedClient) : null;
  return {
    ...config,
    template,
    templateId: template?.id || null,
    templateName: template?.name || template?.file_name || "",
  };
}

async function openChairmanTemplateFile(examId = null) {
  const exam = examId ? data.doctorExams.find((item) => String(item.id) === String(examId)) : null;
  const client = exam ? getClientPool().find((item) => String(item.id) === String(exam.clientId)) : getSelectedClient();
  if (!data.documentTemplatesLoaded) {
    await loadDocumentTemplatesFromBackend();
  }
  const info = getChairmanFormInfo(exam, client);
  if (!info.templateId) {
    showToast(`Не найден файловый шаблон для формы "${info.label}"`);
    return false;
  }
  try {
    return await openAuthorizedFileUrl(buildTemplateFileUrl(info.templateId));
  } catch (error) {
    showToast(humanizeApiError(error, "Не удалось открыть шаблон"));
    return false;
  }
}

function normalizeDriverCategories(categories) {
  const source = Array.isArray(categories)
    ? categories
    : String(categories || "")
        .split(/[\s,;/]+/)
        .map((item) => item.trim())
        .filter(Boolean);
  if (!source.length) return Array.isArray(categories) ? [] : ["A", "B"];
  const expanded = new Set(source);
  if (expanded.has("E")) {
    expanded.add("BE");
    expanded.add("CE");
    expanded.add("DE");
  }
  if (expanded.has("1A")) expanded.add("A1");
  if (expanded.has("1B")) expanded.add("B1");
  if (expanded.has("1C")) expanded.add("C1");
  if (expanded.has("1D")) expanded.add("D1");
  if (expanded.has("1CE")) expanded.add("C1E");
  if (expanded.has("1DE")) expanded.add("D1E");
  return DRIVER_CATEGORY_OPTIONS.filter((item) => expanded.has(item));
}

function getDriverCategoryPrice(categories = []) {
  const normalized = normalizeDriverCategories(categories);
  if (!normalized.length) return 0;
  const isBase = normalized.length > 0 && normalized.every((item) => DRIVER_BASE_CATEGORIES.has(item));
  return isBase ? 3500 : 4000;
}

function getDriverCategoryRuleKey(categories = [], { includeTransport = true } = {}) {
  const normalized = normalizeDriverCategories(categories);
  const parts = new Set();

  if (normalized.includes("A") || normalized.includes("A1")) parts.add("A");
  if (normalized.includes("B") || normalized.includes("B1") || normalized.includes("BE")) parts.add("B");
  if (normalized.includes("C") || normalized.includes("C1") || normalized.includes("CE") || normalized.includes("C1E")) parts.add("C");
  if (normalized.includes("D") || normalized.includes("D1") || normalized.includes("DE") || normalized.includes("D1E")) parts.add("D");
  if (normalized.some((item) => item === "BE" || item === "CE" || item === "DE" || item === "C1E" || item === "D1E")) parts.add("E");

  const key = ["A", "B", "C", "D", "E"].filter((item) => parts.has(item)).join("");
  const transport = [];
  if (normalized.includes("Tb")) transport.push("TB");
  if (normalized.includes("Tm")) transport.push("TM");

  return includeTransport && transport.length ? `${key},${transport.join(",")}` : key;
}

function getDriverRoleCodes(categories = []) {
  const normalized = normalizeDriverCategories(categories);
  if (!normalized.length) return [];
  const exactKey = getDriverCategoryRuleKey(normalized);
  const baseKey = getDriverCategoryRuleKey(normalized, { includeTransport: false });
  const matched = DRIVER_CATEGORY_DOCTOR_RULES.get(exactKey) || DRIVER_CATEGORY_DOCTOR_RULES.get(baseKey);
  if (matched) return matched;

  const isBase = normalized.length > 0 && normalized.every((item) => DRIVER_BASE_CATEGORIES.has(item));
  return isBase ? DRIVER_CATEGORY_BASE_ROLES : DRIVER_CATEGORY_ADVANCED_ROLES;
}

const DRIVER_INDICATION_FIELD_TO_LABEL = {
  indicationManual: "С ручным упр-ем",
  indicationAutomatic: "С автоматич. трансмиссией",
  indicationAcoustic: "Акустич. парковочная система",
  indicationGlasses: "ТС мед. изд. для коррекции зрения",
  indicationHearingAid: "ТС мед. изд. для компенсации потери слуха",
  indicationNoHiring: "Без найма",
  indicationOneYear: "На год",
};

const DRIVER_INDICATION_LABEL_TO_FIELD = Object.fromEntries(
  Object.entries(DRIVER_INDICATION_FIELD_TO_LABEL).map(([key, value]) => [value, key]),
);

const DRIVER_LIMITATION_FIELD_TO_LABEL = {
  restrictionAM: "AM",
  restrictionBBE: "B BE",
  restrictionCCE: "C CE",
  restrictionNoHands: "Без рук",
  restrictionNoLegs: "Без ног",
};

const DRIVER_LIMITATION_LABEL_TO_FIELD = Object.fromEntries(
  Object.entries(DRIVER_LIMITATION_FIELD_TO_LABEL).map(([key, value]) => [value, key]),
);

function collectChairmanDriverCategories(fields = {}) {
  const categories = [];
  if (fields.categoryA) categories.push("A");
  if (fields.categoryB) categories.push("B");
  if (fields.categoryC) categories.push("C");
  if (fields.categoryD) categories.push("D");
  const legacyE = Boolean(fields.categoryE) && !fields.categoryBE && !fields.categoryCE && !fields.categoryDE;
  if (fields.categoryBE || legacyE) categories.push("BE");
  if (fields.categoryCE || legacyE) categories.push("CE");
  if (fields.categoryDE || legacyE) categories.push("DE");
  if (fields.categoryTram) categories.push("Tm");
  if (fields.categoryTrolleybus) categories.push("Tb");
  if (fields.categoryM) categories.push("M");
  if (fields.categoryA1) categories.push("A1");
  if (fields.categoryB1) categories.push("B1");
  if (fields.categoryC1) categories.push("C1");
  if (fields.categoryD1) categories.push("D1");
  if (fields.categoryC1E) categories.push("C1E");
  if (fields.categoryD1E) categories.push("D1E");
  if (fields.categoryTractor) categories.push("tractor");
  if (fields.categoryBoat) categories.push("boat");
  if (fields.categorySailing) categories.push("sailing");
  return categories;
}

function collectChairmanDriverIndications(fields = {}) {
  return Object.entries(DRIVER_INDICATION_FIELD_TO_LABEL)
    .filter(([fieldKey]) => Boolean(fields[fieldKey]))
    .map(([, label]) => label);
}

function collectChairmanDriverLimitations(fields = {}) {
  return Object.entries(DRIVER_LIMITATION_FIELD_TO_LABEL)
    .filter(([fieldKey]) => Boolean(fields[fieldKey]))
    .map(([, label]) => label);
}

function applyDriverSelectionsToChairmanFields(fields = {}, detail = {}, visit = null) {
  const sourceCategories = Array.isArray(detail.categories) ? detail.categories : [];
  const categories = normalizeDriverCategories(sourceCategories);
  const indications = Array.isArray(detail.indications) ? detail.indications : [];
  const limitations = Array.isArray(detail.limitations) ? detail.limitations : [];
  const hasCategoryOverrides = sourceCategories.length > 0;
  const hasIndicationOverrides = indications.length > 0;
  const hasLimitationOverrides = limitations.length > 0;

  return {
    ...fields,
    serviceNames: Array.isArray(visit?.serviceNames) ? visit.serviceNames.join(", ") : (fields.serviceNames || ""),
    driverCategories: hasCategoryOverrides ? categories.join(", ") : (fields.driverCategories || ""),
    categoryA: hasCategoryOverrides ? categories.includes("A") : Boolean(fields.categoryA),
    categoryB: hasCategoryOverrides ? categories.includes("B") : Boolean(fields.categoryB),
    categoryC: hasCategoryOverrides ? categories.includes("C") : Boolean(fields.categoryC),
    categoryD: hasCategoryOverrides ? categories.includes("D") : Boolean(fields.categoryD),
    categoryBE: hasCategoryOverrides ? categories.includes("BE") : Boolean(fields.categoryBE || fields.categoryE),
    categoryCE: hasCategoryOverrides ? categories.includes("CE") : Boolean(fields.categoryCE || fields.categoryE),
    categoryDE: hasCategoryOverrides ? categories.includes("DE") : Boolean(fields.categoryDE || fields.categoryE),
    categoryTram: hasCategoryOverrides ? categories.includes("Tm") : Boolean(fields.categoryTram),
    categoryTrolleybus: hasCategoryOverrides ? categories.includes("Tb") : Boolean(fields.categoryTrolleybus),
    categoryM: hasCategoryOverrides ? categories.includes("M") : Boolean(fields.categoryM),
    categoryA1: hasCategoryOverrides ? categories.includes("A1") : Boolean(fields.categoryA1),
    categoryB1: hasCategoryOverrides ? categories.includes("B1") : Boolean(fields.categoryB1),
    categoryC1: hasCategoryOverrides ? categories.includes("C1") : Boolean(fields.categoryC1),
    categoryD1: hasCategoryOverrides ? categories.includes("D1") : Boolean(fields.categoryD1),
    categoryC1E: hasCategoryOverrides ? categories.includes("C1E") : Boolean(fields.categoryC1E),
    categoryD1E: hasCategoryOverrides ? categories.includes("D1E") : Boolean(fields.categoryD1E),
    categoryTractor: hasCategoryOverrides ? sourceCategories.includes("tractor") : Boolean(fields.categoryTractor),
    categoryBoat: hasCategoryOverrides ? (sourceCategories.includes("boat") || Boolean(detail.boatFit)) : Boolean(fields.categoryBoat),
    categorySailing: hasCategoryOverrides ? sourceCategories.includes("sailing") : Boolean(fields.categorySailing),
    hasGlasses: hasIndicationOverrides ? indications.includes(DRIVER_INDICATION_FIELD_TO_LABEL.indicationGlasses) : Boolean(fields.hasGlasses),
    hasHearingAid: hasIndicationOverrides ? indications.includes(DRIVER_INDICATION_FIELD_TO_LABEL.indicationHearingAid) : Boolean(fields.hasHearingAid),
    indicationManual: hasIndicationOverrides ? indications.includes(DRIVER_INDICATION_FIELD_TO_LABEL.indicationManual) : Boolean(fields.indicationManual),
    indicationAutomatic: hasIndicationOverrides ? indications.includes(DRIVER_INDICATION_FIELD_TO_LABEL.indicationAutomatic) : Boolean(fields.indicationAutomatic),
    indicationAcoustic: hasIndicationOverrides ? indications.includes(DRIVER_INDICATION_FIELD_TO_LABEL.indicationAcoustic) : Boolean(fields.indicationAcoustic),
    indicationGlasses: hasIndicationOverrides ? indications.includes(DRIVER_INDICATION_FIELD_TO_LABEL.indicationGlasses) : Boolean(fields.indicationGlasses),
    indicationHearingAid: hasIndicationOverrides ? indications.includes(DRIVER_INDICATION_FIELD_TO_LABEL.indicationHearingAid) : Boolean(fields.indicationHearingAid),
    indicationNoHiring: hasIndicationOverrides ? indications.includes(DRIVER_INDICATION_FIELD_TO_LABEL.indicationNoHiring) : Boolean(fields.indicationNoHiring),
    indicationOneYear: hasIndicationOverrides ? indications.includes(DRIVER_INDICATION_FIELD_TO_LABEL.indicationOneYear) : Boolean(fields.indicationOneYear),
    restrictionAM: hasLimitationOverrides ? limitations.includes(DRIVER_LIMITATION_FIELD_TO_LABEL.restrictionAM) : Boolean(fields.restrictionAM),
    restrictionBBE: hasLimitationOverrides ? limitations.includes(DRIVER_LIMITATION_FIELD_TO_LABEL.restrictionBBE) : Boolean(fields.restrictionBBE),
    restrictionCCE: hasLimitationOverrides ? limitations.includes(DRIVER_LIMITATION_FIELD_TO_LABEL.restrictionCCE) : Boolean(fields.restrictionCCE),
    restrictionNoHands: hasLimitationOverrides ? limitations.includes(DRIVER_LIMITATION_FIELD_TO_LABEL.restrictionNoHands) : Boolean(fields.restrictionNoHands),
    restrictionNoLegs: hasLimitationOverrides ? limitations.includes(DRIVER_LIMITATION_FIELD_TO_LABEL.restrictionNoLegs) : Boolean(fields.restrictionNoLegs),
    examDate: fields.examDate || visit?.visitDate || "",
  };
}

function getDriverDetailFromVisit(visit) {
  if (!visit) return {};
  const serviceDetails = getVisitServiceDetails(visit);
  const details = Object.values(serviceDetails);
  const detailWithCategories = details.find((detail) =>
    Array.isArray(detail?.categories)
      ? detail.categories.length
      : String(detail?.categories || "").trim(),
  );
  if (detailWithCategories) return detailWithCategories;
  const driverServiceId = getSelectedVisitServiceIds(visit).find((serviceId) => isDriverService(getServiceById(serviceId)));
  return driverServiceId ? (serviceDetails[String(driverServiceId)] ||= {}) : {};
}

function getDoctorRoleCodeById(roleId) {
  return doctorRoles.find((role) => String(role.id) === String(roleId))?.code || null;
}

function getDoctorRoleCodeSetFromService(service, detail = {}) {
  if (!service) return new Set();
  if (isDriverService(service)) {
    return new Set(getDriverRoleCodes(detail.categories || DRIVER_DEFAULT_CATEGORIES));
  }
  if (isSportService(service)) {
    return new Set(["chairman"]);
  }
  if (isStandaloneEkgService(service)) {
    return new Set(["chairman"]);
  }

  const roleCodes = (service.doctorRoleIds || [])
    .map((roleId) => getDoctorRoleCodeById(roleId))
    .filter(Boolean);

  if (isCertificateService(service)) {
    roleCodes.push("chairman");
  }

  if (
    roleCodes.length &&
    (isTractorService(service) || isGimsService(service) || isLmkService(service) || isProfService(service))
  ) {
    roleCodes.push("chairman");
  }

  return new Set(roleCodes);
}

function getRequiredDoctorRoleCountsForVisit(visit) {
  const serviceDetails = getVisitServiceDetails(visit);
  const counts = new Map();
  getSelectedVisitServiceIds(visit).forEach((serviceId) => {
    const service = getServiceById(serviceId);
    const detail = serviceDetails[String(serviceId)] || {};
    getDoctorRoleCodeSetFromService(service, detail).forEach((code) => {
      const current = counts.get(code) || 0;
      counts.set(code, code === "chairman" && isCertificateService(service) ? current + 1 : Math.max(current, 1));
    });
  });
  return counts;
}

function getRequiredDoctorRoleCountsForClient(client, currentVisit = null) {
  const counts = new Map(currentVisit ? getRequiredDoctorRoleCountsForVisit(currentVisit) : []);
  if (!client) return counts;

  getVisitsForClient(client.id).forEach((visit) => {
    if (currentVisit && String(visit.id) === String(currentVisit.id)) return;
    if (visit.status === "closed") return;
    const visitCounts = getRequiredDoctorRoleCountsForVisit(visit);
    const chairmanCount = Number(visitCounts.get("chairman") || 0);
    if (chairmanCount > 0) {
      counts.set("chairman", Number(counts.get("chairman") || 0) + chairmanCount);
    }
  });

  return counts;
}

function getRequiredDoctorRoleCodesForVisit(visit) {
  const serviceDetails = getVisitServiceDetails(visit);
  const result = new Set();
  getSelectedVisitServiceIds(visit).forEach((serviceId) => {
    const service = getServiceById(serviceId);
    const detail = serviceDetails[String(serviceId)] || {};
    getDoctorRoleCodeSetFromService(service, detail).forEach((code) => result.add(code));
  });
  return Array.from(result);
}

function getServerServiceByName(name) {
  return data.serverServices.find((service) => service.name === name) || null;
}

const RU_DATE_FORMAT_OPTIONS = {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
};

const RU_DATE_TIME_FORMAT_OPTIONS = {
  ...RU_DATE_FORMAT_OPTIONS,
  hour: "2-digit",
  minute: "2-digit",
};

function formatDateTime(value = new Date()) {
  const text = typeof value === "string" ? value.trim() : "";
  const isoDateTimeMatch = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s]+(\d{1,2}):(\d{2}))?/);
  if (isoDateTimeMatch) {
    const dateText = `${isoDateTimeMatch[3]}.${isoDateTimeMatch[2]}.${isoDateTimeMatch[1]}`;
    return isoDateTimeMatch[4] ? `${dateText}, ${isoDateTimeMatch[4].padStart(2, "0")}:${isoDateTimeMatch[5]}` : dateText;
  }

  const ruDateTimeMatch = text.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})(?:[,\s]+(\d{1,2}):(\d{2}))?/);
  if (ruDateTimeMatch) {
    const year = ruDateTimeMatch[3].length === 2 ? `20${ruDateTimeMatch[3]}` : ruDateTimeMatch[3];
    const dateText = `${ruDateTimeMatch[1].padStart(2, "0")}.${ruDateTimeMatch[2].padStart(2, "0")}.${year}`;
    return ruDateTimeMatch[4] ? `${dateText}, ${ruDateTimeMatch[4].padStart(2, "0")}:${ruDateTimeMatch[5]}` : dateText;
  }

  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("ru-RU", RU_DATE_TIME_FORMAT_OPTIONS);
}

function formatApiDate(value) {
  if (!value) return "";
  const text = String(value).trim();
  const isoDateMatch = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s].*)?$/);
  if (isoDateMatch) return `${isoDateMatch[3]}.${isoDateMatch[2]}.${isoDateMatch[1]}`;

  const ruDateMatch = text.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})/);
  if (ruDateMatch) {
    const year = ruDateMatch[3].length === 2 ? `20${ruDateMatch[3]}` : ruDateMatch[3];
    return `${ruDateMatch[1].padStart(2, "0")}.${ruDateMatch[2].padStart(2, "0")}.${year}`;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString("ru-RU", RU_DATE_FORMAT_OPTIONS);
}

function joinClientName(client) {
  return [client?.last_name, client?.first_name, client?.middle_name].filter(Boolean).join(" ").trim();
}

function joinDocument(client) {
  const number = [client?.document_series, client?.document_number].filter(Boolean).join(" ").trim();
  return [client?.document_type, number].filter(Boolean).join(" ").trim();
}

function mapApiClient(client) {
  const services = Array.isArray(client.services) ? client.services : [];
  return {
    id: client.id,
    backendId: client.id,
    patientNumber: client.patient_number,
    fullName: joinClientName(client) || `Пациент ${client.patient_number || client.id}`,
    birthDate: formatApiDate(client.birth_date),
    sex: client.sex || "",
    gender: client.sex || "",
    phone: client.phone || "",
    center: client.center || "Медцентр 1",
    document: joinDocument(client),
    documentType: client.document_type || "",
    documentSeries: client.document_series || "",
    documentNumber: client.document_number || "",
    documentIssuedBy: client.document_issued_by || client.legacy_payload_json?.WhoGive || client.legacy_payload_json?.["qdfMain.WhoGive"] || "",
    documentIssuedDate: formatApiDate(client.document_issued_date),
    snils: client.snils || "",
    email: client.email || "",
    note: client.notes || "",
    lastVisit: formatDateTime(client.real_date_text || client.encounter_date_text || ""),
    services,
    registration: client.registration_text || client.address_text || "",
    admissionCategory: client.admission_category || "",
    category: resolveAdmissionCategoryValue(client.admission_category, services),
    referenceNumber: client.reference_number || "",
    gynecologist: client.doctor_gynecologist || "",
    stomatologist: client.doctor_stomatologist || "",
    dermatologist: client.doctor_dermatologist || "",
    neurologist: client.doctor_neurologist || "",
    surgeon: client.doctor_surgeon || "",
    otolaryngologist: client.doctor_otolaryngologist || "",
    ophthalmologist: client.doctor_ophthalmologist || "",
    therapist: client.doctor_therapist || "",
    psychiatrist: client.doctor_psychiatrist || "",
    infectionist: client.doctor_infectionist || "",
    phthisiatrician: client.doctor_phthisiatrician || "",
    uzist: client.doctor_uzist || "",
    encounterDate: formatDateTime(client.encounter_date_text || client.real_date_text || ""),
    cardNumber: client.card_number || "",
    profession: client.profession || "",
    workPlace: client.work_place || "",
    organization: client.organization || "",
    agent: client.agent || client.legacy_payload_json?.agent || "",
    mkb10: client.mkb10 || "",
    realDate: client.real_date_text || "",
    rawApiClient: client,
  };
}

const doctorRoleToClientFieldMap = {
  gynecologist: "gynecologist",
  dentist: "stomatologist",
  dermatologist: "dermatologist",
  neurologist: "neurologist",
  surgeon: "surgeon",
  otolaryngologist: "otolaryngologist",
  ophthalmologist: "ophthalmologist",
  therapist: "therapist",
  psychiatrist: "psychiatrist",
  infectionist: "infectionist",
  phthisiatrist: "phthisiatrician",
  uzist: "uzist",
  chairman: "chairman",
};

function getClientDoctorFieldKey(doctorRoleId) {
  return doctorRoleToClientFieldMap[String(doctorRoleId || "").trim()] || "";
}

function syncCompletedDoctorMarksToClient(client, exams = []) {
  if (!client) return;

  const existing = Array.isArray(client.doctorExamHistory) ? client.doctorExamHistory : [];
  const nextItems = (Array.isArray(exams) ? exams : [])
    .filter((exam) => exam?.isCompleted)
    .map((exam) => ({
      doctorRoleId: String(exam.doctorRoleId || "").trim(),
      visitId: exam.visitId || null,
      backendEncounterId: exam.backendEncounterId || null,
    }))
    .filter((exam) => exam.doctorRoleId);

  const byKey = new Map();
  [...existing, ...nextItems].forEach((exam) => {
    const key = [
      exam.doctorRoleId,
      exam.backendEncounterId ? `backend-${exam.backendEncounterId}` : "",
      exam.visitId ? `visit-${exam.visitId}` : "",
    ].join(":");
    byKey.set(key, exam);
  });
  client.doctorExamHistory = Array.from(byKey.values());
}

function hasCompletedDoctorExamHistory(clientId, doctorRoleId, currentVisitId = null) {
  if (!clientId || !doctorRoleId) return false;
  const roleCode = String(doctorRoleId || "").trim();
  const client = getClientPool().find((item) => String(item.id) === String(clientId));
  const currentVisit = currentVisitId
    ? data.visits.find((item) => String(item.id) === String(currentVisitId))
    : getCurrentVisitForClient(clientId);
  const currentLocalVisitId = String(currentVisitId || currentVisit?.id || "");
  const currentBackendEncounterId = currentVisit?.backendId ? String(currentVisit.backendId) : "";

  const isOtherEncounter = (exam) => {
    if (currentBackendEncounterId && exam?.backendEncounterId) {
      return String(exam.backendEncounterId) !== currentBackendEncounterId;
    }
    return String(exam?.visitId || "") !== currentLocalVisitId;
  };

  return (Array.isArray(data.doctorExams) ? data.doctorExams : []).some(
    (exam) =>
      String(exam?.clientId) === String(clientId) &&
      String(exam?.doctorRoleId || "") === roleCode &&
      exam?.isCompleted &&
      isOtherEncounter(exam),
  ) || (Array.isArray(client?.doctorExamHistory) ? client.doctorExamHistory : []).some(
    (exam) => String(exam?.doctorRoleId || "") === roleCode && isOtherEncounter(exam),
  );
}

function buildDoctorMark(roleCode, requiredDoctors, completedDoctors) {
  const requiredCount = requiredDoctors instanceof Map
    ? Number(requiredDoctors.get(roleCode) || 0)
    : requiredDoctors.has(roleCode)
      ? 1
      : 0;
  if (completedDoctors.has(roleCode)) {
    return { value: "✓", title: "Врач пройден в текущем обращении" };
  }
  if (requiredCount > 0) {
    const requiredTitle = requiredCount > 1
      ? `Требуется в текущем обращении: ${requiredCount}`
      : "Требуется в текущем обращении";
    return {
      value: "×",
      title: requiredTitle,
    };
  }
  return { value: "", title: "" };
}

function mapApiService(service) {
  return {
    id: service.id,
    backendId: service.id,
    legacySourceId: service.legacy_source_id,
    name: service.name,
    groupId: service.category_id,
    price: Number(service.price || 0),
    isActive: service.is_active,
    requiresSequence: Boolean(service.requires_sequence),
    recallAfterDays: service.recall_after_days || null,
    sortOrder: service.legacy_source_id || service.id,
    doctorRoleIds: Array.isArray(service.doctor_role_ids) ? service.doctor_role_ids : [],
  };
}

function mapApiServiceCategory(category) {
  return {
    id: category.id,
    code: category.code,
    name: category.name,
    sortOrder: category.sort_order || category.id,
    isActive: true,
  };
}

function mapApiDoctorRole(role) {
  return {
    id: role.id,
    code: role.code,
    name: role.name,
    sortOrder: role.sort_order || role.id,
    isActive: role.is_active !== false,
  };
}

function humanizeApiError(error, fallback = "Не удалось выполнить действие") {
  const message = error?.message || String(error || "");
  if (!message || message === "[object Object]") return fallback;
  if (message.includes("Failed to fetch")) return "Backend недоступен. Проверь, что сервер запущен.";
  if (message.includes("HTTP 409")) return "Похожая запись уже есть в базе.";
  try {
    const parsed = JSON.parse(message);
    if (typeof parsed?.detail === "string") {
      return parsed.detail;
    }
    if (Array.isArray(parsed?.detail) && parsed.detail.length) {
      const validationMessages = parsed.detail
        .map((item) => item?.msg)
        .filter(Boolean);
      if (validationMessages.length) {
        return validationMessages.join(". ");
      }
    }
  } catch {
  }
  return message;
}

async function apiRequest(path, options = {}) {
  ensureDemoAuthConsistency();
  const optionHeaders = options.headers || {};
  const authHeaders = getDemoAuthHeaders();
  let requestBody = options.body;
  if (
    requestBody &&
    typeof requestBody !== "string" &&
    !(requestBody instanceof FormData) &&
    !(requestBody instanceof URLSearchParams) &&
    !(requestBody instanceof Blob)
  ) {
    requestBody = JSON.stringify(requestBody);
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(requestBody instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...authHeaders,
      ...optionHeaders,
    },
    body: requestBody,
  });

  if (!response.ok) {
    let detail = "";
    try {
      const errorBody = await response.json();
      if (errorBody?.detail?.message) {
        detail = errorBody.detail.message;
      } else if (typeof errorBody?.detail === "string") {
        detail = errorBody.detail;
      } else if (Array.isArray(errorBody?.detail)) {
        detail = JSON.stringify({ detail: errorBody.detail });
      } else if (errorBody?.detail && typeof errorBody.detail === "object") {
        detail = JSON.stringify(errorBody.detail);
      }
    } catch {
      detail = await response.text();
    }
    throw new Error(detail || `HTTP ${response.status}`);
  }

  if (response.status === 204) return null;
  return response.json();
}

function getDemoAuthHeaders() {
  return appState.auth?.accessToken
    ? { Authorization: `Bearer ${appState.auth.accessToken}` }
    : {};
}

async function getApiErrorMessage(response) {
  try {
    const errorBody = await response.json();
    if (errorBody?.detail?.message) return errorBody.detail.message;
    if (typeof errorBody?.detail === "string") return errorBody.detail;
    if (Array.isArray(errorBody?.detail)) return JSON.stringify({ detail: errorBody.detail });
    if (errorBody?.detail && typeof errorBody.detail === "object") return JSON.stringify(errorBody.detail);
  } catch {
    try {
      return await response.text();
    } catch {
      return "";
    }
  }
  return "";
}

async function fetchAuthorizedFileObjectUrl(url) {
  ensureDemoAuthConsistency();
  if (!appState.auth?.accessToken) {
    throw new Error("Чтобы открыть файл, войдите под учетной записью сотрудника.");
  }

  const response = await fetch(url, {
    headers: getDemoAuthHeaders(),
  });
  if (!response.ok) {
    throw new Error((await getApiErrorMessage(response)) || `HTTP ${response.status}`);
  }

  return URL.createObjectURL(await response.blob());
}

async function openAuthorizedFileUrl(url, { print = false } = {}) {
  if (!url) return false;
  let objectUrl = "";
  try {
    objectUrl = await fetchAuthorizedFileObjectUrl(url);
    const fileWindow = window.open(objectUrl, "_blank");
    if (!fileWindow) {
      URL.revokeObjectURL(objectUrl);
      return false;
    }

    if (print) {
      const requestPrint = () => {
        try {
          fileWindow.focus();
          fileWindow.print();
        } catch (error) {
          console.warn("Не удалось сразу вызвать окно печати", error);
        }
      };

      window.setTimeout(requestPrint, 1200);
      try {
        fileWindow.addEventListener("load", () => window.setTimeout(requestPrint, 150), { once: true });
      } catch (error) {
        console.warn("Не удалось подписаться на загрузку документа для печати", error);
      }
    }

    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
    return true;
  } catch (error) {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    throw error;
  }
}

function normalizeCenterLookupValue(value) {
  return String(value || "").trim().toLowerCase();
}

async function ensureCentersLoaded() {
  if (data.centersLoaded) return data.centers;
  if (data.centersLoadingPromise) return data.centersLoadingPromise;

  data.centersLoadingPromise = (async () => {
    try {
      const centers = await apiRequest("/centers");
      data.centers = Array.isArray(centers) ? centers : [];
      data.centersLoaded = true;
      return data.centers;
    } finally {
      data.centersLoadingPromise = null;
    }
  })();

  return data.centersLoadingPromise;
}

async function resolveCenterIdForVisit(visit, client) {
  const centers = await ensureCentersLoaded();
  if (!Array.isArray(centers) || !centers.length) {
    throw new Error("Не удалось загрузить список центров");
  }

  const candidateNames = [
    visit?.center,
    client?.center,
    appState.centerFilter !== "all" ? appState.centerFilter : null,
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean);

  for (const candidate of candidateNames) {
    const normalizedCandidate = normalizeCenterLookupValue(candidate);
    const matchedCenter = centers.find((center) => {
      const name = normalizeCenterLookupValue(center?.name);
      const code = normalizeCenterLookupValue(center?.code);
      return normalizedCandidate === name || normalizedCandidate === code;
    });
    if (matchedCenter?.id) {
      return Number(matchedCenter.id);
    }
  }

  if (centers.length === 1 && centers[0]?.id) {
    return Number(centers[0].id);
  }

  throw new Error(`Не удалось определить центр для обращения: ${candidateNames.join(", ") || "центр не указан"}`);
}

async function loginDemoStaff(login, password) {
  if (String(login).trim() === "chairman" && String(password).trim() === "chairman123") {
    appState.auth = {
      accessToken: "demo-token-2",
      userName: "Председатель комиссии",
      roleCode: "chairman",
      roleName: "Председатель",
    };
    persistDemoState();
    return {
      access_token: appState.auth.accessToken,
      user_name: appState.auth.userName,
      role_code: appState.auth.roleCode,
      role_name: appState.auth.roleName,
    };
  }

  const response = await apiRequest("/auth/login", {
    method: "POST",
    body: { login, password },
    headers: {},
  });

  appState.auth = {
    accessToken: response.access_token || "",
    userName: response.user_name || "",
    roleCode: response.role_code || "",
    roleName: response.role_name || "",
  };
  persistDemoState();
  return response;
}

async function loadStaffWorkspace() {
  if (appState.auth.roleCode === "admin") {
    data.staffUsers = [];
    data.staffRoles = [];
    data.staffError = "";
    data.staffLoading = false;
    renderApp();
    return;
  }

  if (appState.auth.roleCode !== "chairman") {
    data.staffUsers = [];
    data.staffRoles = [];
    data.staffError = "Управление сотрудниками доступно только председателю.";
    return;
  }

  data.staffLoading = true;
  data.staffError = "";
  renderApp();

  try {
    const [roles, users] = await Promise.all([
      apiRequest("/staff/roles"),
      apiRequest("/staff"),
    ]);
    data.staffRoles = Array.isArray(roles) ? roles : [];
    data.staffUsers = Array.isArray(users) ? users : [];
  } catch (error) {
    data.staffError = humanizeApiError(error, "Не удалось загрузить сотрудников");
  } finally {
    data.staffLoading = false;
    renderApp();
  }
}

async function createDemoStaffUser(payload) {
  data.staffCreateError = "";
  try {
    const createdUser = await apiRequest("/staff", {
      method: "POST",
      body: JSON.stringify(payload),
      headers: {},
    });
    data.lastCreatedStaffUser = createdUser;
    await loadStaffWorkspace();
    persistDemoState();
    showToast(`Сотрудник ${payload.full_name} создан`);
  } catch (error) {
    data.staffCreateError = humanizeApiError(error, "Не удалось создать сотрудника");
    renderApp();
  }
}

async function deleteDemoStaffUser(userId, userName) {
  try {
    await apiRequest(`/staff/${encodeURIComponent(userId)}`, {
      method: "DELETE",
      headers: {},
    });
    data.staffUsers = (data.staffUsers || []).filter((user) => Number(user.id) !== Number(userId));
    if (Number(data.lastCreatedStaffUser?.id) === Number(userId)) {
      data.lastCreatedStaffUser = null;
    }
    persistDemoState();
    renderApp();
    showToast(`Сотрудник ${userName || userId} удален`);
  } catch (error) {
    data.staffCreateError = humanizeApiError(error, "Не удалось удалить сотрудника");
    renderApp();
  }
}

async function loadServicesFromBackend() {
  try {
    const [categories, roles, services] = await Promise.all([
      apiRequest("/service-categories"),
      apiRequest("/doctor-roles"),
      apiRequest("/services"),
    ]);
    serviceGroups = Array.isArray(categories) ? categories.map(mapApiServiceCategory) : [];
    doctorRoles = Array.isArray(roles) ? roles.map(mapApiDoctorRole) : [];
    data.serverServices = Array.isArray(services) ? services.map(mapApiService) : [];
    structuredServices = data.serverServices.slice();
    data.serverServicesLoaded = true;
    refreshServiceCatalog();
    renderApp();
  } catch (error) {
    data.serverServicesLoaded = Array.isArray(data.serverServices) && data.serverServices.length > 0;
    showToast(humanizeApiError(error, "Не удалось загрузить справочники с backend"));
    console.warn("Не удалось загрузить услуги с backend", error);
  }
}

async function loadDocumentTemplatesFromBackend() {
  try {
    const templates = await apiRequest("/documents/templates");
    data.documentTemplates = Array.isArray(templates) ? templates : [];
    data.documentTemplatesLoaded = true;
  } catch (error) {
    data.documentTemplates = [];
    data.documentTemplatesLoaded = false;
    console.warn("Не удалось загрузить шаблоны документов с backend", error);
  }
}

async function refreshDocumentTemplatesFromBackend() {
  const templates = await apiRequest("/documents/templates/refresh", { method: "POST" });
  data.documentTemplates = Array.isArray(templates) ? templates : [];
  data.documentTemplatesLoaded = true;
  data.templateOperationStatus = "Список шаблонов перечитан из папки файлов.";
  renderApp();
}

async function replaceDocumentTemplateFile(templateId, file) {
  const formData = new FormData();
  formData.append("file", file);
  const template = await apiRequest(`/documents/templates/${encodeURIComponent(templateId)}/replace`, {
    method: "POST",
    body: formData,
  });
  data.documentTemplates = (data.documentTemplates || []).map((item) => (String(item.id) === String(template.id) ? template : item));
  data.templateOperationStatus = `Шаблон "${template.name || template.file_name}" обновлен.`;
  renderApp();
}

function getSelectedBackendClientId() {
  const client = getSelectedClient();
  return client?.backendId || client?.id || null;
}

function getSelectedBackendEncounterId() {
  const client = getSelectedClient();
  const visit = client ? getCurrentVisitForClient(client.id) : null;
  return visit?.backendId || null;
}

function buildQuery(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, value);
  });
  const text = query.toString();
  return text ? `?${text}` : "";
}

function buildGeneratedDocumentUrl(fileName, { inline = false } = {}) {
  if (!fileName) return "";
  const query = inline ? "?inline=1" : "";
  return `${API_BASE_URL}/documents/generated/${encodeURIComponent(fileName)}${query}`;
}

function resolveApiUrl(url) {
  if (!url) return "";
  try {
    return new URL(url).href;
  } catch {
    return new URL(url, API_BASE_URL).href;
  }
}

async function requestGeneratedDocumentPrintTicket(documentItem) {
  const fileName = documentItem?.fileName;
  if (!fileName) {
    throw new Error("Не найден файл документа для печати");
  }
  const ticket = await apiRequest(`/documents/generated/${encodeURIComponent(fileName)}/print-ticket`, {
    method: "POST",
  });
  return {
    ...ticket,
    file_url: resolveApiUrl(ticket?.file_url),
  };
}

function buildTemplateFileUrl(templateId) {
  return `${API_BASE_URL}/documents/templates/${encodeURIComponent(templateId)}/file`;
}

function isContractDocument(documentItem) {
  const text = `${documentItem?.title || ""} ${documentItem?.fileName || ""} ${documentItem?.type || ""}`.toLowerCase();
  return text.includes("договор") || text.includes("contract");
}

async function openGeneratedDocumentInBrowser(documentItem) {
  const inlineUrl = buildGeneratedDocumentUrl(documentItem?.fileName, { inline: true });
  if (!inlineUrl) return false;

  return openAuthorizedFileUrl(inlineUrl);
}

async function openGeneratedDocumentManually(documentItem, options = {}) {
  try {
    const ticket = await requestGeneratedDocumentPrintTicket(documentItem);
    const targetWindow = options.targetWindow;
    if (targetWindow && !targetWindow.closed) {
      targetWindow.location.href = ticket.file_url;
      return true;
    }

    const fileWindow = window.open(ticket.file_url, "_blank");
    if (fileWindow) {
      return true;
    }

    if (options.sameTabFallback !== false) {
      window.location.href = ticket.file_url;
      return true;
    }
  } catch (error) {
    console.warn("Не удалось открыть документ по временной ссылке", error);
  }
  return openGeneratedDocumentInBrowser(documentItem);
}

async function openGeneratedDocumentDirectly(documentItem, options = {}) {
  const targetWindow = options.targetWindow || null;
  try {
    const ticket = await requestGeneratedDocumentPrintTicket(documentItem);
    if (targetWindow && !targetWindow.closed) {
      targetWindow.location.href = ticket.file_url;
      return true;
    }
    window.location.href = ticket.file_url;
    return true;
  } catch (error) {
    if (targetWindow && !targetWindow.closed) {
      targetWindow.close();
    }
    throw error;
  }
}

function mapGeneratedDocument(item) {
  const template = data.documentTemplates.find((candidate) => String(candidate.id) === String(item.template_id));
  return {
    id: item.id,
    backendId: item.id,
    templateId: item.template_id,
    clientId: item.client_id,
    encounterId: item.encounter_id,
    title: template?.name || item.file_name || `Документ ${item.id}`,
    fileName: item.file_name,
    series: item.series || "",
    number: item.document_number || "",
    blankFormId: item.blank_form_id ?? null,
    blankNumber: item.blank_number_snapshot || "",
    cancelledAt: item.cancelled_at || null,
    cancelledReason: item.cancelled_reason || "",
    createdAt: item.generated_at,
    downloadUrl: buildGeneratedDocumentUrl(item.file_name),
  };
}

async function loadWorkflowData(options = {}) {
  const clientId = options.clientId ?? getSelectedBackendClientId();
  const encounterId = options.encounterId ?? getSelectedBackendEncounterId();
  const clientQuery = buildQuery({ client_id: clientId });
  const clientEncounterQuery = buildQuery({ client_id: clientId, encounter_id: encounterId });

  data.workflowDataLoading = true;
  data.workflowDataError = "";
  setTimeout(renderApp, 0);

  try {
    const [
      generatedDocuments,
      documentJournals,
      spoiledBlanks,
      patientConsents,
      medicalRecords,
    ] = await Promise.all([
      apiRequest(`/generated-documents${clientEncounterQuery}`),
      apiRequest(`/document-journals${clientQuery}`),
      apiRequest("/document-journals/spoiled-blanks"),
      apiRequest(`/patient-consents${clientEncounterQuery}`),
      apiRequest(`/medical-records${clientQuery}`),
    ]);

    data.generatedDocuments = Array.isArray(generatedDocuments) ? generatedDocuments.map(mapGeneratedDocument) : [];
    data.documentJournals = Array.isArray(documentJournals) ? documentJournals : [];
    data.spoiledBlanks = Array.isArray(spoiledBlanks) ? spoiledBlanks : [];
    data.patientConsents = Array.isArray(patientConsents) ? patientConsents : [];
    data.medicalRecords = Array.isArray(medicalRecords) ? medicalRecords : [];

    const recordId = data.medicalRecords[0]?.id;
    data.medicalRecordEntries = recordId
      ? await apiRequest(`/medical-records/entries?medical_record_id=${encodeURIComponent(recordId)}`)
      : [];
    if (!Array.isArray(data.medicalRecordEntries)) data.medicalRecordEntries = [];
    data.workflowDataLoaded = true;
  } catch (error) {
    data.workflowDataError = humanizeApiError(error, "Не удалось загрузить журналы и карту пациента");
    console.warn("Failed to load workflow data", error);
  } finally {
    data.workflowDataLoading = false;
    renderApp();
  }
}

function parseRuDateToIso(value, fallback = "1900-01-01") {
  const text = String(value || "").trim();
  const match = text.match(/^(\d{2})\.(\d{2})\.(\d{4}|\d{2})(?:[\s,].*)?$/);
  if (match) {
    const year = match[3].length === 2 ? expandTwoDigitYear(match[3]) : match[3];
    return `${year}-${match[2]}-${match[1]}`;
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  return fallback;
}

function expandTwoDigitYear(value) {
  const year = Number(value);
  if (Number.isNaN(year)) return String(value);
  const currentYear = new Date().getFullYear();
  const currentCentury = Math.floor(currentYear / 100) * 100;
  const currentTwoDigitYear = currentYear % 100;
  return String((year <= currentTwoDigitYear + 20 ? currentCentury : currentCentury - 100) + year).padStart(4, "0");
}

function upsertClientInMemory(client) {
  if (!client) return null;
  const mappedClient = client.rawApiClient ? client : mapApiClient(client);
  const mergeClient = (existing, incoming) => {
    const existingServices = Array.isArray(existing?.services) ? existing.services : [];
    const incomingServices = Array.isArray(incoming?.services) ? incoming.services : [];
    return {
      ...existing,
      ...incoming,
      services: incomingServices.length ? incomingServices : existingServices,
    };
  };
  const existingIndex = data.clients.findIndex(
    (item) =>
      String(item.backendId || item.id) === String(mappedClient.backendId || mappedClient.id) ||
      String(item.patientNumber || "") === String(mappedClient.patientNumber || ""),
  );
  if (existingIndex >= 0) {
    data.clients[existingIndex] = mergeClient(data.clients[existingIndex], mappedClient);
  } else {
    data.clients.unshift(mappedClient);
  }

  const backendIndex = data.backendClients.findIndex((item) => String(item.id) === String(mappedClient.id));
  if (backendIndex >= 0) {
    data.backendClients[backendIndex] = mergeClient(data.backendClients[backendIndex], mappedClient);
  } else {
    data.backendClients.unshift(mappedClient);
  }

  invalidateClientPool();
  return mappedClient;
}

function showClientInDashboardResults(client, options = {}) {
  const mappedClient = upsertClientInMemory(client);
  if (!mappedClient) return null;

  if (options.resetSearch) {
    appState.clientSearch = "";
    data.backendSearch = "";
  }
  appState.selectedClientId = mappedClient.id;
  appState.dashboardPage = 1;
  data.backendClientsLoaded = true;
  data.backendSearchLoading = false;
  data.backendSearchError = "";
  invalidateClientPool();
  renderApp();
  void loadDashboardDoctorStatuses(getVisibleDashboardClients(), { render: true });
  if (options.refresh !== false) {
    window.setTimeout(() => loadClientsFromBackend(appState.clientSearch), 0);
  }
  return mappedClient;
}

function getVisitTitle(visit) {
  if (!visit) return "Обращение не создано";
  return `Обращение от ${visit.visitDate || formatDateTime(visit.createdAt)}`;
}

function getDoctorRoleIdByLabel(label) {
  const normalized = String(label || "").trim().toLowerCase();

  const map = {
    "гинеколог": "gynecologist",
    "стоматолог": "dentist",
    "дерматолог": "dermatologist",
    "невролог": "neurologist",
    "хирург": "surgeon",
    "отоларинголог": "otolaryngologist",
    "офтальмолог": "ophthalmologist",
    "терапевт": "therapist",
    "психиатр": "psychiatrist",
    "инфекционист": "infectionist",
    "фтизиатр": "phthisiatrist",
    "узист": "uzist",
    "председатель": "chairman",
  };

  return map[normalized] || null;
}

function getDoctorFullName(doctorRoleId) {
  return String(data.doctorDirectory?.[String(doctorRoleId || "").trim()] || "").trim();
}

function setDoctorFullName(doctorRoleId, value) {
  const roleId = String(doctorRoleId || "").trim();
  if (!roleId) return;
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (!data.doctorDirectory || typeof data.doctorDirectory !== "object") {
    data.doctorDirectory = {};
  }
  if (normalized) {
    data.doctorDirectory[roleId] = normalized;
  } else {
    delete data.doctorDirectory[roleId];
  }
}

function getDoctorDisplayName(doctorRoleId) {
  const fullName = getDoctorFullName(doctorRoleId);
  if (fullName) return fullName;
  const template = getDoctorTemplate(doctorRoleId);
  if (template?.name) return template.name;

  const role = doctorRoles.find((item) => String(item.id) === String(doctorRoleId) || item.code === doctorRoleId);
  return role?.name || doctorRoleId;
}

function buildDoctorExamFields(template) {
  const result = {};

  (template?.fields || []).forEach((field) => {
    if (
      (field.type === "radio" || field.type === "select") &&
      field.defaultValue === undefined &&
      Array.isArray(field.options) &&
      field.options.length
    ) {
      result[field.key] = field.options[0];
    } else {
      result[field.key] = field.defaultValue ?? "";
    }
  });

  return result;
}

const CHAIRMAN_CERTIFICATE_DEFAULTS = {
  certificate086: {
    diagnosis:
      "патология органа зрения не выявлено, Патология ЛОР-органов не выявлено, рентгенологической симптоматики не выявлено, хирургической патологии не выявлено, По здоровью, По здоровью, по здоровью",
    clearDriverFields: true,
  },
  certificate095: {
    diagnosis:
      "патология органа зрения не выявлено, Патология ЛОР-органов не выявлено, рентгенологической симптоматики не выявлено, хирургической патологии не выявлено, По здоровью, По здоровью, по здоровью",
    clearDriverFields: true,
  },
  pool: {
    medicalRequirements: (client) => `${buildPoolAdmissionVerb(client)} к занятиям спортом и плаванию в бассейне.`,
    conclusionText: (client) => `${buildPoolAdmissionVerb(client)} к занятиям спортом и плаванию в бассейне.`,
    diagnosis:
      "патология органа зрения не выявлено, Патология ЛОР-органов не выявлено, очаговой инфильтративной симптоматики не выявлено, хирургической патологии не выявлено, По здоровью, По здоровью, Практически здоров",
    validity: "6 мес",
    clearDriverFields: true,
  },
};

const CHAIRMAN_DRIVER_FIELD_KEYS = [
  "driverCategories",
  "categoryA",
  "categoryB",
  "categoryC",
  "categoryD",
  "categoryBE",
  "categoryCE",
  "categoryDE",
  "categoryTram",
  "categoryTrolleybus",
  "categoryM",
  "categoryA1",
  "categoryB1",
  "categoryC1",
  "categoryD1",
  "categoryC1E",
  "categoryD1E",
  "categoryTractor",
  "categoryBoat",
  "categorySailing",
  "indicationManual",
  "indicationAutomatic",
  "indicationAcoustic",
  "indicationGlasses",
  "indicationHearingAid",
  "indicationNoHiring",
  "indicationOneYear",
  "restrictionAM",
  "restrictionBBE",
  "restrictionCCE",
  "restrictionNoHands",
  "restrictionNoLegs",
];

function getClientSexKey(client) {
  const sex = String(client?.sex || client?.rawApiClient?.sex || client?.gender || client?.rawApiClient?.gender || "").toLowerCase();
  if (/^(f|female|woman|ж|жен|женский)$/.test(sex) || sex.includes("жен")) return "female";
  if (/^(m|male|man|м|муж|мужской)$/.test(sex) || sex.includes("муж")) return "male";
  const patronymic = String(client?.fullName || "").trim().split(/\s+/)[2] || "";
  if (/(вна|чна|ична)$/i.test(patronymic)) return "female";
  if (/(вич|ич)$/i.test(patronymic)) return "male";
  return "";
}

function buildPoolAdmissionVerb(client) {
  const sex = getClientSexKey(client);
  if (sex === "female") return "Допущена";
  if (sex === "male") return "Допущен";
  return "Допущен(а)";
}

function extractRuDate(value) {
  return String(value ?? "").match(/\b\d{2}\.\d{2}\.(?:\d{4}|\d{2})\b/)?.[0] || "";
}

function todayRuDate() {
  return new Date().toLocaleDateString("ru-RU", RU_DATE_FORMAT_OPTIONS);
}

function buildChairmanAutoEkgConclusion(date) {
  const finalDate = extractRuDate(date) || todayRuDate();
  return `Ритм синусовый, ЧСС , нормальная электрическая позиция сердца, ЭКГ-комплексы без особенностей от ${finalDate}`;
}

function applyCertificateDefaultsToChairmanFields(fields = {}, visit = null) {
  const formType = getChairmanFormTypeForVisit(visit);
  const defaults = CHAIRMAN_CERTIFICATE_DEFAULTS[formType];
  if (!defaults) return fields;

  const result = { ...fields };
  const client = visit ? getClientPool().find((item) => String(item.id) === String(visit.clientId)) : getSelectedClient();
  const visitDate = extractRuDate(visit?.visitDate) || extractRuDate(visit?.createdAt) || todayRuDate();
  const resolveDefault = (value) => (typeof value === "function" ? value(client, visit, result) : value);
  const setIfBlank = (key, value) => {
    if (String(result[key] ?? "").trim()) return;
    result[key] = resolveDefault(value);
  };

  if (defaults.clearDriverFields) {
    CHAIRMAN_DRIVER_FIELD_KEYS.forEach((key) => {
      result[key] = key === "driverCategories" ? "" : false;
    });
  }

  setIfBlank("examDate", visitDate);
  setIfBlank("ekg", `Медицинский центр ООО "ЦМО "ЮЛМЕД", ЭКГ от ${visitDate}`);
  setIfBlank("ekgConclusion", buildChairmanAutoEkgConclusion(visitDate));
  setIfBlank("fluorography", `от ${visitDate} ОГК б.п.`);
  if (defaults.medicalRequirements) setIfBlank("medicalRequirements", defaults.medicalRequirements);
  setIfBlank("diagnosis", defaults.diagnosis);
  if (defaults.conclusionText) setIfBlank("conclusionText", defaults.conclusionText);
  setIfBlank("conclusion", "Годен");
  setIfBlank("validity", defaults.validity || "1 год");
  setIfBlank("organ", "По возрасту");

  return result;
}

function getVisitsForClient(clientId) {
  ensureVisitsStore();
  return data.visits
    .filter((visit) => String(visit.clientId) === String(clientId))
    .sort((a, b) => new Date(b.createdAt || 0) - new Date(a.createdAt || 0));
}

function getCurrentVisitForClient(clientId) {
  ensureVisitsStore();
  const active = data.visits.find(
    (visit) => String(visit.id) === String(appState.activeVisitId) && String(visit.clientId) === String(clientId),
  );
  if (active) return active;
  return getVisitsForClient(clientId)[0] || null;
}

function createVisitForClient(clientId, options = {}) {
  ensureVisitsStore();
  const client = getClientPool().find((item) => String(item.id) === String(clientId));
  if (!client) return null;

  const serviceNames = Array.isArray(options.serviceNames)
    ? options.serviceNames
    : Array.isArray(client.services)
      ? client.services.slice()
      : [];

  const visit = {
    id: generateId("visit"),
    clientId,
    createdAt: new Date().toISOString(),
    visitDate: formatDateTime(new Date()),
    serviceNames,
    serviceIds: Array.isArray(options.serviceIds) ? options.serviceIds.map((id) => String(id)) : [],
    serviceDetails: options.serviceDetails || {},
    center: client.center || "Медцентр 1",
    paymentType: options.paymentType || "Наличные",
    amount: Number(options.amount ?? calculateVisitAmount(serviceNames)),
    comment: options.comment || "",
    examIds: [],
    documentIds: [],
    status: options.status || "draft",
  };

  data.visits.unshift(visit);
  appState.activeVisitId = visit.id;
  appState.visitServiceGroupFilter = "all";
  appState.visitServiceSearch = "";
  persistDemoState();
  ensureRequiredDoctorExamsForVisit(client, visit);
  syncVisitToBackend(visit, client);

  return visit;
}

function createVisitForClientIfNeeded(clientId, options = {}) {
  const existing = getCurrentVisitForClient(clientId);
  if (!options.forceNew && existing && existing.status !== "closed") return existing;
  return createVisitForClient(clientId, options);
}

function updateVisit(visitId, patch = {}) {
  ensureVisitsStore();
  const visit = data.visits.find((item) => String(item.id) === String(visitId));
  if (!visit) return null;

  Object.assign(visit, patch, {
    updatedAt: new Date().toISOString(),
  });

  persistDemoState();
  const client = getClientPool().find((item) => String(item.id) === String(visit.clientId));
  if (client) syncVisitToBackend(visit, client);
  return visit;
}

async function syncVisitToBackend(visit, client) {
  if (!visit || !client) return null;
  if (visit.__backendSyncPromise) return visit.__backendSyncPromise;
  const clientId = client.backendId || client.id;
  if (!clientId || !data.serverServicesLoaded) return null;

  visit.__backendSyncPromise = (async () => {
    visit.__backendSyncing = true;
    try {
      const centerId = await resolveCenterIdForVisit(visit, client);
      const payload = {
        center_id: centerId,
        client_id: Number(clientId),
        encounter_date: parseRuDateToIso(visit.visitDate, new Date().toISOString().slice(0, 10)),
        payment_type: visit.paymentType || "cash",
        total_amount: Number(visit.amount || calculateVisitAmountByIds(getSelectedVisitServiceIds(visit), getVisitServiceDetails(visit))),
        comment: visit.comment || "",
        status: visit.status || "draft",
      };

      const encounter = await apiRequest(visit.backendId ? `/encounters/${visit.backendId}` : "/encounters", {
        method: visit.backendId ? "PUT" : "POST",
        body: JSON.stringify(payload),
      });
      visit.backendId = encounter.id;
      visit.status = encounter.status || visit.status || "draft";

      const selectedServiceIds = getSelectedVisitServiceIds(visit);
      const serviceDetails = getVisitServiceDetails(visit);
      if (Array.isArray(selectedServiceIds)) {
        await apiRequest(`/encounter-services?encounter_id=${encodeURIComponent(visit.backendId)}`, {
          method: "DELETE",
        });
        for (const serviceId of selectedServiceIds) {
          const service = getServiceById(serviceId);
          if (!service?.backendId) continue;
          const detail = serviceDetails[String(serviceId)] || {};
          const unitPrice = Number(detail.unitPrice ?? service.price ?? 0);
          const notes = Object.keys(detail).length ? JSON.stringify(detail) : null;
          await apiRequest("/encounter-services", {
            method: "POST",
            body: JSON.stringify({
              encounter_id: visit.backendId,
              service_id: service.backendId,
              quantity: 1,
              unit_price: unitPrice,
              line_total: unitPrice,
              notes,
            }),
          });
        }
        visit.__backendServicesSaved = true;
      }

      await ensureRequiredDoctorExamsForVisit(client, visit, { syncToBackend: true });
      persistDemoState();
      return visit;
    } catch (error) {
      console.warn("Не удалось сохранить обращение в backend", error);
      return null;
    } finally {
      visit.__backendSyncing = false;
      visit.__backendSyncPromise = null;
    }
  })();

  return visit.__backendSyncPromise;
}

function getServerServiceNameById(serviceId) {
  return data.serverServices.find((service) => String(service.backendId) === String(serviceId))?.name || "";
}

async function loadVisitServicesFromBackend(encounterId) {
  const items = await apiRequest(`/encounter-services?encounter_id=${encodeURIComponent(encounterId)}`);
  return (Array.isArray(items) ? items : [])
    .map((item) => {
      let detail = {};
      if (item.notes) {
        try {
          detail = JSON.parse(item.notes);
        } catch {
          detail = {};
        }
      }
      if (detail.unitPrice === undefined) detail.unitPrice = Number(item.unit_price || 0);
      return {
        serviceId: String(item.service_id),
        serviceName: getServerServiceNameById(item.service_id),
        detail,
      };
    })
    .filter((item) => item.serviceName);
}

window.syncVisitToBackend = syncVisitToBackend;

async function loadEncountersForClient(client) {
  if (!client?.backendId && !client?.id) return;
  const clientId = client.backendId || client.id;
  try {
    const encounters = await apiRequest(`/encounters?client_id=${encodeURIComponent(clientId)}`);
    const existingVisitsByBackendId = new Map(
      data.visits
        .filter((visit) => String(visit.clientId) === String(client.id) && visit.backendId)
        .map((visit) => [String(visit.backendId), visit]),
    );
    const mappedVisits = [];
    for (const encounter of Array.isArray(encounters) ? encounters : []) {
      const serviceItems = await loadVisitServicesFromBackend(encounter.id);
      const serviceNames = serviceItems.map((item) => item.serviceName);
      const serviceIds = serviceItems.map((item) => item.serviceId);
      const serviceDetails = serviceItems.reduce((result, item) => {
        result[item.serviceId] = item.detail || {};
        return result;
      }, {});
      const existingVisit = existingVisitsByBackendId.get(String(encounter.id));
      mappedVisits.push({
        ...(existingVisit || {}),
        id: `encounter-${encounter.id}`,
        backendId: encounter.id,
        clientId: client.id,
        createdAt: encounter.encounter_date,
        visitDate: formatApiDate(encounter.encounter_date),
        serviceNames,
        serviceIds,
        serviceDetails,
        center: client.center || "Медцентр 1",
        paymentType: encounter.payment_type || "cash",
        amount: Number(encounter.total_amount || 0),
        comment: encounter.comment || "",
        examIds: [],
        documentIds: [],
        status: encounter.status || "draft",
      });
    }

    data.visits = [
      ...mappedVisits,
      ...data.visits.filter((visit) => String(visit.clientId) !== String(client.id) || !visit.backendId),
    ];
    appState.activeVisitId = mappedVisits[0]?.id || null;
  } catch (error) {
    showToast("Не удалось загрузить историю обращений клиента");
    console.warn("Failed to load encounters", error);
  }
}

async function loadDoctorExamsForClient(client, visit = null) {
  if (!client?.backendId && !client?.id) return;
  const clientId = client.backendId || client.id;
  const encounterId = visit?.backendId || null;
  const query = encounterId
    ? `/doctor-exams?client_id=${encodeURIComponent(clientId)}&encounter_id=${encodeURIComponent(encounterId)}`
    : `/doctor-exams?client_id=${encodeURIComponent(clientId)}`;

  try {
    const exams = await apiRequest(query);
    const mapped = (Array.isArray(exams) ? exams : []).map((exam) => ({
      id: `exam-${exam.id}`,
      backendId: exam.id,
      clientId: client.id,
      visitId: visit?.id || `encounter-${exam.encounter_id}`,
      backendEncounterId: exam.encounter_id || null,
      doctorRoleId: exam.doctor_role_id,
      status: exam.is_completed ? "completed" : "draft",
      isCompleted: Boolean(exam.is_completed),
      updatedAt: new Date().toISOString(),
      fields: exam.fields_json || {},
    }));

    data.doctorExams = [
      ...data.doctorExams.filter(
        (exam) =>
          String(exam.clientId) !== String(client.id) ||
          (visit && String(exam.visitId) !== String(visit.id)),
      ),
      ...mapped,
    ];
    syncCompletedDoctorMarksToClient(client, mapped);
  } catch (error) {
    showToast("Не удалось загрузить карточки врачей");
    console.warn("Failed to load doctor exams", error);
  }
}

function parseDashboardDoctorStatusServiceDetail(notes) {
  if (!notes) return {};
  try {
    const detail = JSON.parse(notes);
    return detail && typeof detail === "object" ? detail : {};
  } catch {
    return {};
  }
}

function mapDashboardDoctorStatus(status) {
  const services = Array.isArray(status?.services)
    ? status.services.map((service) => ({
        serviceId: String(service.service_id),
        detail: parseDashboardDoctorStatusServiceDetail(service.notes),
      }))
    : [];
  return {
    clientId: status?.client_id,
    encounterId: status?.encounter_id || null,
    encounterStatus: status?.encounter_status || null,
    services,
    completedDoctorRoleIds: Array.isArray(status?.completed_doctor_role_ids)
      ? status.completed_doctor_role_ids.slice()
      : [],
  };
}

function getDashboardDoctorStatus(client) {
  const clientId = client?.backendId || client?.id;
  return clientId ? data.dashboardDoctorStatuses[String(clientId)] || null : null;
}

function getDashboardDoctorStatusVisit(client) {
  const status = getDashboardDoctorStatus(client);
  if (!status?.encounterId) return null;
  return {
    id: `dashboard-encounter-${status.encounterId}`,
    backendId: status.encounterId,
    clientId: client.id,
    serviceIds: status.services.map((service) => service.serviceId),
    serviceDetails: status.services.reduce((result, service) => {
      result[service.serviceId] = service.detail;
      return result;
    }, {}),
    status: status.encounterStatus || "draft",
  };
}

function areDashboardDoctorStatusesReady(clients) {
  return (Array.isArray(clients) ? clients : []).every((client) => {
    const clientId = client?.backendId || client?.id;
    return clientId && Object.hasOwn(data.dashboardDoctorStatuses, String(clientId));
  });
}

async function loadDashboardDoctorStatuses(clients, { render = true } = {}) {
  const items = Array.isArray(clients) ? clients.filter(Boolean) : [];
  const ids = items.map((c) => c?.backendId || c?.id).filter(Boolean);
  if (!ids.length) {
    data.dashboardDoctorStatusesLoading = false;
    data.dashboardDoctorStatusesError = "";
    if (render) renderApp();
    return;
  }

  const requestId = ++data.dashboardDoctorStatusesRequestId;
  data.dashboardDoctorStatusesLoading = true;
  data.dashboardDoctorStatusesError = "";
  if (render) renderApp();

  try {
    const params = ids.map((id) => `client_ids=${encodeURIComponent(id)}`).join("&");
    const statuses = await apiRequest(`/dashboard/client-doctor-statuses?${params}`);
    if (requestId !== data.dashboardDoctorStatusesRequestId) return;

    const nextStatuses = { ...data.dashboardDoctorStatuses };
    ids.forEach((id) => {
      nextStatuses[String(id)] = mapDashboardDoctorStatus({ client_id: id });
    });
    for (const status of Array.isArray(statuses) ? statuses : []) {
      nextStatuses[String(status.client_id)] = mapDashboardDoctorStatus(status);
    }
    data.dashboardDoctorStatuses = nextStatuses;
  } catch (error) {
    if (requestId !== data.dashboardDoctorStatusesRequestId) return;
    data.dashboardDoctorStatusesError = humanizeApiError(error, "Не удалось загрузить отметки врачей");
    console.warn("Failed to load dashboard doctor statuses", error);
  } finally {
    if (requestId !== data.dashboardDoctorStatusesRequestId) return;
    data.dashboardDoctorStatusesLoading = false;
    if (render) renderApp();
  }
}

async function refreshDashboardDoctorStatusForExam(exam, options = {}) {
  const client = getClientPool().find((item) => String(item.id) === String(exam?.clientId));
  if (!client) return;
  await loadDashboardDoctorStatuses([client], options);
}

async function loadClientWorkspace(client) {
  if (!client) return;
  data.medicalRecordEditMode = false;
  data.medicalRecordSaveError = "";
  await loadEncountersForClient(client);
  const visit = getCurrentVisitForClient(client.id);
  await loadDoctorExamsForClient(client, visit);
  await loadWorkflowData({
    clientId: client.backendId || client.id,
    encounterId: visit?.backendId || null,
  });
  renderApp();
}

async function ensureFullClientLoaded(client) {
  if (!client) return null;
  if (client.rawApiClient && Object.hasOwn(client.rawApiClient, "legacy_payload_json")) return client;

  const clientId = client.backendId || client.id;
  const apiClient = await apiRequest(`/clients/${encodeURIComponent(clientId)}`);
  return upsertClientInMemory(apiClient);
}

async function restoreWorkplaceSelection() {
  try {
    const raw = window.localStorage?.getItem(SELECTION_STORAGE_KEY);
    const saved = raw ? JSON.parse(raw) : null;
    if (!saved?.selectedClientId) return;

    const apiClient = await apiRequest(`/clients/${encodeURIComponent(saved.selectedClientId)}`);
    const client = upsertClientInMemory(apiClient);
    if (!client) return;

    appState.selectedClientId = client.id;
    appState.clientSearch = "";
    await loadClientWorkspace(client);

    if (saved.activeEncounterId) {
      const visit = data.visits.find((item) => String(item.backendId) === String(saved.activeEncounterId));
      if (visit) appState.activeVisitId = visit.id;
    }
    renderApp();
  } catch (error) {
    console.warn("Failed to restore workplace selection", error);
  }
}

function syncClientServicesFromVisit(client, visit) {
  if (!client || !visit) return;
  client.services = Array.isArray(visit.serviceNames) ? visit.serviceNames.slice() : [];
  markClientChanged(client, false);
}

function getOrCreateDraftVisit(clientId) {
  const current = getCurrentVisitForClient(clientId);
  if (current && current.status !== "closed") {
    appState.activeVisitId = current.id;
    return current;
  }

  return createVisitForClient(clientId);
}

function getDoctorExam(clientId, visitId, doctorRoleId) {
  ensureVisitsStore();

  return (
    data.doctorExams.find(
      (item) =>
        item.clientId === clientId &&
        item.visitId === visitId &&
        item.doctorRoleId === doctorRoleId,
    ) || null
  );
}

function getDoctorExamById(examId) {
  ensureVisitsStore();
  return data.doctorExams.find((item) => String(item.id) === String(examId)) || null;
}

function getOrCreateDoctorExam(clientId, visitId, doctorRoleId) {
  ensureVisitsStore();

  let exam = getDoctorExam(clientId, visitId, doctorRoleId);
  if (exam) {
    if (doctorRoleId === "chairman") {
      const visit = data.visits.find((item) => String(item.id) === String(visitId));
      const nextFields = applyCertificateDefaultsToChairmanFields(exam.fields || {}, visit);
      if (JSON.stringify(nextFields) !== JSON.stringify(exam.fields || {})) {
        exam.fields = nextFields;
        exam.updatedAt = new Date().toISOString();
        persistDemoState();
      }
    }
    return exam;
  }

  const template = getDoctorTemplate(doctorRoleId);
  if (!template) {
    console.error("Не найден шаблон врача:", doctorRoleId);
    return null;
  }

  exam = {
    id: generateId("exam"),
    clientId,
    visitId,
    doctorRoleId,
    status: "draft",
    isCompleted: false,
    updatedAt: new Date().toISOString(),
    fields: buildDoctorExamFields(template),
  };

  if (doctorRoleId === "chairman") {
    const visit = data.visits.find((item) => String(item.id) === String(visitId));
    if (visit) {
      exam.fields = applyDriverSelectionsToChairmanFields(exam.fields, getDriverDetailFromVisit(visit), visit);
      exam.fields = applyCertificateDefaultsToChairmanFields(exam.fields, visit);
    }
  }

  data.doctorExams.push(exam);

  const visit = data.visits.find((item) => item.id === visitId);
  if (visit && !visit.examIds.includes(exam.id)) {
    visit.examIds.push(exam.id);
  }

  persistDemoState();

  return exam;
}

async function ensureRequiredDoctorExamsForVisit(client, visit, { syncToBackend = false } = {}) {
  if (!client || !visit) return [];
  const requiredRoleCodes = getRequiredDoctorRoleCodesForVisit(visit);
  const createdOrExisting = [];

  requiredRoleCodes.forEach((doctorRoleId) => {
    const exam = getOrCreateDoctorExam(client.id, visit.id, doctorRoleId);
    if (!exam) return;

    if (!exam.isCompleted && exam.status !== "draft") {
      exam.status = "draft";
      exam.updatedAt = new Date().toISOString();
    }

    createdOrExisting.push(exam);
  });

  persistDemoState();

  if (syncToBackend && visit.backendId) {
    for (const exam of createdOrExisting) {
      await syncDoctorExamToBackend(exam);
    }
  }

  return createdOrExisting;
}

function openDoctorExamCard({ clientId, visitId, doctorRoleId }) {
  if (!clientId || !doctorRoleId) return;

  ensureVisitsStore();
  window.closeServiceCardOverlays?.();

  const finalVisitId = visitId || getOrCreateDraftVisit(clientId).id;
  const visit = data.visits.find((item) => String(item.id) === String(finalVisitId));
  const chairmanFormType = getChairmanFormTypeForVisit(visit);
  if (
    doctorRoleId === "chairman" &&
    (chairmanFormType === "sport" || chairmanFormType === "ekg") &&
    typeof window.openSportCard === "function"
  ) {
    const cardService = getServicesForVisit(visit).find((service) =>
      chairmanFormType === "ekg" ? isStandaloneEkgService(service) : isSportService(service)
    ) || { name: CHAIRMAN_FORM_CONFIGS[chairmanFormType]?.label || CHAIRMAN_FORM_CONFIGS.sport.label };
    appState.doctorExamModal = {
      isOpen: false,
      clientId: null,
      visitId: null,
      doctorRoleId: null,
    };
    appState.activeVisitId = finalVisitId;
    persistDemoState();
    window.openSportCard({
      clientId,
      visitId: finalVisitId,
      service: cardService,
      doctorRoleId: "chairman",
    });
    return;
  }

  const exam = getOrCreateDoctorExam(clientId, finalVisitId, doctorRoleId);

  if (!exam) {
    showToast(`Для врача "${getDoctorDisplayName(doctorRoleId)}" пока нет шаблона`);
    return;
  }

  appState.doctorExamModal = {
    isOpen: true,
    clientId,
    visitId: finalVisitId,
    doctorRoleId,
  };
  appState.activeVisitId = finalVisitId;
  persistDemoState();

  renderApp();
}

function closeDoctorExamCard() {
  appState.doctorExamModal = {
    isOpen: false,
    clientId: null,
    visitId: null,
    doctorRoleId: null,
  };

  persistDemoState();
  renderApp();
}

function normalizeChairmanRecordValue(value) {
  const text = String(value ?? "").trim();
  return text || null;
}

function buildChairmanMedicalRecordNotes(fields = {}) {
  const notes = [
    ["medicalRequirements", "Мед. требования"],
    ["ekg", "ЭКГ"],
    ["ekgConclusion", "Заключение ЭКГ"],
    ["fluorography", "Флюорография"],
    ["bloodSource", "Кровь - откуда данные"],
    ["conclusion", "Заключение председателя"],
    ["note", "Примечание"],
  ]
    .map(([key, label]) => {
      const value = normalizeChairmanRecordValue(fields[key]);
      return value ? `${label}: ${value}` : "";
    })
    .filter(Boolean);

  if (fields.vaccinationRefusal) notes.push("Подписан отказ от прививок");
  if (fields.needsKekReferral) notes.push("Нуждается в направлении на КЭК");
  if (fields.stampApplied) notes.push("Печать поставлена");

  return notes.join("\n");
}

function buildChairmanMedicalRecordData(fields = {}) {
  const recordNotes = buildChairmanMedicalRecordNotes(fields);
  return {
    bloodGroup: normalizeChairmanRecordValue(fields.bloodGroup),
    rhFactor: normalizeChairmanRecordValue(fields.rhesusFactor),
    diagnosis: normalizeChairmanRecordValue(fields.diagnosis),
    mkb10: normalizeChairmanRecordValue(fields.mkb10),
    recordNotes: recordNotes || null,
  };
}

function getCompletedChairmanExam(exams = []) {
  return (Array.isArray(exams) ? exams : []).find(
    (entry) => String(entry?.doctorRoleId || "") === "chairman" && entry?.isCompleted,
  ) || null;
}

async function syncChairmanExamToClientAndMedicalRecord(exam) {
  if (!exam || exam.doctorRoleId !== "chairman") return;

  const client = getClientPool().find((item) => String(item.id) === String(exam.clientId));
  if (!client) return;
  const raw = client.rawApiClient || {};
  const visit = data.visits.find((item) => String(item.id) === String(exam.visitId));
  const driverDetail = getDriverDetailFromVisit(visit);
  const fields = exam.fields || {};
  const chairmanFormInfo = getChairmanFormInfo(visit, client);
  const isDriverChairmanFlow = chairmanFormInfo.printMode === "driver-flow";

  const chairmanCategories = isDriverChairmanFlow ? collectChairmanDriverCategories(fields) : [];
  const admissionCategory = isDriverChairmanFlow
    ? String(fields.driverCategories || "").trim() || chairmanCategories.join(", ")
    : "";
  const indicationsList = isDriverChairmanFlow ? collectChairmanDriverIndications(fields) : [];
  const limitationsList = isDriverChairmanFlow ? collectChairmanDriverLimitations(fields) : [];
  const indicationsText = indicationsList.join(", ") || String(fields.diagnosis || raw.indications || "").trim() || null;
  const chairmanMedicalRecordData = buildChairmanMedicalRecordData(fields);

  if (isDriverChairmanFlow && visit) {
    driverDetail.categories = chairmanCategories.slice();
    driverDetail.indications = indicationsList;
    driverDetail.limitations = limitationsList;
    driverDetail.boatFit = Boolean(fields.categoryBoat);
    if (visit.__backendSyncPromise) {
      await visit.__backendSyncPromise;
    }
    await syncVisitToBackend(visit, client);
  }

  const nextRaw = {
    ...raw,
    admission_category: admissionCategory || null,
    indications: indicationsText,
    mkb10: chairmanMedicalRecordData.mkb10 || String(raw.mkb10 || "").trim() || null,
  };

  client.category = resolveAdmissionCategoryValue(nextRaw.admission_category, client.services);
  client.admissionCategory = nextRaw.admission_category || "";
  client.mkb10 = nextRaw.mkb10 || "";
  client.rawApiClient = nextRaw;

  const backendClientId = nextRaw.id || client.backendId || client.id;
  const currentRecord = (data.medicalRecords || []).find(
    (record) => String(record?.client_id) === String(backendClientId),
  ) || null;
  const recordDiagnosis = chairmanMedicalRecordData.diagnosis || indicationsText || currentRecord?.diagnosis || null;
  const recordMkb10 = chairmanMedicalRecordData.mkb10 || nextRaw.mkb10 || currentRecord?.mkb10 || null;
  const recordNotes = chairmanMedicalRecordData.recordNotes || currentRecord?.notes || null;

  if (currentRecord && String(currentRecord.client_id) === String(nextRaw.id || client.backendId || client.id)) {
    currentRecord.blood_group = chairmanMedicalRecordData.bloodGroup || currentRecord.blood_group || null;
    currentRecord.rh_factor = chairmanMedicalRecordData.rhFactor || currentRecord.rh_factor || null;
    currentRecord.dispensary_observation = indicationsText;
    currentRecord.diagnosis = recordDiagnosis;
    currentRecord.mkb10 = recordMkb10;
    currentRecord.notes = recordNotes;
  }

  if (!backendClientId) {
    persistDemoState();
    return;
  }

  const savedClient = await apiRequest(`/clients/${encodeURIComponent(backendClientId)}`, {
    method: "PUT",
    body: JSON.stringify({
      last_name: nextRaw.last_name || "Без фамилии",
      first_name: nextRaw.first_name || "Без имени",
      middle_name: nextRaw.middle_name || null,
      birth_date: nextRaw.birth_date || "1900-01-01",
      sex: nextRaw.sex || null,
      phone: nextRaw.phone || null,
      email: nextRaw.email || null,
      document_type: nextRaw.document_type || null,
      document_series: nextRaw.document_series || null,
      document_number: nextRaw.document_number || null,
      document_issued_by: nextRaw.document_issued_by || null,
      document_issued_date: nextRaw.document_issued_date || null,
      snils: nextRaw.snils || null,
      oms_policy: nextRaw.oms_policy || null,
      address_text: nextRaw.address_text || null,
      notes: nextRaw.notes || null,
      registration_text: nextRaw.registration_text || null,
      admission_category: nextRaw.admission_category || null,
      reference_number: nextRaw.reference_number || null,
      doctor_gynecologist: nextRaw.doctor_gynecologist || null,
      doctor_stomatologist: nextRaw.doctor_stomatologist || null,
      doctor_dermatologist: nextRaw.doctor_dermatologist || null,
      doctor_neurologist: nextRaw.doctor_neurologist || null,
      doctor_surgeon: nextRaw.doctor_surgeon || null,
      doctor_otolaryngologist: nextRaw.doctor_otolaryngologist || null,
      doctor_ophthalmologist: nextRaw.doctor_ophthalmologist || null,
      doctor_therapist: nextRaw.doctor_therapist || null,
      doctor_psychiatrist: nextRaw.doctor_psychiatrist || null,
      doctor_infectionist: nextRaw.doctor_infectionist || null,
      doctor_phthisiatrician: nextRaw.doctor_phthisiatrician || null,
      doctor_uzist: nextRaw.doctor_uzist || null,
      indications: nextRaw.indications || null,
      encounter_date_text: nextRaw.encounter_date_text || null,
      card_number: nextRaw.card_number || null,
      journal_number: nextRaw.journal_number || null,
      no_number: nextRaw.no_number || null,
      flg: nextRaw.flg || null,
      profession: nextRaw.profession || null,
      work_place: nextRaw.work_place || null,
      organization: nextRaw.organization || null,
      mkb10: nextRaw.mkb10 || null,
      real_date_text: nextRaw.real_date_text || null,
      legacy_payload_json: nextRaw.legacy_payload_json || null,
    }),
  });
  upsertClientInMemory(savedClient);

  const recordPayload = {
    ...(currentRecord || {}),
    client_id: backendClientId,
    center_id: currentRecord?.center_id ?? null,
    card_number: currentRecord?.card_number || nextRaw.card_number || null,
    opened_at: currentRecord?.opened_at || parseRuDateToIso(fields.examDate, "") || null,
    insurance_org: currentRecord?.insurance_org || null,
    oms_policy: currentRecord?.oms_policy || nextRaw.oms_policy || null,
    marital_status: currentRecord?.marital_status || null,
    education: currentRecord?.education || null,
    employment_status: currentRecord?.employment_status || null,
    work_place: currentRecord?.work_place || nextRaw.work_place || nextRaw.organization || null,
    position: currentRecord?.position || null,
    disability: currentRecord?.disability || null,
    blood_group: chairmanMedicalRecordData.bloodGroup || currentRecord?.blood_group || null,
    rh_factor: chairmanMedicalRecordData.rhFactor || currentRecord?.rh_factor || null,
    allergies: currentRecord?.allergies || null,
    dispensary_observation: indicationsText || currentRecord?.dispensary_observation || null,
    health_group: currentRecord?.health_group || null,
    diagnosis: recordDiagnosis,
    mkb10: recordMkb10,
    notes: recordNotes,
  };

  const savedRecord = await apiRequest(
    currentRecord?.id ? `/medical-records/${encodeURIComponent(currentRecord.id)}` : "/medical-records",
    {
      method: currentRecord?.id ? "PUT" : "POST",
      body: JSON.stringify(recordPayload),
    },
  );
  data.medicalRecords = [savedRecord];

  persistDemoState();
}

async function saveDoctorExam(examId, updatedFields) {
  ensureVisitsStore();

  const exam = data.doctorExams.find((item) => item.id === examId);
  if (!exam) return false;
  if (exam.__saving) return false;
  exam.__saving = true;

  const previousFields = exam.fields || {};
  const previousUpdatedAt = exam.updatedAt;
  const previousIsCompleted = exam.isCompleted;
  const previousStatus = exam.status;
  exam.fields = {
    ...exam.fields,
    ...updatedFields,
  };
  const visit = data.visits.find((item) => String(item.id) === String(exam.visitId));
  const previousChairmanFields = exam.doctorRoleId === "chairman" && visit?.chairmanFields
    ? { ...visit.chairmanFields }
    : null;
  if (exam.doctorRoleId === "chairman" && visit) {
    visit.chairmanFields = { ...exam.fields };
  }
  exam.updatedAt = new Date().toISOString();
  exam.isCompleted = true;
  exam.status = "completed";
  rememberMkb10Value(exam.fields?.mkb10);
  persistDemoState();
  if (!appState.doctorExamModal?.isOpen) {
    renderApp();
  }
  try {
    if (exam.doctorRoleId === "chairman") {
      await syncDoctorExamToBackend(exam);
      try {
        await syncChairmanExamToClientAndMedicalRecord(exam);
      } catch (chairmanSyncError) {
        console.warn("Не удалось полностью досинхронизировать председателя", chairmanSyncError);
        showToast("Карточка председателя сохранена, но обращение/карта обновились не полностью");
      }
      await refreshDashboardDoctorStatusForExam(exam, { render: false });
      exam.__saving = false;
      return true;
    }
    await syncDoctorExamToBackend(exam);
    await refreshDashboardDoctorStatusForExam(exam, { render: false });
    exam.__saving = false;
    return true;
  } catch (error) {
    exam.fields = previousFields;
    exam.updatedAt = previousUpdatedAt;
    exam.isCompleted = previousIsCompleted;
    exam.status = previousStatus;
    if (exam.doctorRoleId === "chairman" && visit) {
      if (previousChairmanFields) {
        visit.chairmanFields = previousChairmanFields;
      } else {
        delete visit.chairmanFields;
      }
    }
    exam.__saving = false;
    persistDemoState();
    if (!appState.doctorExamModal?.isOpen) {
      renderApp();
    }
    showToast("Не удалось сохранить карточку врача");
    console.warn("Не удалось сохранить карточку врача в backend", error);
    return false;
  }
}

function saveDoctorExamDraft(examId, updatedFields) {
  ensureVisitsStore();

  const exam = data.doctorExams.find((item) => item.id === examId);
  if (!exam) return false;

  exam.fields = {
    ...exam.fields,
    ...updatedFields,
  };
  const visit = data.visits.find((item) => String(item.id) === String(exam.visitId));
  if (exam.doctorRoleId === "chairman" && visit) {
    visit.chairmanFields = { ...exam.fields };
  }
  exam.updatedAt = new Date().toISOString();
  rememberMkb10Value(exam.fields?.mkb10);
  persistDemoState();
  return true;
}

async function deleteDoctorExam(examId) {
  ensureVisitsStore();

  const examIndex = data.doctorExams.findIndex((item) => item.id === examId);
  if (examIndex < 0) return false;

  const [exam] = data.doctorExams.splice(examIndex, 1);
  const visit = data.visits.find((item) => String(item.id) === String(exam.visitId));
  if (visit) {
    visit.examIds = Array.isArray(visit.examIds)
      ? visit.examIds.filter((value) => String(value) !== String(exam.id))
      : [];
  }

  persistDemoState();

  if (!exam.backendId) {
    return true;
  }

  try {
    await apiRequest(`/doctor-exams/${encodeURIComponent(exam.backendId)}`, {
      method: "DELETE",
    });
    await refreshDashboardDoctorStatusForExam(exam, { render: false });
    return true;
  } catch (error) {
    data.doctorExams.splice(examIndex, 0, exam);
    if (visit) {
      visit.examIds = Array.isArray(visit.examIds) ? visit.examIds : [];
      if (!visit.examIds.includes(exam.id)) {
        visit.examIds.push(exam.id);
      }
    }
    persistDemoState();
    showToast("Не удалось удалить карточку врача");
    console.warn("Не удалось удалить карточку врача в backend", error);
    return false;
  }
}

function closeActionModal() {
  actionModal?.classList.add("hidden");
}

function openCompletedDoctorExamActions({ selectedClient, activeVisit, doctorRoleId, currentExam }) {
  const doctorName = getDoctorDisplayName(doctorRoleId);
  openActionModal(
    "Осмотр врача",
    `
      <div class="doctor-mark-action">
        <p>Карточка врача «${escapeHtml(doctorName)}» уже заполнена.</p>
        <div class="client-create-actions">
          <button type="button" class="primary-button" id="viewCompletedDoctorExam">Просмотреть</button>
          <button type="button" class="ghost-button danger-button" id="deleteCompletedDoctorExam">Удалить</button>
        </div>
      </div>
    `,
    "modal--doctor-mark-action",
  );

  document.getElementById("viewCompletedDoctorExam")?.addEventListener("click", () => {
    closeActionModal();
    openDoctorExamCard({
      clientId: selectedClient.id,
      visitId: activeVisit.id,
      doctorRoleId,
    });
  });

  document.getElementById("deleteCompletedDoctorExam")?.addEventListener("click", async () => {
    const removed = await deleteDoctorExam(currentExam.id);
    if (removed) {
      closeActionModal();
      showToast(`Карточка врача "${doctorName}" удалена`);
      renderApp();
    }
  });
}

async function uncompleteDoctorExam(examId) {
  ensureVisitsStore();

  const exam = getDoctorExamById(examId);
  if (!exam) return false;

  const previousIsCompleted = exam.isCompleted;
  const previousStatus = exam.status;
  const previousUpdatedAt = exam.updatedAt;

  exam.isCompleted = false;
  exam.status = "draft";
  exam.updatedAt = new Date().toISOString();
  persistDemoState();

  if (!appState.doctorExamModal?.isOpen) {
    renderApp();
  }

  if (!exam.backendId) {
    return true;
  }

  try {
    const savedExam = await apiRequest(`/doctor-exams/${encodeURIComponent(exam.backendId)}`, {
      method: "PUT",
      body: JSON.stringify({
        is_completed: false,
      }),
    });

    exam.isCompleted = Boolean(savedExam.is_completed);
    exam.status = exam.isCompleted ? "completed" : "draft";
    exam.updatedAt = savedExam.updated_at || new Date().toISOString();
    await refreshDashboardDoctorStatusForExam(exam, { render: false });
    persistDemoState();
    if (!appState.doctorExamModal?.isOpen) {
      renderApp();
    }
    return true;
  } catch (error) {
    exam.isCompleted = previousIsCompleted;
    exam.status = previousStatus;
    exam.updatedAt = previousUpdatedAt;
    persistDemoState();
    if (!appState.doctorExamModal?.isOpen) {
      renderApp();
    }
    showToast("Не удалось снять отметку врача");
    console.warn("Не удалось снять отметку врача в backend", error);
    return false;
  }
}

async function syncDoctorExamToBackend(exam) {
  const client = getClientPool().find((item) => String(item.id) === String(exam.clientId));
  const visit = data.visits.find((item) => String(item.id) === String(exam.visitId));
  const clientId = client?.backendId || client?.id;
  if (!clientId) {
    throw new Error("Cannot sync doctor exam without client id");
  }

  if (visit && !visit.backendId) {
    await syncVisitToBackend(visit, client);
  }
  const savedExam = await apiRequest("/doctor-exams", {
    method: "POST",
    body: JSON.stringify({
      client_id: Number(clientId),
      encounter_id: visit?.backendId ? Number(visit.backendId) : null,
      doctor_role_id: exam.doctorRoleId,
      doctor_name: getDoctorDisplayName(exam.doctorRoleId),
      fields_json: exam.fields || {},
      is_completed: Boolean(exam.isCompleted),
    }),
  });
  exam.backendId = savedExam.id;
  exam.backendEncounterId = savedExam.encounter_id || visit?.backendId || null;
  exam.updatedAt = savedExam.completed_at || savedExam.updated_at || new Date().toISOString();
  exam.fields = savedExam.fields_json || exam.fields || {};
  exam.isCompleted = Boolean(savedExam.is_completed);
  exam.status = exam.isCompleted ? "completed" : "draft";
  if (exam.doctorRoleId === "chairman" && visit) {
    visit.chairmanFields = { ...exam.fields };
  }
  if (exam.isCompleted && client) {
    syncCompletedDoctorMarksToClient(client, [exam]);
  }
  persistDemoState();
  return savedExam;
}

function getDoctorExamStatus(clientId, doctorRoleId) {
  if (!clientId || !doctorRoleId) return "empty";

  const visit = getCurrentVisitForClient(clientId);
  if (!visit) return "empty";
  const exam = getDoctorExam(clientId, visit.id, doctorRoleId);

  if (!exam) {
    const isRequired = getRequiredDoctorRoleCodesForVisit(visit).includes(doctorRoleId);
    const hasHistory = hasCompletedDoctorExamHistory(clientId, doctorRoleId, visit.id);
    if (isRequired && hasHistory) return "draft-history";
    if (isRequired) return "draft";
    if (hasHistory) return "history";
    return "empty";
  }
  if (exam.isCompleted) return "completed";
  return hasCompletedDoctorExamHistory(clientId, doctorRoleId, visit.id) ? "draft-history" : "draft";
}

function getDoctorExamStatusTitle(status) {
  if (status === "completed") return "Врач пройден в текущем обращении";
  if (status === "draft-history") return "Требуется в текущем обращении; есть прошлый осмотр в другом обращении";
  if (status === "draft") return "Требуется в текущем обращении";
  if (status === "history") return "Есть прошлый осмотр в другом обращении";
  return "";
}

function matchesCenter(center) {
  return appState.centerFilter === "all" || center === appState.centerFilter;
}

function normalizeEncounterDateFilterValue(value) {
  const text = String(value || "").trim();
  if (!text) return "";

  const isoMatch = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (isoMatch) return `${isoMatch[3]}.${isoMatch[2]}.${isoMatch[1].slice(-2)}`;

  const ruMatch = text.match(/^(\d{2})\.(\d{2})\.(\d{4}|\d{2})(?:[,\s]+\d{1,2}:\d{2})?/);
  if (ruMatch) return `${ruMatch[1]}.${ruMatch[2]}.${ruMatch[3].slice(-2)}`;

  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return text;
  return parsed.toLocaleDateString("ru-RU", RU_DATE_FORMAT_OPTIONS);
}

function isCompleteEncounterDateFilter(value) {
  const text = String(value || "").trim();
  return !text || /^\d{4}-\d{2}-\d{2}$/.test(text) || /^\d{2}\.\d{2}\.(?:\d{4}|\d{2})$/.test(text);
}

function matchesEncounterDate(client) {
  if (!isCompleteEncounterDateFilter(appState.clientEncounterDate)) return true;
  const filterDate = normalizeEncounterDateFilterValue(appState.clientEncounterDate);
  if (!filterDate) return true;
  const clientDate = normalizeEncounterDateFilterValue(client?.encounterDate || client?.lastVisit || client?.rawApiClient?.encounter_date_text);
  return clientDate === filterDate;
}

function filteredClients() {
  return data.backendClients.filter((client) => matchesCenter(client.center));
}

function getDashboardClientPage() {
  const allClients = data.backendClientsLoaded ? filteredClients() : [];
  const totalPages = Math.max(1, Math.ceil(allClients.length / DASHBOARD_PAGE_SIZE));
  const currentPage = Math.min(Math.max(1, appState.dashboardPage || 1), totalPages);
  const pageStartIndex = (currentPage - 1) * DASHBOARD_PAGE_SIZE;
  return {
    allClients,
    currentPage,
    currentClients: allClients.slice(pageStartIndex, pageStartIndex + DASHBOARD_PAGE_SIZE),
    pageStartIndex,
    totalPages,
  };
}

function getVisibleDashboardClients() {
  return getDashboardClientPage().currentClients;
}

async function loadClientsFromBackend(searchValue) {
  const search = String(searchValue || "").trim();
  const legacyEncounterDate = parseRuDateToIso(appState.clientEncounterDate, "");
  const encounterDateFrom = parseRuDateToIso(appState.clientEncounterDateFrom || legacyEncounterDate, "");
  const encounterDateTo = parseRuDateToIso(appState.clientEncounterDateTo || legacyEncounterDate, "");
  const requestId = ++clientSearchRequestId;
  clientSearchAbortController?.abort();
  const abortController = new AbortController();
  clientSearchAbortController = abortController;

  data.backendSearchLoading = true;
  data.backendSearchError = "";
  setTimeout(renderApp, 0);

  try {
    const params = new URLSearchParams({ limit: String(DASHBOARD_PAGE_SIZE) });
    if (search) params.set("search", search);
    if (encounterDateFrom) params.set("encounter_date_from", encounterDateFrom);
    if (encounterDateTo) params.set("encounter_date_to", encounterDateTo);
    const url = `${API_BASE_URL}/clients/search?${params.toString()}`;
    const response = await fetch(url, { signal: abortController.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const clients = await response.json();
    if (requestId !== clientSearchRequestId) return;

    data.backendClients = Array.isArray(clients) ? clients.map(mapApiClient) : [];
    data.backendClientsLoaded = true;
    invalidateClientPool();
    data.backendSearch = search;
    data.backendSearchLoading = false;
    renderApp();
    void loadDashboardDoctorStatuses(getVisibleDashboardClients());
  } catch (error) {
    if (error?.name === "AbortError") return;
    if (requestId !== clientSearchRequestId) return;
    data.backendClients = [];
    data.backendClientsLoaded = false;
    invalidateClientPool();
    data.backendSearch = search;
    data.backendSearchError = `Backend недоступен: ${API_BASE_URL}`;
    data.backendSearchError = humanizeApiError(error, `Backend недоступен: ${API_BASE_URL}`);
    console.error("Client search API error:", error);
  } finally {
    if (requestId !== clientSearchRequestId) return;
    if (clientSearchAbortController === abortController) clientSearchAbortController = null;
    data.backendSearchLoading = false;
    renderApp();
  }
}

function scheduleClientSearch(searchValue, { render = true } = {}) {
  window.clearTimeout(clientSearchTimer);
  clientSearchAbortController?.abort();
  data.backendSearchLoading = true;
  data.backendSearchError = "";
  if (render) renderApp();
  clientSearchTimer = window.setTimeout(() => {
    loadClientsFromBackend(searchValue);
  }, 250);
}

function formatClientSearchInputValue(value = "") {
  return String(value || "").replace(/[^\s-]+/gu, (part) => {
    const [first = "", ...rest] = Array.from(part);
    return first.toLocaleUpperCase("ru-RU") + rest.join("").toLocaleLowerCase("ru-RU");
  });
}

function resetDashboardClientSelection() {
  window.clearTimeout(clientSearchTimer);
  clientSearchAbortController?.abort();
  clientSearchRequestId += 1;
  appState.clientSearch = "";
  appState.clientEncounterDate = "";
  appState.clientEncounterDateFrom = "";
  appState.clientEncounterDateTo = "";
  appState.dashboardPage = 1;
  appState.selectedClientId = null;
  appState.activeVisitId = null;
  data.backendSearch = "";
  data.backendSearchError = "";
  data.backendSearchLoading = false;
  persistDemoState();
  scheduleClientSearch("");
}

function normalizeSearchValue(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^\dа-яёa-z]+/gi, " ")
    .trim();
}

function buildClientSearchHaystack(client) {
  return normalizeSearchValue([
    client?.patientNumber,
    client?.fullName,
    client?.birthDate,
    client?.registration,
    client?.category,
    client?.referenceNumber,
    client?.profession,
    client?.workPlace,
    client?.organization,
    client?.agent,
    client?.note,
    client?.phone,
    client?.document,
    client?.snils,
    client?.cardNumber,
    client?.encounterDate,
    Array.isArray(client?.services) ? client.services.join(" ") : "",
  ].join(" "));
}

function findDuplicateCandidates(searchValue) {
  const normalizedSearch = normalizeSearchValue(searchValue);
  if (normalizedSearch.length < 2) return [];

  const searchParts = normalizedSearch.split(/\s+/).filter(Boolean);
  if (searchParts.length < 2) return [];

  return getClientPool()
    .filter((client) => matchesCenter(client.center))
    .map((client) => {
      const haystack = normalizeSearchValue(client.fullName);
      const score = searchParts.reduce((total, part) => total + (haystack.includes(part) ? 1 : 0), 0);
      return { client, score };
    })
    .filter((item) => item.score === searchParts.length)
    .sort((a, b) => b.score - a.score || (a.client.patientNumber ?? a.client.id) - (b.client.patientNumber ?? b.client.id))
    .slice(0, 5)
    .map((item) => item.client);
}

function rerenderAndRestoreInput(inputId, value, caretPosition) {
  appState.restoreInputId = inputId;
  renderApp();
  const input = document.getElementById(inputId);
  if (!input) {
    appState.restoreInputId = null;
    return;
  }
  input.focus();
  const safePos = Math.min(caretPosition, value.length);
  input.setSelectionRange(safePos, safePos);
  appState.restoreInputId = null;
}

function renderNav() {
  if (!navRoot) return;
  const visibleNavItems = navItems.filter((item) => (item.id === "reports" ? canAccessReportsWorkspace() : true));

  navRoot.innerHTML = repairDemoText(`
    <div class="nav-group">
      ${visibleNavItems
        .map(
          (item) => `
            <button
              class="${appState.page === item.id ? "active" : ""}"
              data-page="${item.id}"
              data-toast="${item.toast || ""}"
              title="${escapeHtml(item.label)}"
              aria-label="${escapeHtml(item.label)}"
            >
              ${escapeHtml(item.label)}
            </button>
          `,
        )
        .join("")}
    </div>
  `);

  navRoot.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const page = button.dataset.page;
      if (!page) return;
      if (page === "dashboard") {
        resetDashboardClientSelection();
      }
      if (page === "cash") {
        resetCashPeriodToToday();
      }
      if (page === "reports" && !canAccessReportsWorkspace()) {
        showToast("Отчеты доступны только председателю");
        return;
      }
      if (page === "chart") {
        openAmbulatoryCardForCurrentClient();
        if (button.dataset.toast) showToast(button.dataset.toast);
        return;
      }
      appState.page = page;
      setTimeout(renderApp, 0);
      if (page === "employee" && (appState.auth.roleCode === "chairman" || appState.auth.roleCode === "admin") && !data.staffLoading) {
        loadStaffWorkspace();
      }
      if (page === "calendar" && !data.recallItemsLoaded && !data.recallItemsLoading) {
        loadRecallCalendar();
      }
      if (page === "reports" && !data.reportLoading) {
        loadReportsSummary();
      }
      if ((page === "blanks" || page === "chart") && !data.workflowDataLoading) {
        loadWorkflowData();
      }
      if (page === "blanks" && typeof window.loadBlanksData === "function" && !data.blanksLoading) {
        window.loadBlanksData();
      }
      window.scrollTo({ top: 0, behavior: "auto" });
      if (button.dataset.toast) showToast(button.dataset.toast);
    });
  });
}

function buildExcelRows(clients) {
  const registrations = [
    "Гор. Валдай, Ул. Строителей, 10 корп.- кв.-",
    "ЗАТО Озерный, Ул. Киевская, 2А корп.- кв.69",
    "СПб, Пр-Кт Героев, 24 корп.2 кв.313",
    "СПб, - корп.- кв.-",
    "Гор. Чебаркуль, Ул. Каширина, 15 корп.- кв.12",
    "Гор. Кизел, Ул. Пролетарская, 76 корп.- кв.3",
    "Гор. Самара, Ул. Управленческий, Краснолинск",
  ];

  const categories = ["ABC п8", "BC", "ЛМК", "ABCDE п8", "В", "B в9", "BCD"];
  const notes = [
    "ви )",
    "ви )",
    "3. новая наталья пеперони )",
    "вячеслав ) трактор уточ пропис",
    "победа ) уточнить категории",
    "военком ) ТРАКТОР",
    "людмила ) УТОЧ КАТ ДАТУ УЛ",
  ];
  const organizations = ["-", "-", 'ООО "РАДУГА-2"', "-", "-", "-", "Самозанятый"];

  return clients.map((client) => {
    const status = getDashboardDoctorStatus(client);
    const fallbackServiceIds = (Array.isArray(client.services) ? client.services : [])
      .map((name) => getServerServiceByName(name))
      .filter(Boolean)
      .map((service) => getServiceToken(service))
      .filter(Boolean);
    const currentVisit = getDashboardDoctorStatusVisit(client) || (
      fallbackServiceIds.length
        ? {
            id: `dashboard-client-services-${client.id}`,
            clientId: client.id,
            serviceIds: fallbackServiceIds,
            serviceDetails: {},
            status: "draft",
          }
        : null
    );
    const requiredDoctors = currentVisit ? getRequiredDoctorRoleCountsForVisit(currentVisit) : new Map();
    const completedDoctors = new Set(status?.completedDoctorRoleIds || []);
    const markDoctor = (roleCode) => buildDoctorMark(roleCode, requiredDoctors, completedDoctors);

    return {
      id: client.id,
      patientNumber: client.patientNumber ?? client.id,
      fullName: client.fullName,
      birthDate: client.birthDate,
      registration: client.registration || client.document || "",
      category: resolveAdmissionCategoryValue(client.category, client.services),
      referenceNumber: client.referenceNumber || "",
      gynecologist: markDoctor("gynecologist"),
      stomatologist: markDoctor("dentist"),
      dermatologist: markDoctor("dermatologist"),
      neurologist: markDoctor("neurologist"),
      surgeon: markDoctor("surgeon"),
      otolaryngologist: markDoctor("otolaryngologist"),
      ophthalmologist: markDoctor("ophthalmologist"),
      therapist: markDoctor("therapist"),
      psychiatrist: markDoctor("psychiatrist"),
      infectionist: markDoctor("infectionist"),
      phthisiatrician: markDoctor("phthisiatrist"),
      uzist: markDoctor("uzist"),
      chairman: markDoctor("chairman"),
      stamp: "",
      note: client.note || "",
      encounterDate: client.encounterDate || "",
      cardNumber: client.cardNumber || "",
      organization: client.organization || "",
      agent: client.agent || "",
    };
  });
}

function renderDoctorButton(label, selectedClient) {
  const doctorRoleId = getDoctorRoleIdByLabel(label);
  const status = selectedClient && doctorRoleId
    ? getDoctorExamStatus(selectedClient.id, doctorRoleId)
    : "empty";
  const title = getDoctorExamStatusTitle(status);

  return `
    <button
      class="doctor-pill doctor-pill--${status}"
      title="${escapeHtml(title)}"
      data-doctor-label="${escapeHtml(label)}"
      data-doctor-role-id="${escapeHtml(doctorRoleId || "")}"
    >
      ${label}
    </button>
  `;
}

function renderExcelDoctorCell(row, key) {
  const doctorRoleId = doctorRoleByExcelColumn[key] || "";
  const mark = row[key];
  const value = typeof mark === "object" && mark !== null ? mark.value || "" : mark || "";
  const title = typeof mark === "object" && mark !== null ? mark.title || "" : "";
  const modifier = value === "✓" ? "done" : value === "×" ? "required" : "empty";
  return `<span class="excel-doctor-mark excel-doctor-mark--${modifier}" title="${escapeHtml(title)}" data-row-doctor-role-id="${escapeHtml(doctorRoleId)}">${escapeHtml(value)}</span>`;
}

function renderExcelActionCell(value, actionId) {
  return `<span>${escapeHtml(value || "")}</span>`;
}

function collectChairmanModalFormValues(form) {
  const values = {};
  if (!form) return values;

  form.querySelectorAll("[name]").forEach((field) => {
    const key = field.name;
    if (!key) return;
    if (field.type === "checkbox") {
      values[key] = Boolean(field.checked);
      return;
    }
    if (field.type === "radio") {
      if (field.checked) {
        values[key] = field.value;
      } else if (!(key in values)) {
        values[key] = "";
      }
      return;
    }
    values[key] = field.value;
    if (key === "medicalRequirements") {
      window.rememberChairmanMedicalRequirement?.(field.value);
    }
  });

  return values;
}

function getClientDocumentHistory(clientId) {
  const visitIds = getVisitsForClient(clientId).map((visit) => String(visit.id));
  const localDocuments = data.documents
    .filter((item) => visitIds.includes(String(item.visitId)))
    .map((item) => ({ ...item, source: "local" }));
  const backendClientId = getClientPool().find((client) => String(client.id) === String(clientId))?.backendId || clientId;
  const backendDocuments = (data.generatedDocuments || [])
    .filter((item) => String(item.clientId) === String(backendClientId))
    .map((item) => ({ ...item, source: "backend" }));
  const seen = new Set();
  return [...backendDocuments, ...localDocuments]
    .filter((item) => {
      const key = item.backendId ? `backend-${item.backendId}` : `local-${item.id}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => new Date(b.createdAt || 0) - new Date(a.createdAt || 0));
}

function getClientDoctorExamHistory(clientId) {
  return data.doctorExams
    .filter((item) => String(item.clientId) === String(clientId))
    .slice()
    .sort((a, b) => new Date(b.updatedAt || 0) - new Date(a.updatedAt || 0));
}

function getClientRecallHistory(clientId) {
  const source = data.recallItemsLoaded ? data.recallItems : buildLocalRecallItems();
  return source
    .filter((item) => String(item.client_id) === String(clientId))
    .slice()
    .sort((a, b) => new Date(a.planned_date || 0) - new Date(b.planned_date || 0));
}

function renderAmbulatoryCardPage() {
  const selectedClient = getSelectedClient();
  if (!selectedClient) {
    return `
      <section class="card">
        <p class="muted">Сначала выбери клиента на главной странице. После этого здесь появится его полная карта: данные, обращения, врачи, документы и сроки.</p>
      </section>
    `;
  }

  const visits = getVisitsForClient(selectedClient.id);
  const documents = getClientDocumentHistory(selectedClient.id);
  const exams = getClientDoctorExamHistory(selectedClient.id);
  const recalls = getClientRecallHistory(selectedClient.id);
  const completedExams = exams.filter((item) => item.isCompleted);
  const activeVisit = getCurrentVisitForClient(selectedClient.id);

  return `
    <section class="chart-page">
      <div class="chart-page__header">
        <div>
          <p class="muted">Полная карточка клиента по текущей базе: данные, история обращений, осмотры, документы и сроки.</p>
        </div>
        <div class="chart-page__actions">
          <button class="ghost-button" id="chartBackToDashboard">На главную</button>
          <button class="primary-button" id="chartEditClientButton">Изменить клиента</button>
        </div>
      </div>

      <div class="cards-grid chart-summary-grid">
        <article class="summary-card">
          <div class="summary-card__label">Клиент</div>
          <div class="summary-card__value">${escapeHtml(selectedClient.patientNumber ?? selectedClient.id)}</div>
          <div class="summary-card__meta">${escapeHtml(selectedClient.fullName)}</div>
        </article>
        <article class="summary-card">
          <div class="summary-card__label">Обращения</div>
          <div class="summary-card__value">${visits.length}</div>
          <div class="summary-card__meta">${activeVisit ? `Активное: ${escapeHtml(activeVisit.visitDate || "")}` : "Пока без активного обращения"}</div>
        </article>
        <article class="summary-card">
          <div class="summary-card__label">Осмотры врачей</div>
          <div class="summary-card__value">${completedExams.length}</div>
          <div class="summary-card__meta">${exams.length ? `Всего карточек: ${exams.length}` : "Осмотры еще не заполнялись"}</div>
        </article>
      </div>

      ${renderWorkflowLoadState()}
      ${renderMedicalRecordBackendBlock(selectedClient, exams)}

      <div class="two-col chart-main-grid">
        <article class="card chart-profile-card">
          <h3>Паспортная часть</h3>
          <div class="chart-fields">
            <div><span>ФИО</span><strong>${escapeHtml(selectedClient.fullName || "не указано")}</strong></div>
            <div><span>Дата рождения</span><strong>${escapeHtml(selectedClient.birthDate || "не указана")}</strong></div>
            <div><span>Телефон</span><strong>${escapeHtml(selectedClient.phone || "не указан")}</strong></div>
            <div><span>Документ</span><strong>${escapeHtml(selectedClient.document || "не указан")}</strong></div>
            <div><span>СНИЛС</span><strong>${escapeHtml(selectedClient.snils || "не указан")}</strong></div>
            <div><span>Центр</span><strong>${escapeHtml(selectedClient.center || "не указан")}</strong></div>
            <div><span>Регистрация</span>${renderCopyableValue(selectedClient.registration, "регистрацию", { fallback: "не указана", copyMessage: "Регистрация скопирована" })}</div>
            <div><span>Профессия</span><strong>${escapeHtml(selectedClient.profession || "не указана")}</strong></div>
            <div><span>Место работы</span><strong>${escapeHtml(selectedClient.workPlace || "не указано")}</strong></div>
            <div><span>Организация</span><strong>${escapeHtml(selectedClient.organization || "не указана")}</strong></div>
            <div><span>Агент</span><strong>${escapeHtml(selectedClient.agent || "не указан")}</strong></div>
            <div><span>Категория</span><strong>${escapeHtml(selectedClient.category || "не указана")}</strong></div>
            <div><span>№ карты</span><strong>${escapeHtml(selectedClient.cardNumber || "не указан")}</strong></div>
            <div><span>№ справки</span><strong>${escapeHtml(selectedClient.referenceNumber || "не указан")}</strong></div>
            <div><span>МКБ-10</span><strong>${escapeHtml(selectedClient.mkb10 || "не указан")}</strong></div>
          </div>
          ${
            selectedClient.note
              ? `<div class="chart-note"><span>Комментарий</span><p>${escapeHtml(selectedClient.note)}</p></div>`
              : ""
          }
        </article>

        <article class="card chart-profile-card">
          <h3>Сроки и напоминания</h3>
          ${
            recalls.length
              ? `
                <div class="chart-list">
                  ${recalls
                    .map((item) => {
                      const meta = getCalendarStatusMeta(item);
                      return `
                        <div class="chart-list__row">
                          <div>
                            <strong>${escapeHtml(item.service_name)}</strong>
                            <small>${escapeHtml(formatCalendarDate(item.planned_date))}</small>
                          </div>
                          <span class="calendar-status calendar-status--${meta.className}">${meta.label}</span>
                        </div>
                      `;
                    })
                    .join("")}
                </div>
              `
              : `<p class="muted">По клиенту пока нет сроков для обзвона.</p>`
          }
        </article>
      </div>

      <article class="card">
        <h3>История обращений</h3>
        ${
          visits.length
            ? `
              <div class="chart-list">
                ${visits
                  .map(
                    (visit) => `
                      <div class="chart-list__row chart-list__row--visit">
                        <div>
                          <strong>${escapeHtml(getVisitTitle(visit))}</strong>
                          <small>${escapeHtml((visit.serviceNames || []).join(", ") || "услуги не выбраны")}</small>
                          ${visit.comment ? `<small>${escapeHtml(visit.comment)}</small>` : ""}
                        </div>
                        <div class="chart-visit-meta">
                          <span>${escapeHtml(visit.paymentType || "не указано")}</span>
                          <strong>${Number(visit.amount || 0).toLocaleString("ru-RU")} ₽</strong>
                        </div>
                      </div>
                    `,
                  )
                  .join("")}
              </div>
            `
            : `<p class="muted">Обращений по клиенту пока нет.</p>`
        }
      </article>

      <div class="two-col chart-main-grid">
        <article class="card">
          <h3>Осмотры врачей</h3>
          ${
            exams.length
              ? `
                <div class="chart-list">
                  ${exams
                    .map(
                      (exam) => `
                        <div class="chart-list__row">
                          <div>
                            <strong>${escapeHtml(getDoctorDisplayName(exam.doctorRoleId))}</strong>
                            <small>${escapeHtml(formatDateTime(exam.updatedAt))}</small>
                          </div>
                          <span class="calendar-status calendar-status--${exam.isCompleted ? "done" : "planned"}">
                            ${exam.isCompleted ? "Заполнено" : "Черновик"}
                          </span>
                        </div>
                      `,
                    )
                    .join("")}
                </div>
              `
              : `<p class="muted">Карточки врачей еще не заполнялись.</p>`
          }
        </article>

        <article class="card">
          <h3>Документы</h3>
          ${
            documents.length
              ? `
                <div class="chart-list">
                  ${documents
                    .map(
                      (item) => `
                        <div class="chart-list__row">
                          <div>
                            <strong>${escapeHtml(item.fileName || item.title || item.type || "Документ")}</strong>
                            <small>${escapeHtml(formatDateTime(item.createdAt))}</small>
                            ${item.blankNumber ? `<small class="blank-badge">№ бланка: ${escapeHtml(item.blankNumber)}</small>` : ""}
                          </div>
                          <button class="ghost-button" data-open-document-id="${escapeHtml(item.id)}">Открыть</button>
                        </div>
                      `,
                    )
                    .join("")}
                </div>
              `
              : `<p class="muted">По клиенту пока нет сформированных документов.</p>`
          }
        </article>
      </div>
    </section>
  `;
}

function renderDashboardTableSkeleton(rowCount = 8) {
  return Array.from(
    { length: rowCount },
    () => `
      <div class="sketch-table__grid sketch-table__grid--row sketch-table__grid--skeleton" aria-hidden="true">
        ${columnKeys.map(() => '<span><i class="dashboard-table-skeleton-bar"></i></span>').join("")}
      </div>
    `,
  ).join("");
}

function renderSketchHome() {
  const {
    allClients,
    currentPage,
    currentClients,
    pageStartIndex,
    totalPages,
  } = getDashboardClientPage();
  const selectedClient = currentClients.find((client) => client.id === appState.selectedClientId) || getSelectedClient();
  const duplicateCandidates = findDuplicateCandidates(appState.clientSearch).filter((client) => client.id !== selectedClient?.id);
  const hasSelectedClient = Boolean(selectedClient);
  const doctorButtons = [
    "Гинеколог",
    "Стоматолог",
    "Дерматолог",
    "Невролог",
    "Хирург",
    "Отоларинголог",
    "Офтальмолог",
    "Терапевт",
    "Психиатр",
    "Инфекционист",
    "Фтизиатр",
    "Узист",
  ];
  const excelColumns = [
    "Дата обращения",
    "ФИО",
    "Дата рождения",
    "Регистрация",
    "Категории и условия допуска",
    "№ справки",
    "Гинеколог",
    "Стоматолог",
    "Дерматолог",
    "Невролог",
    "Хирург",
    "Отоларинголог",
    "Офтальмолог",
    "Терапевт",
    "Психиатр",
    "Инфекционист",
    "Фтизиатр",
    "Узист",
    "Председатель",
    "Примечания",
    "Номер карты",
    "Организация",
    "Агент",
  ];
  const tableLoading =
    data.backendSearchLoading ||
    (!data.backendClientsLoaded && !data.backendSearchError);
  const tableError = data.backendSearchError;
  const excelRows = tableLoading || tableError ? [] : buildExcelRows(currentClients);
  const pageNumbers = [];
  const pageWindowStart = Math.max(1, currentPage - 2);
  const pageWindowEnd = Math.min(totalPages, pageWindowStart + 4);
  for (let pageNumber = Math.max(1, pageWindowEnd - 4); pageNumber <= pageWindowEnd; pageNumber += 1) {
    pageNumbers.push(pageNumber);
  }
  const dashboardTableHead = `
    <div class="sketch-table__grid sketch-table__grid--head">
      ${excelColumns
        .map(
          (column, index) => `
            <span class="sketch-head-cell sketch-head-cell--resizable">
              <span>${column}</span>
              <button class="col-resize-handle" data-resize-col="${columnKeys[index]}" aria-label="Изменить ширину столбца ${column}"></button>
            </span>
          `,
        )
        .join("")}
    </div>
  `;

  return `
    <section class="sketch-layout">
      <div class="sketch-main sketch-main--full">
        <article class="sketch-panel sketch-panel--dashboard">
          <div class="dashboard-sticky-controls">
            <div class="sketch-doctors-block">
              <div class="sketch-doctors sketch-doctors--top">
                ${doctorButtons.map((label) => renderDoctorButton(label, selectedClient)).join("")}
              </div>
            </div>

            <div class="sketch-toolbar">
              <label class="field sketch-search">
                <span></span>
                <input id="clientSearchInput" value="${escapeHtml(appState.clientSearch)}" placeholder="поиск" autocapitalize="words" />
              </label>
              <div class="sketch-toolbar__actions">
                <button class="primary-button" id="addClientButton" type="button">Добавить</button>
                <button
                  class="secondary-button dashboard-new-visit-button"
                  id="createVisitFromDashboardButton"
                  type="button"
                  ${hasSelectedClient ? "" : "disabled"}
                  title="${hasSelectedClient ? "Создать новое обращение для выбранного клиента" : "Сначала выберите клиента в таблице"}"
                >
                  Новое обращение
                </button>
              </div>
              <div class="client-period-filter">
                <label>
                  <span>С даты</span>
                  <input id="clientEncounterDateFromInput" type="date" value="${escapeHtml(parseRuDateToIso(appState.clientEncounterDateFrom || appState.clientEncounterDate, ""))}" />
                </label>
                <label>
                  <span>По дату</span>
                  <input id="clientEncounterDateToInput" type="date" value="${escapeHtml(parseRuDateToIso(appState.clientEncounterDateTo || appState.clientEncounterDate, getLocalDateInputValue()))}" />
                </label>
                <button class="primary-button" id="applyClientPeriodFilterButton" type="button">Показать</button>
                <button class="ghost-button" id="clearClientPeriodFilterButton" type="button">Сброс</button>
              </div>
              <div class="sketch-toolbar__meta">
                ${
                  tableLoading
                    ? "Загрузка данных..."
                    : allClients.length
                    ? `Показано ${pageStartIndex + 1}-${pageStartIndex + currentClients.length} из ${allClients.length}`
                    : "Клиенты не найдены"
                }
              </div>
            </div>

            <div class="dashboard-table-head-scroll" data-dashboard-head-scroll>
              ${dashboardTableHead}
            </div>
          </div>

          ${data.backendSearchLoading ? '<div class="muted" style="margin: 0 0 8px;">Идет поиск в PostgreSQL...</div>' : ""}
          ${data.backendSearchError ? `<div class="empty" style="margin: 0 0 8px;">${escapeHtml(data.backendSearchError)}</div>` : ""}

          ${
            duplicateCandidates.length
              ? `
                <div class="duplicate-panel">
                  <div class="duplicate-panel__title">Возможные дубли</div>
                  <div class="duplicate-panel__list">
                    ${duplicateCandidates
                      .map(
                        (client) => `
                          <button class="duplicate-card" data-client-id="${client.id}">
                            <strong>${escapeHtml(client.fullName)}</strong>
                            <span>${escapeHtml(client.birthDate)} · ${escapeHtml(client.phone)} · ${escapeHtml(client.document)}</span>
                          </button>
                        `,
                      )
                      .join("")}
                  </div>
                </div>
              `
              : ""
          }

          <div class="sketch-table sketch-table--excel" data-dashboard-table-scroll>
            ${
              tableLoading
                ? renderDashboardTableSkeleton()
                : tableError
                  ? '<div class="empty">Данные таблицы временно недоступны</div>'
                  : excelRows.length
                ? excelRows
                    .map(
                      (row) => `
                        <button type="button" class="sketch-table__grid sketch-table__grid--row ${selectedClient && selectedClient.id === row.id ? "sketch-table__grid--active" : ""}" data-client-id="${row.id}" title="Двойной клик откроет амбулаторную карту">
                          <span>${escapeHtml(row.encounterDate)}</span>
                          <span class="sketch-table__fio">${escapeHtml(displayTableValue(row.fullName))}</span>
                          <span>${escapeHtml(row.birthDate)}</span>
                          <span>${renderCopyableValue(row.registration, "регистрацию", { className: "copyable-table-value", fallback: "—", copyMessage: "Регистрация скопирована", keyboard: false })}</span>
                          <span title="${escapeHtml(row.category || "не указана")}">${escapeHtml(displayTableValue(row.category))}</span>
                          <span>${escapeHtml(row.referenceNumber)}</span>
                          ${renderExcelDoctorCell(row, "gynecologist")}
                          ${renderExcelDoctorCell(row, "stomatologist")}
                          ${renderExcelDoctorCell(row, "dermatologist")}
                          ${renderExcelDoctorCell(row, "neurologist")}
                          ${renderExcelDoctorCell(row, "surgeon")}
                          ${renderExcelDoctorCell(row, "otolaryngologist")}
                          ${renderExcelDoctorCell(row, "ophthalmologist")}
                          ${renderExcelDoctorCell(row, "therapist")}
                          ${renderExcelDoctorCell(row, "psychiatrist")}
                          ${renderExcelDoctorCell(row, "infectionist")}
                          ${renderExcelDoctorCell(row, "phthisiatrician")}
                          ${renderExcelDoctorCell(row, "uzist")}
                          ${renderExcelDoctorCell(row, "chairman")}
                          <span>${escapeHtml(row.note)}</span>
                          <span>${escapeHtml(row.cardNumber)}</span>
                          <span>${escapeHtml(row.organization)}</span>
                          <span>${escapeHtml(row.agent)}</span>
                        </button>
                      `,
                    )
                    .join("")
                : '<div class="empty">По текущему фильтру клиентов не найдено</div>'
            }
          </div>

          ${
            allClients.length
              ? `
                <div class="table-pagination">
                  <button class="ghost-button table-pagination__button" data-dashboard-page="${Math.max(1, currentPage - 1)}" ${currentPage === 1 ? "disabled" : ""}>Назад</button>
                  <div class="table-pagination__pages">
                    ${pageNumbers
                      .map(
                        (pageNumber) => `
                          <button
                            class="table-pagination__page ${pageNumber === currentPage ? "table-pagination__page--active" : ""}"
                            data-dashboard-page="${pageNumber}"
                          >
                            ${pageNumber}
                          </button>
                        `,
                      )
                      .join("")}
                  </div>
                  <button class="ghost-button table-pagination__button" data-dashboard-page="${Math.min(totalPages, currentPage + 1)}" ${currentPage === totalPages ? "disabled" : ""}>Вперед</button>
                </div>
              `
              : ""
          }
        </article>
      </div>
    </section>
  `;
}

async function fileToBase64(file) {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  let binary = "";
  for (let index = 0; index < bytes.length; index += chunkSize) {
    const chunk = bytes.subarray(index, index + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return window.btoa(binary);
}

function resetClientImportState() {
  data.importPreview = null;
  data.importError = "";
  data.importSuccess = "";
}

async function previewClientImport() {
  if (!data.importFileBase64 || !data.importFileName) {
    showToast("Сначала выбери заполненный Excel-файл");
    return;
  }

  data.importLoading = true;
  data.importError = "";
  data.importSuccess = "";
  renderApp();
  try {
    data.importPreview = await apiRequest("/imports/clients-excel/preview", {
      method: "POST",
      body: JSON.stringify({
        file_name: data.importFileName,
        file_content_base64: data.importFileBase64,
      }),
    });
  } catch (error) {
    data.importError = humanizeApiError(error, "Не удалось разобрать Excel-файл");
  } finally {
    data.importLoading = false;
    renderApp();
  }
}

async function commitClientImport() {
  if (!data.importFileBase64 || !data.importFileName) {
    showToast("Сначала выбери заполненный Excel-файл");
    return;
  }

  data.importLoading = true;
  data.importError = "";
  data.importSuccess = "";
  renderApp();
  try {
    const result = await apiRequest("/imports/clients-excel/commit", {
      method: "POST",
      body: JSON.stringify({
        file_name: data.importFileName,
        file_content_base64: data.importFileBase64,
      }),
    });
    data.importSuccess = `Импорт завершен. Создано: ${result.created}. Обновлено: ${result.updated}.`;
    data.importPreview = null;
    scheduleClientSearch(appState.clientSearch || "");
  } catch (error) {
    data.importError = humanizeApiError(error, "Не удалось загрузить клиентов");
  } finally {
    data.importLoading = false;
    renderApp();
  }
}

function renderClientImportPage() {
  const preview = data.importPreview;
  return `
    <section class="import-page">
      <article class="card">
        <div class="import-page__header">
          <div>
            <h3>Загрузка клиентов</h3>
            <p class="muted">Скачай шаблон, отправь его заводу для заполнения, потом загрузи готовый Excel сюда.</p>
          </div>
          <a class="primary-button" href="./client-import-template.xlsx" download>Скачать шаблон Excel</a>
        </div>

        <div class="import-help">
          <div>
            <strong>Как это работает</strong>
            <ol>
              <li>Скачать шаблон.</li>
              <li>Отправить его клиенту/заводу для заполнения.</li>
              <li>Выбрать заполненный файл ниже.</li>
              <li>Сначала посмотреть предпросмотр, потом загрузить в базу.</li>
            </ol>
          </div>
          <div>
            <strong>Что загрузчик умеет</strong>
            <ul>
              <li>создавать новых клиентов;</li>
              <li>обновлять существующих по СНИЛС, документу или ФИО + дате рождения;</li>
              <li>поддерживает файлы <code>.xlsx</code> и <code>.xls</code>.</li>
            </ul>
          </div>
        </div>

        <div class="import-upload-box">
          <label class="field field--wide">
            <span>Заполненный файл</span>
            <input id="clientImportFileInput" type="file" accept=".xlsx,.xls" />
          </label>
          <div class="import-upload-box__actions">
            <button class="ghost-button" id="previewClientImportButton" ${data.importLoading ? "disabled" : ""}>Предпросмотр</button>
            <button class="primary-button" id="commitClientImportButton" ${data.importLoading ? "disabled" : ""}>Загрузить в базу</button>
          </div>
          <div class="muted">${escapeHtml(data.importFileName || "Файл еще не выбран")}</div>
        </div>

        ${data.importLoading ? '<p class="muted">Идет обработка файла...</p>' : ""}
        ${data.importError ? `<div class="empty">${escapeHtml(data.importError)}</div>` : ""}
        ${data.importSuccess ? `<div class="import-success">${escapeHtml(data.importSuccess)}</div>` : ""}
      </article>

      ${
        preview
          ? `
            <article class="card">
              <h3>Предпросмотр загрузки</h3>
              <div class="cards-grid import-stats-grid">
                <div class="summary-card">
                  <div class="summary-card__label">Строк в файле</div>
                  <div class="summary-card__value">${preview.parsed_rows}</div>
                </div>
                <div class="summary-card">
                  <div class="summary-card__label">Будет создано</div>
                  <div class="summary-card__value">${preview.created_candidates}</div>
                </div>
                <div class="summary-card">
                  <div class="summary-card__label">Будет обновлено</div>
                  <div class="summary-card__value">${preview.update_candidates}</div>
                </div>
              </div>

              <div class="import-preview-list">
                ${preview.preview_rows
                  .map(
                    (row) => `
                      <div class="import-preview-row">
                        <div>
                          <strong>${escapeHtml(row.full_name)}</strong>
                          <small>Строка ${row.row_number}${row.birth_date ? ` В· ${escapeHtml(row.birth_date)}` : ""}${row.organization ? ` В· ${escapeHtml(row.organization)}` : ""}</small>
                        </div>
                        ${row.agent ? `<small>Агент: ${escapeHtml(row.agent)}</small>` : ""}
                        <div class="import-preview-row__meta">
                          <span class="calendar-status calendar-status--${row.status === "create" ? "planned" : "done"}">
                            ${row.status === "create" ? "Создание" : "Обновление"}
                          </span>
                          ${row.match_reason ? `<small>${escapeHtml(row.match_reason)}</small>` : ""}
                        </div>
                      </div>
                    `,
                  )
                  .join("")}
              </div>
            </article>
          `
          : ""
      }
    </section>
  `;
}

function renderStubPage(title) {
  return `
    <section class="card">
      <h3>${title}</h3>
      <p class="muted">Этот экран пока оставлен как заглушка в демке. Основная рабочая настройка сейчас идет на главной странице.</p>
    </section>
  `;
}

function renderEmployeePage() {
  const isChairman = canManageEmployeeWorkspace();
  const isAdmin = appState.auth.roleCode === "admin";
  const userName = appState.auth.userName || "Не авторизован";
  const roleName = appState.auth.roleName || "Нет роли";

  return `
    <section class="card">
      <h3>Сотрудники</h3>
      <p class="muted">Демо-страница для проверки аутентификации сотрудников и ролей. Председатель создает учетные записи и назначает роли, админ работает в ограниченном режиме без отчетов и без управления доступами.</p>
      <div class="employee-grid">
        <div class="summary-card">
          <div class="summary-card__label">Текущий пользователь</div>
          <div class="summary-card__value">${escapeHtml(userName)}</div>
          <div class="summary-card__meta">${escapeHtml(roleName)}</div>
        </div>
        <div class="summary-card">
          <div class="summary-card__label">Точка входа</div>
          <div class="summary-card__value">Сотрудники</div>
          <div class="summary-card__meta">chairman / chairman123</div>
        </div>
        <div class="summary-card">
          <div class="summary-card__label">Распределение ролей</div>
          <div class="summary-card__value">Только председатель</div>
          <div class="summary-card__meta">Админ без отчетов и без назначения ролей</div>
        </div>
      </div>

      <div class="actions">
        <button class="primary-button" id="openEmployeeLogin">${appState.auth.accessToken ? "Сменить пользователя" : "Войти по логину"}</button>
        <button class="ghost-button" id="refreshEmployeeStaff" ${isChairman ? "" : "disabled"}>Обновить список</button>
        <button class="ghost-button" id="employeeSignOut" ${appState.auth.accessToken ? "" : "disabled"}>Выйти</button>
      </div>

      ${data.staffError ? `<div class="note employee-note employee-note--error">${escapeHtml(data.staffError)}</div>` : ""}

      ${
        isChairman
          ? `
            <div class="employee-card-grid">
              <section class="mini-card">
                <h3>Роли</h3>
                <div class="table">
                  ${
                    (data.staffRoles || []).map((role) => `
                      <div class="table-row">
                        <div class="table-row__title">${escapeHtml(role.name || role.code)}</div>
                        <div class="table-row__meta">${escapeHtml(role.description || role.code || "")}</div>
                      </div>
                    `).join("") || `<div class="empty">Роли пока не загружены.</div>`
                  }
                </div>
              </section>
              <section class="mini-card">
                <h3>Создать сотрудника</h3>
                <form class="field-grid cols-2" id="employeeCreateForm">
                  <label class="field">
                    <span>ФИО</span>
                    <input name="full_name" placeholder="Например, Иванов Иван Иванович" required />
                  </label>
                  <label class="field">
                    <span>Логин</span>
                    <input name="login" placeholder="ivanov" required />
                  </label>
                  <label class="field">
                    <span>Пароль</span>
                    <input name="password" value="temp12345" required />
                  </label>
                  <label class="field">
                    <span>Роль</span>
                    <select name="role_code">
                      ${(data.staffRoles || []).map((role) => `<option value="${escapeHtml(role.code)}">${escapeHtml(role.name)}</option>`).join("")}
                    </select>
                  </label>
                  <label class="field field--wide">
                    <span>Email</span>
                    <input name="email" placeholder="optional@example.com" />
                  </label>
                  ${data.staffCreateError ? `<div class="note employee-note employee-note--error field--wide">${escapeHtml(data.staffCreateError)}</div>` : ""}
                  <div class="actions field--wide">
                    <button class="primary-button" type="submit">Создать учетную запись</button>
                  </div>
                </form>
              </section>
              <section class="mini-card">
                <h3>Учетные записи</h3>
                ${
                  data.lastCreatedStaffUser
                    ? `
                      <div class="note">
                        Последний созданный сотрудник:
                        <strong>${escapeHtml(data.lastCreatedStaffUser.full_name || data.lastCreatedStaffUser.login || "Сотрудник")}</strong>
                        · логин <strong>${escapeHtml(data.lastCreatedStaffUser.login || "")}</strong>
                        · роль <strong>${escapeHtml(data.lastCreatedStaffUser.role?.name || data.lastCreatedStaffUser.role?.code || "")}</strong>
                      </div>
                    `
                    : ""
                }
                ${
                  data.staffLoading
                    ? `<div class="empty">Загружаем сотрудников...</div>`
                    : `
                      <div class="table">
                        ${
                          (data.staffUsers || []).map((user) => `
                            <div class="table-row">
                              <div class="table-row__top">
                                <div class="table-row__title">${escapeHtml(user.full_name || user.login)}</div>
                                <div class="actions">
                                  <span class="status ${user.is_active ? "ok" : "warn"}">${user.is_active ? "Активен" : "Отключен"}</span>
                                  ${user.role?.code !== "chairman" ? `<button class="ghost-button" type="button" data-delete-staff-user="${escapeHtml(user.id)}" data-delete-staff-name="${escapeHtml(user.full_name || user.login || "сотрудник")}">Удалить</button>` : ""}
                                </div>
                              </div>
                              <div class="table-row__meta">${escapeHtml(user.login)} · ${escapeHtml(user.role?.name || "Без роли")}</div>
                            </div>
                          `).join("") || `<div class="empty">Сотрудники пока не найдены.</div>`
                        }
                      </div>
                    `
                }
              </section>
            </div>
          `
          : isAdmin
            ? `
              <div class="note">
                Вы вошли как <strong>${escapeHtml(roleName)}</strong>. Здесь доступен только ограниченный режим:
                без создания сотрудников, без распределения ролей и без доступа к отчетам.
              </div>
            `
          : `
            <div class="note">
              Чтобы открыть контур сотрудников, нажмите <strong>Войти по логину</strong>.
              Председатель увидит роли и список учетных записей, а админ откроется в ограниченном режиме.
            </div>
          `
      }
    </section>
  `;
}

function formatPaymentTypeLabel(value) {
  const normalized = String(value || "").trim().toLowerCase();
  const map = {
    cash: "нал",
    card: "карта",
    invoice: "безнал",
    "наличные": "нал",
    "карта": "карта",
    "безнал": "безнал",
    "организация": "организация",
  };
  return map[normalized] || value || "не указано";
}

function normalizeCashFilterDate(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const date = parseCalendarDate(text);
  if (!date) return "";
  return getLocalDateInputValue(date);
}

function resetCashPeriodToToday() {
  const today = getLocalDateInputValue();
  appState.cashDateFrom = today;
  appState.cashDateTo = today;
}

function isVisitInCashPeriod(visit) {
  const visitDate = parseCalendarDate(visit?.visitDate || visit?.createdAt);
  if (!visitDate) return false;
  visitDate.setHours(0, 0, 0, 0);

  let dateFrom = normalizeCashFilterDate(appState.cashDateFrom);
  let dateTo = normalizeCashFilterDate(appState.cashDateTo);
  if (dateFrom && dateTo && dateFrom > dateTo) {
    [dateFrom, dateTo] = [dateTo, dateFrom];
  }

  if (dateFrom) {
    const fromDate = new Date(`${dateFrom}T00:00:00`);
    fromDate.setHours(0, 0, 0, 0);
    if (visitDate < fromDate) return false;
  }

  if (dateTo) {
    const toDate = new Date(`${dateTo}T00:00:00`);
    toDate.setHours(0, 0, 0, 0);
    if (visitDate > toDate) return false;
  }

  return true;
}

function getCashVisitRows() {
  ensureVisitsStore();
  return data.visits
    .slice()
    .sort((a, b) => new Date(b.createdAt || 0) - new Date(a.createdAt || 0))
    .filter((visit) => isVisitInCashPeriod(visit))
    .map((visit) => {
      const client = getClientPool().find((item) => String(item.id) === String(visit.clientId));
      const serviceDetails = getVisitServiceDetails(visit);
      const serviceIds = getSelectedVisitServiceIds(visit);
      const services = serviceIds.length
        ? serviceIds.map((serviceId) => {
            const service = getServiceById(serviceId);
            const detail = serviceDetails[String(serviceId)] || {};
            const basePrice = Number(service?.price || 0);
            const paidPrice = Number(detail.unitPrice ?? basePrice);
            return {
              name: service?.name || detail.name || "Услуга",
              basePrice,
              paidPrice,
              discount: Math.max(0, basePrice - paidPrice),
              paymentType: detail.paymentType || visit.paymentType || "",
              comment: detail.comment || "",
            };
          })
        : (visit.serviceNames || []).map((name) => {
            const service = getServiceByName(name);
            const basePrice = Number(service?.price || 0);
            return {
              name,
              basePrice,
              paidPrice: basePrice,
              discount: 0,
              paymentType: visit.paymentType || "",
              comment: "",
            };
          });
      const calculatedAmount = calculateVisitAmountByIds(serviceIds, serviceDetails);
      const amount = Number(visit.amount ?? calculatedAmount);
      const paymentTotals = getVisitPaymentTotals(services, amount, visit.paymentType);
      const paymentLabels = Array.from(new Set(
        services
          .map((service) => formatPaymentTypeLabel(service.paymentType))
          .filter(Boolean),
      ));
      const paymentLabel = paymentLabels.length === 1
        ? paymentLabels[0]
        : paymentLabels.length > 1
          ? "смешанная"
          : formatPaymentTypeLabel(visit.paymentType);
      return {
        visit,
        client,
        services,
        amount,
        discount: services.reduce((sum, service) => sum + service.discount, 0),
        cashAmount: paymentTotals.cash,
        nonCashAmount: paymentTotals.nonCash,
        paymentLabel,
      };
    });
}

function renderCashPage() {
  const rows = getCashVisitRows();
  const total = rows.reduce((sum, row) => sum + row.amount, 0);
  const discountTotal = rows.reduce((sum, row) => sum + row.discount, 0);
  const cashTotal = rows.reduce((sum, row) => sum + row.cashAmount, 0);
  const nonCashTotal = rows.reduce((sum, row) => sum + row.nonCashAmount, 0);
  const dateFrom = normalizeCashFilterDate(appState.cashDateFrom) || getLocalDateInputValue();
  const dateTo = normalizeCashFilterDate(appState.cashDateTo) || dateFrom;

  return `
    <section class="cash-page">
      <div class="card cash-toolbar">
        <div>
          <h3>Касса</h3>
          <p class="muted">По умолчанию показана текущая смена за сегодня. Период можно выбрать вручную.</p>
        </div>
        <div class="cash-toolbar__filters">
          <label class="field">
            <span>С даты</span>
            <input id="cashDateFrom" type="date" value="${escapeHtml(dateFrom)}" />
          </label>
          <label class="field">
            <span>По дату</span>
            <input id="cashDateTo" type="date" value="${escapeHtml(dateTo)}" />
          </label>
          <button type="button" class="ghost-button" id="cashPeriodTodayButton">Сегодня</button>
        </div>
      </div>
      <div class="cash-summary">
        <article class="summary-card">
          <div class="summary-card__label">Итого за смену</div>
          <div class="summary-card__value">${total.toLocaleString("ru-RU")} ₽</div>
          <div class="summary-card__meta">${rows.length ? `Обращений: ${rows.length}` : "Пока нет оплат"}</div>
        </article>
        <article class="summary-card">
          <div class="summary-card__label">Наличные</div>
          <div class="summary-card__value">${cashTotal.toLocaleString("ru-RU")} ₽</div>
          <div class="summary-card__meta">по выбранному типу оплаты</div>
        </article>
        <article class="summary-card">
          <div class="summary-card__label">Карта / безнал</div>
          <div class="summary-card__value">${nonCashTotal.toLocaleString("ru-RU")} ₽</div>
          <div class="summary-card__meta">все кроме наличных</div>
        </article>
        <article class="summary-card">
          <div class="summary-card__label">Скидки</div>
          <div class="summary-card__value">${discountTotal.toLocaleString("ru-RU")} ₽</div>
          <div class="summary-card__meta">разница с прайсом</div>
        </article>
      </div>

      <div class="cash-list">
        ${
          rows.length
            ? rows
                .map((row) => {
                  const visit = row.visit;
                  const client = row.client;
                  const visitComment = visit.comment || "";
                  return `
                    <article class="cash-row">
                      <div class="cash-row__head">
                        <div>
                          <strong>${escapeHtml(client?.fullName || "Клиент не найден")}</strong>
                          <span>${escapeHtml(visit.visitDate || formatDateTime(visit.createdAt))}</span>
                        </div>
                        <div class="cash-row__total">
                          <span>${escapeHtml(row.paymentLabel)}</span>
                          <strong>${row.amount.toLocaleString("ru-RU")} ₽</strong>
                        </div>
                      </div>
                      <div class="cash-services">
                        ${
                          row.services.length
                            ? row.services
                                .map(
                                  (service) => `
                                    <div class="cash-service-line">
                                      <span>${escapeHtml(service.name)}</span>
                                      <small>Прайс: ${service.basePrice.toLocaleString("ru-RU")} ₽</small>
                                      <small>Оплачено: ${service.paidPrice.toLocaleString("ru-RU")} ₽</small>
                                      <small class="${service.discount ? "cash-service-line__discount" : ""}">${service.discount ? `Скидка: ${service.discount.toLocaleString("ru-RU")} ₽` : "Без скидки"}</small>
                                      <small>${escapeHtml(formatPaymentTypeLabel(service.paymentType))}</small>
                                      <em>${escapeHtml(service.comment || visitComment || "комментария нет")}</em>
                                    </div>
                                  `,
                                )
                                .join("")
                            : `<div class="muted">Услуги не выбраны</div>`
                        }
                      </div>
                      ${
                        visitComment
                          ? `<div class="cash-row__comment">Комментарий: ${escapeHtml(visitComment)}</div>`
                          : ""
                      }
                    </article>
                  `;
                })
                .join("")
            : `<article class="card"><p class="muted">Оплат пока нет. Создай клиента, выбери услуги, при необходимости измени цену и нажми ОК.</p></article>`
        }
      </div>
    </section>
  `;
}

function renderReportsPage() {
  const normalizedFrom = normalizeCashFilterDate(appState.reportDateFrom) || getLocalDateInputValue();
  const normalizedTo = normalizeCashFilterDate(appState.reportDateTo) || normalizedFrom;
  const report = data.reportSummary;
  const totals = report?.totals || {
    clients_count: 0,
    documents_count: 0,
    services_count: 0,
    revenue: 0,
  };

  return `
    <section class="cash-page">
      <div class="card cash-toolbar">
        <div>
          <h3>Отчеты</h3>
          <p class="muted">Сводка по центрам за день или период: клиенты, документы, услуги и выручка.</p>
        </div>
        <div class="cash-toolbar__filters">
          <label class="field">
            <span>С даты</span>
            <input id="reportDateFrom" type="date" value="${escapeHtml(normalizedFrom)}" />
          </label>
          <label class="field">
            <span>По дату</span>
            <input id="reportDateTo" type="date" value="${escapeHtml(normalizedTo)}" />
          </label>
          <button type="button" class="ghost-button" id="reportPeriodTodayButton">Сегодня</button>
        </div>
      </div>

      ${data.reportError ? `<div class="card"><p class="muted">${escapeHtml(data.reportError)}</p></div>` : ""}

      <div class="cash-summary">
        <article class="summary-card">
          <div class="summary-card__label">Клиенты</div>
          <div class="summary-card__value">${Number(totals.clients_count || 0).toLocaleString("ru-RU")}</div>
          <div class="summary-card__meta">уникальные по обращениям за период</div>
        </article>
        <article class="summary-card">
          <div class="summary-card__label">Документы</div>
          <div class="summary-card__value">${Number(totals.documents_count || 0).toLocaleString("ru-RU")}</div>
          <div class="summary-card__meta">сформированные через backend</div>
        </article>
        <article class="summary-card">
          <div class="summary-card__label">Услуги</div>
          <div class="summary-card__value">${Number(totals.services_count || 0).toLocaleString("ru-RU")}</div>
          <div class="summary-card__meta">сумма количеств по обращениям</div>
        </article>
        <article class="summary-card">
          <div class="summary-card__label">Выручка</div>
          <div class="summary-card__value">${Number(totals.revenue || 0).toLocaleString("ru-RU")} ₽</div>
          <div class="summary-card__meta">${report ? `${escapeHtml(report.date_from)} - ${escapeHtml(report.date_to)}` : "период загрузки"}</div>
        </article>
      </div>

      ${
        data.reportLoading
          ? `<div class="card"><p class="muted">Загружаю отчет по центрам...</p></div>`
          : `
            <div class="card">
              <div class="data-table">
                <table>
                  <thead>
                    <tr>
                      <th>Центр</th>
                      <th>Код</th>
                      <th>Клиенты</th>
                      <th>Документы</th>
                      <th>Услуги</th>
                      <th>Выручка</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${
                      Array.isArray(report?.centers) && report.centers.length
                        ? report.centers
                            .map(
                              (center) => `
                                <tr>
                                  <td>${escapeHtml(center.center_name || "Без названия")}</td>
                                  <td>${escapeHtml(center.center_code || "")}</td>
                                  <td>${Number(center.clients_count || 0).toLocaleString("ru-RU")}</td>
                                  <td>${Number(center.documents_count || 0).toLocaleString("ru-RU")}</td>
                                  <td>${Number(center.services_count || 0).toLocaleString("ru-RU")}</td>
                                  <td>${Number(center.revenue || 0).toLocaleString("ru-RU")} ₽</td>
                                </tr>
                              `,
                            )
                            .join("")
                        : `<tr><td colspan="6" class="muted">За выбранный период данных по центрам пока нет.</td></tr>`
                    }
                  </tbody>
                </table>
              </div>
            </div>
          `
      }
    </section>
  `;
}

function renderDoctorsPage() {
  const templates = getDoctorTemplates();
  const roles = [
    ["Гинеколог", "gynecologist"],
    ["Стоматолог", "dentist"],
    ["Дерматолог", "dermatologist"],
    ["Невролог", "neurologist"],
    ["Хирург", "surgeon"],
    ["Отоларинголог", "otolaryngologist"],
    ["Офтальмолог", "ophthalmologist"],
    ["Терапевт", "therapist"],
    ["Психиатр", "psychiatrist"],
    ["Инфекционист", "infectionist"],
    ["Фтизиатр", "phthisiatrist"],
    ["Узист", "uzist"],
    ["Председатель", "chairman"],
  ];

  return `
    <section class="card">
      <h3>Врачи</h3>
      <p class="muted">Карточки врачей подключены. Чтобы открыть осмотр, вернись на главную, найди клиента и нажми нужного врача.</p>
      <div class="cards-grid">
        ${roles
          .map(([label, id]) => {
            const template = templates.find((item) => item.id === id);
            const doctorFullName = getDoctorFullName(id);
            return `
              <article class="mini-card">
                <strong>${label}</strong>
                <label class="doctor-card__field">
                  <span class="doctor-card__caption">ФИО врача</span>
                  <input
                    class="doctor-card__input"
                    type="text"
                    value="${escapeHtml(doctorFullName)}"
                    placeholder="Введите ФИО врача"
                    data-doctor-name-input="${escapeHtml(id)}"
                  />
                </label>
                <span>${template ? `Форма: ${escapeHtml(template.name)}` : "Форма пока не найдена"}</span>
                ${
                  template
                    ? `<button class="ghost-button" data-template-preview-role-id="${escapeHtml(id)}">Открыть форму</button>`
                    : `<button class="ghost-button" disabled>Формы нет</button>`
                }
              </article>
            `;
          })
          .join("")}
      </div>
    </section>
  `;
}

function renderVisitServicePicker(activeVisit) {
  const selectedSet = new Set(activeVisit?.serviceNames || []);
  const selectedIds = new Set(getSelectedVisitServiceIds(activeVisit));
  const serviceDetails = getVisitServiceDetails(activeVisit);
  const currentGroup = appState.visitServiceGroupFilter || "all";
  const search = String(appState.visitServiceSearch || "").trim().toLowerCase();
  const groups = getSortedServiceGroups();
  const visibleServices = getSortedServices()
    .filter((service) => currentGroup === "all" || String(service.groupId) === String(currentGroup))
    .filter((service) => {
      if (!search) return true;
      return [service.name, service.notes, service.price].join(" ").toLowerCase().includes(search);
    });
  const selectedDriverService = getSelectedVisitServiceIds(activeVisit)
    .map((id) => getServiceById(id))
    .find((service) => isDriverService(service));
  const selectedDriverId = selectedDriverService ? getServiceToken(selectedDriverService) : null;
  const driverDetail = selectedDriverId ? serviceDetails[selectedDriverId] || {} : {};
  const driverCategories = normalizeDriverCategories(driverDetail.categories || activeVisit?.admissionCategory || getSelectedClient()?.admissionCategory || getSelectedClient()?.category);
  const driverPrice = Number(driverDetail.unitPrice ?? (selectedDriverService ? getDriverCategoryPrice(driverCategories) : 0));

  return `
    <div class="operator-services">
      <div class="operator-services__top">
        <strong>Услуги в обращении</strong>
        <input id="visitServiceSearchInput" value="${escapeHtml(appState.visitServiceSearch || "")}" placeholder="найти услугу" />
      </div>

      <div class="operator-service-groups">
        <button class="${currentGroup === "all" ? "active" : ""}" data-visit-service-group="all">Все</button>
        ${groups
          .map(
            (group) => `
              <button class="${String(currentGroup) === String(group.id) ? "active" : ""}" data-visit-service-group="${group.id}">
                ${escapeHtml(group.name)}
              </button>
            `,
          )
          .join("")}
      </div>

      <div class="operator-service-list">
        ${
          visibleServices.length
            ? visibleServices
                .map(
                  (service) => `
                    <label class="${
                      selectedIds.has(getServiceToken(service)) || selectedSet.has(service.name)
                        ? "client-service-chip client-service-chip--active operator-service-chip"
                        : "client-service-chip operator-service-chip"
                    }">
                      <input
                        type="checkbox"
                        name="visitService"
                        value="${escapeHtml(getServiceToken(service))}"
                        data-service-name="${escapeHtml(service.name)}"
                        ${selectedIds.has(getServiceToken(service)) || selectedSet.has(service.name) ? "checked" : ""}
                      />
                      <span>${escapeHtml(service.name)}</span>
                      <strong>${Number(service.price || 0).toLocaleString("ru-RU")} ₽</strong>
                      ${
                        selectedIds.has(getServiceToken(service)) || selectedSet.has(service.name)
                          ? '<span class="client-service-chip__remove" aria-hidden="true">×</span>'
                          : ""
                      }
                    </label>
                  `,
                )
                .join("")
            : `<div class="muted">Услуги не найдены</div>`
        }
      </div>

      ${
        selectedDriverService
          ? `
            <div class="driver-category-panel">
              <div class="driver-category-panel__head">
                <strong>Категории водительской справки</strong>
                <span>по ним назначаются врачи и считается цена</span>
              </div>
              <div class="driver-category-grid">
                ${DRIVER_CATEGORY_OPTIONS.map(
                  (category) => `
                    <label class="driver-category-chip">
                      <input type="checkbox" name="driverCategory" value="${category}" ${driverCategories.includes(category) ? "checked" : ""} />
                      <span>${category}</span>
                    </label>
                  `,
                ).join("")}
              </div>
              <div class="driver-category-price">
                <label>
                  <span>Цена</span>
                  <input name="driverPrice" inputmode="numeric" value="${driverPrice}" />
                </label>
                <div>
                  <span>Назначатся</span>
                  <strong>${getDriverRoleCodes(driverCategories).map((code) => escapeHtml(getDoctorDisplayName(code))).join(", ")}</strong>
                </div>
              </div>
            </div>
          `
          : ""
      }
    </div>
  `;
}

function renderOperatorVisitForm(selectedClient, activeVisit) {
  return `
    <form class="operator-visit-form" id="operatorVisitForm" data-visit-id="${escapeHtml(activeVisit.id)}">
      <div class="operator-visit-form__title">
        <strong>Оформление обращения</strong>
        <span>оператор меняет услуги, оплату, сумму и комментарий прямо здесь</span>
      </div>

      <div class="encounter-grid">
        <label>
          <span>Дата</span>
          <input name="visitDate" value="${escapeHtml(activeVisit.visitDate || formatDateTime(activeVisit.createdAt))}" />
        </label>
        <label>
          <span>Центр</span>
          <input name="center" value="${escapeHtml(activeVisit.center || selectedClient.center || "Медцентр 1")}" />
        </label>
        <label>
          <span>Оплата</span>
          <select name="paymentType">
            ${["Наличные", "Карта", "Безнал", "Организация"]
              .map((item) => `<option ${item === activeVisit.paymentType ? "selected" : ""}>${item}</option>`)
              .join("")}
          </select>
        </label>
        <label>
          <span>Сумма</span>
          <input name="amount" inputmode="numeric" value="${Number(activeVisit.amount || 0)}" />
        </label>
      </div>

      ${renderVisitServicePicker(activeVisit)}

      <label class="operator-comment">
        <span>Комментарий</span>
        <textarea name="comment" rows="2" placeholder="например: уточнить категорию, организация, особенности оплаты">${escapeHtml(activeVisit.comment || "")}</textarea>
      </label>

      <div class="operator-visit-summary">
        <div>
          <span>Выбрано услуг</span>
          <strong>${(activeVisit.serviceNames || []).length}</strong>
        </div>
        <div>
          <span>Расчет по прайсу</span>
          <strong>${calculateVisitAmountByIds(getSelectedVisitServiceIds(activeVisit), getVisitServiceDetails(activeVisit)).toLocaleString("ru-RU")} ₽</strong>
        </div>
        <div>
          <span>Статус</span>
          <strong>${activeVisit.status === "closed" ? "Завершено" : "В работе"}</strong>
        </div>
      </div>

      <div class="operator-visit-actions">
        <button type="button" class="ghost-button" id="recalculateVisitAmountButton">Пересчитать сумму</button>
        <button type="submit" class="primary-button">Сохранить обращение</button>
        <button type="button" class="ghost-button" id="openVisitDocumentsButton">Документы</button>
        <button type="button" class="ghost-button" id="closeVisitButton">Завершить</button>
      </div>
    </form>
  `;
}

function renderVisitPanel(selectedClient) {
  if (!selectedClient) return "";

  const visits = getVisitsForClient(selectedClient.id);
  const activeVisit = getCurrentVisitForClient(selectedClient.id);

  return `
    <div class="encounter-panel">
      <div class="encounter-panel__head">
        <div>
          <strong>Обращение</strong>
          <span>${activeVisit ? escapeHtml(getVisitTitle(activeVisit)) : "для клиента пока не создано"}</span>
        </div>
        <button class="primary-button" id="createVisitButton">Новое обращение</button>
      </div>

      ${
        activeVisit
          ? `
            <div class="encounter-grid">
              <div><span>Дата</span><strong>${escapeHtml(activeVisit.visitDate || formatDateTime(activeVisit.createdAt))}</strong></div>
              <div><span>Центр</span><strong>${escapeHtml(activeVisit.center || selectedClient.center || "Медцентр 1")}</strong></div>
              <div><span>Оплата</span><strong>${escapeHtml(activeVisit.paymentType || "Наличные")}</strong></div>
              <div><span>Сумма</span><strong>${Number(activeVisit.amount || 0).toLocaleString("ru-RU")} ₽</strong></div>
            </div>
            <div class="encounter-services">
              ${(activeVisit.serviceNames || selectedClient.services || [])
                .map((service) => `<span>${escapeHtml(service)}</span>`)
                .join("") || "<span>Услуги не выбраны</span>"}
            </div>
            ${
              activeVisit.comment
                ? `<div class="muted" style="margin-top:8px;">${escapeHtml(activeVisit.comment)}</div>`
                : ""
            }
          `
          : `<p class="muted" style="margin:8px 0 0 0;">Создай обращение, чтобы привязать к нему услуги, врачей и документы.</p>`
      }

      ${
        visits.length > 1
          ? `
            <div class="encounter-history">
              <strong>История обращений</strong>
              ${visits
                .slice(0, 5)
                .map(
                  (visit) => `
                    <button class="${visit.id === activeVisit?.id ? "active" : ""}" data-select-visit-id="${escapeHtml(visit.id)}">
                      ${escapeHtml(visit.visitDate || formatDateTime(visit.createdAt))} · ${Number(visit.amount || 0).toLocaleString("ru-RU")} ₽
                    </button>
                  `,
                )
                .join("")}
            </div>
          `
          : ""
      }
    </div>
  `;
}

function renderTemplatesPage() {
  const doctorTemplates = getDoctorTemplates();
  const documentTemplates = Array.isArray(data.documentTemplates) ? data.documentTemplates : [];
  const canManageTemplates = ["admin", "chairman"].includes(appState.auth.roleCode);

  return `
    <section class="card">
      <h3>Шаблоны</h3>
      <div class="template-page-head">
        <p class="muted">${canManageTemplates ? "Файловые шаблоны можно посмотреть, заменить новым файлом и перечитать из папки." : "Файлы шаблонов скрыты от операторов. Для изменения шаблонов войдите как председатель или администратор."} Желтые ячейки с подписью “авто” заполняются системой.</p>
        ${canManageTemplates ? '<button class="primary-button" type="button" data-refresh-document-templates>Перечитать папку</button>' : ""}
      </div>
      ${data.templateOperationStatus ? `<div class="template-status">${escapeHtml(data.templateOperationStatus)}</div>` : ""}
      <div class="document-template-grid">
        ${
          documentTemplates.length
            ? documentTemplates
                .map(
                  (template) => `
                    <article class="document-template-card">
                      <div>
                        <strong>${escapeHtml(template.name || template.file_name || `Шаблон ${template.id}`)}</strong>
                        <span>${escapeHtml(template.file_name || "")}</span>
                      </div>
                      <small>${escapeHtml(template.template_type || "")}${template.requires_numbered_blank ? " · номерной бланк" : ""}</small>
                      ${
                        canManageTemplates
                          ? `<div class="document-template-card__actions">
                              <button class="ghost-button" type="button" data-open-document-template="${escapeHtml(template.id)}">Посмотреть</button>
                              <button class="ghost-button" type="button" data-replace-document-template="${escapeHtml(template.id)}">Обновить шаблон</button>
                            </div>`
                          : ""
                      }
                    </article>
                  `,
                )
                .join("")
            : `<div class="empty-state">Файловые шаблоны еще не загружены с backend.</div>`
        }
      </div>
      <input class="hidden" id="documentTemplateUploadInput" type="file" accept=".docx,.xml,.xls" />
    </section>

    <section class="card">
      <h3>Шаблоны врачей</h3>
      <p class="muted">Подключено шаблонов врачей: ${doctorTemplates.length}. Эти шаблоны используются при открытии карточки врача на главной.</p>
      <div class="cards-grid">
        ${doctorTemplates
          .map(
            (template) => `
              <article class="mini-card">
                <strong>${escapeHtml(template.name || template.id)}</strong>
                <span>Полей: ${Array.isArray(template.fields) ? template.fields.length : 0}</span>
              </article>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
}

function renderWorkflowLoadState() {
  if (data.workflowDataLoading) {
    return `<section class="card"><p class="muted">Загружаю карту, журналы и бланки из базы...</p></section>`;
  }
  if (data.workflowDataError) {
    return `<section class="card"><p class="muted">${escapeHtml(data.workflowDataError)}</p></section>`;
  }
  return "";
}

function normalizeSheetValue(value, fallback = "—") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function denormalizeSheetValue(value) {
  const text = String(value ?? "").trim();
  return text === "—" ? "" : text;
}

function splitFullName(value) {
  const parts = String(value || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  return {
    lastName: parts[0] || "",
    firstName: parts[1] || "",
    middleName: parts.slice(2).join(" ") || "",
  };
}

function splitClientDocumentParts(client) {
  const raw = client?.rawApiClient || {};
  const series = String(raw.document_series || "").trim();
  const number = String(raw.document_number || "").trim();
  const type = String(raw.document_type || "").trim();

  if (series || number || type) {
    return {
      type: type || "Паспорт РФ",
      series: series || "—",
      number: number || "—",
    };
  }

  const source = String(client?.document || "").trim();
  const digits = source.match(/\d+/g) || [];
  return {
    type: source.replace(/[\d\s]+/g, " ").trim() || "Паспорт РФ",
    series: digits.slice(0, 2).join(" ") || "—",
    number: digits.slice(2).join("") || "—",
  };
}

function splitOmsPolicy(value) {
  const digits = String(value || "").replace(/\D+/g, "");
  if (!digits) return { series: "—", number: "—" };
  if (digits.length <= 6) return { series: digits, number: "—" };
  return { series: digits.slice(0, 6), number: digits.slice(6) };
}

function splitClientAddressParts(client) {
  const raw = client?.rawApiClient || {};
  const source = String(raw.registration_text || raw.address_text || client?.registration || "").trim();
  const parts = source
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  const isCountryPart = (part) => /^(россия|рф|российская федерация)$/i.test(String(part || "").replace(/\./g, "").trim());
  const hasSubjectMarker = (part) => /обл\.?|область|край|респ\.?|республика|автоном|ао\b|округ|санкт-петербург|спб|москва|севастополь/i.test(part);
  const hasDistrictMarker = (part) => /район|р-н/i.test(part);
  const hasCityMarker = (part) => /(^|\s)(г\.|гор\.|город)\s*|санкт-петербург|спб|москва|севастополь/i.test(part);
  const hasStreetMarker = (part) => /(^|\s)(ул\.|улица|пр-?кт|просп\.?|проспект|пер\.|переулок|наб\.|шоссе|б-р|бул\.?|бульвар)\s*/i.test(part);
  const hasHouseMarker = (part) => /(^|\s)(д\.|дом)\s*/i.test(part);
  const hasBuildingMarker = (part) => /корпус|корп\.?|к\.\s*/i.test(part);
  const hasFlatMarker = (part) => /(^|\s)(кв\.|квартира)\s*/i.test(part);
  const stripMarker = (part, pattern) => String(part || "").replace(pattern, "").trim();

  let subjectPart = "";
  let districtPart = "";
  let cityPart = "";
  let streetPart = "";
  let housePart = "";
  let buildingPart = "";
  let flatPart = "";

  if (parts.length && isCountryPart(parts[0])) {
    subjectPart = parts[1] || "";
    districtPart = parts[2] || "";
    cityPart = parts[3] || "";
    streetPart = parts[4] || "";
    housePart = parts[5] || "";
    buildingPart = parts[6] || "";
    flatPart = parts[7] || "";
  } else {
    subjectPart = parts.find(hasSubjectMarker) || "";
    districtPart = parts.find(hasDistrictMarker) || "";
    cityPart = parts.find(hasCityMarker) || parts.find((part) => part && part !== subjectPart && part !== districtPart && !hasStreetMarker(part) && !hasHouseMarker(part)) || "";
    streetPart = parts.find(hasStreetMarker) || "";
    housePart = parts.find(hasHouseMarker) || "";
    buildingPart = parts.find(hasBuildingMarker) || "";
    flatPart = parts.find(hasFlatMarker) || "";
  }

  const houseFull = [housePart, buildingPart, flatPart]
    .map((part) => String(part || "").trim())
    .filter(Boolean)
    .join(", ");

  return {
    full: normalizeSheetValue(source),
    subject: normalizeSheetValue(subjectPart || "Российская Федерация"),
    district: normalizeSheetValue(districtPart),
    city: normalizeSheetValue(cityPart),
    locality: normalizeSheetValue(parts.find((part) => /пос\.|село|деревня|насел/i.test(part)) || cityPart),
    street: normalizeSheetValue(streetPart),
    house: normalizeSheetValue(
      stripMarker(houseFull, /(^|\s)(д\.|дом|корпус|корп\.?|к\.|кв\.|квартира)\s*/gi),
    ),
  };
}

function formatClientSexForSheet(client) {
  const raw = String(client?.rawApiClient?.sex || "").trim().toLowerCase();
  if (["m", "male", "м", "мужской"].includes(raw)) return "мужской";
  if (["f", "female", "ж", "женский"].includes(raw)) return "женский";
  return "—";
}

function formatMedicalRecordSexForApi(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) return null;
  if (["f", "female", "ж", "жен", "женский"].includes(raw)) return "F";
  if (["m", "male", "м", "муж", "мужской"].includes(raw)) return "M";
  return null;
}

function getMedicalRecordTextValue(formData, name) {
  const value = String(formData.get(name) || "").trim();
  return value || null;
}

function buildMedicalRecordDraft(selectedClient, record = {}, entries = []) {
  const raw = selectedClient?.rawApiClient || {};
  const documentParts = splitClientDocumentParts(selectedClient);
  const omsParts = splitOmsPolicy(record.oms_policy || raw.oms_policy || "");
  const address = splitClientAddressParts(selectedClient);
  const sourceEntries = buildAmbulatorySheetEntries(entries, getClientDoctorExamHistory(selectedClient?.id)).slice(0, 6);

  while (sourceEntries.length < 6) {
    sourceEntries.push({
      id: `draft-${sourceEntries.length}`,
      source: "draft",
      backendId: null,
      doctorRoleId: "",
      doctorName: "",
      entryDate: "",
      complaints: "",
      anamnesis: "",
      objective: "",
      diagnosis: "",
      mkb10: "",
      conclusion: "",
    });
  }

  return {
    fullName: selectedClient?.fullName || "",
    sex: denormalizeSheetValue(formatClientSexForSheet(selectedClient)),
    birthDate: selectedClient?.birthDate || "",
    phone: selectedClient?.phone || "",
    snils: selectedClient?.snils || "",
    openedAt: formatApiDate(record.opened_at) || "",
    cardNumber: record.card_number || selectedClient?.cardNumber || raw.card_number || "",
    addressSubject: denormalizeSheetValue(address.subject),
    addressDistrict: denormalizeSheetValue(address.district),
    addressCity: denormalizeSheetValue(address.city),
    addressLocality: denormalizeSheetValue(address.locality),
    addressStreet: denormalizeSheetValue(address.street),
    addressHouse: denormalizeSheetValue(address.house),
    omsPolicySeries: denormalizeSheetValue(omsParts.series),
    omsPolicyNumber: denormalizeSheetValue(omsParts.number),
    insuranceOrg: record.insurance_org || raw.legacy_payload_json?.insurance_org || "",
    documentType: denormalizeSheetValue(documentParts.type),
    documentSeries: denormalizeSheetValue(documentParts.series),
    documentNumber: denormalizeSheetValue(documentParts.number),
    dispensaryObservation: record.dispensary_observation || raw.indications || "",
    maritalStatus: record.marital_status || "",
    education: record.education || "",
    employmentStatus: record.employment_status || "",
    disability: record.disability || "",
    workPlace: record.work_place || raw.organization || "",
    position: record.position || "",
    diagnosis: record.diagnosis || raw.indications || selectedClient?.mkb10 || "",
    mkb10: record.mkb10 || raw.mkb10 || selectedClient?.mkb10 || "",
    bloodGroup: record.blood_group || "",
    rhFactor: record.rh_factor || "",
    allergies: record.allergies || "",
    healthGroup: record.health_group || "",
    recordNotes: record.notes || "",
    entries: sourceEntries.map((entry) => ({
      backendId: entry.source === "backend" ? entry.backendId : null,
      doctorRoleId: entry.doctorRoleId || "",
      doctorName: denormalizeSheetValue(entry.doctorName),
      entryDate: denormalizeSheetValue(entry.entryDate),
      complaints: denormalizeSheetValue(entry.complaints),
      anamnesis: denormalizeSheetValue(entry.anamnesis),
      objective: denormalizeSheetValue(entry.objective),
      diagnosis: denormalizeSheetValue(entry.diagnosis),
      mkb10: denormalizeSheetValue(entry.mkb10),
      conclusion: denormalizeSheetValue(entry.conclusion),
    })),
  };
}

function renderMedicalRecordControl(name, value, options = {}) {
  const normalizedValue = String(value ?? "");
  const placeholder = options.placeholder || "";
  const rows = options.rows || 3;
  const type = options.type || "text";
  const className = options.className ? ` ${options.className}` : "";

  if (!data.medicalRecordEditMode) {
    return options.multiline
      ? `<p>${escapeHtml(normalizeSheetValue(normalizedValue))}</p>`
      : `<strong>${escapeHtml(normalizeSheetValue(normalizedValue))}</strong>`;
  }

  if (options.multiline) {
    return `<textarea name="${escapeHtml(name)}" rows="${rows}" class="ambulatory-sheet__control ambulatory-sheet__control--textarea${className}" placeholder="${escapeHtml(placeholder)}">${escapeHtml(normalizedValue)}</textarea>`;
  }

  if (options.type === "select") {
    const choices = Array.isArray(options.choices) ? options.choices : [];
    return `
      <select name="${escapeHtml(name)}" class="ambulatory-sheet__control${className}">
        ${choices
          .map(
            (choice) => `
              <option value="${escapeHtml(choice.value)}" ${String(choice.value) === normalizedValue ? "selected" : ""}>
                ${escapeHtml(choice.label)}
              </option>
            `,
          )
          .join("")}
      </select>
    `;
  }

  return `<input name="${escapeHtml(name)}" type="${escapeHtml(type)}" class="ambulatory-sheet__control${className}" value="${escapeHtml(normalizedValue)}" placeholder="${escapeHtml(placeholder)}" ${options.dateMask ? "data-date-mask" : ""} />`;
}

function renderMedicalRecordTableCell(name, value, options = {}) {
  if (!data.medicalRecordEditMode) {
    return `<div>${escapeHtml(normalizeSheetValue(value))}</div>`;
  }
  return `
    <div class="ambulatory-sheet__table-cell-edit">
      ${renderMedicalRecordControl(name, value, { ...options, multiline: options.multiline })}
    </div>
  `;
}

function getExamFieldValue(exam, keys) {
  const fields = exam?.fields || {};
  return keys.map((key) => String(fields[key] || "").trim()).find(Boolean) || "";
}

function buildAmbulatorySheetEntries(entries, exams) {
  const backendEntries = (Array.isArray(entries) ? entries : []).map((entry) => ({
    id: `record-${entry.id}`,
    source: "backend",
    backendId: entry.id,
    doctorRoleId: entry.doctor_role_id || "",
    doctorName: entry.doctor_name || getDoctorDisplayName(entry.doctor_role_id) || "Врач",
    entryDate: formatApiDate(entry.entry_date) || "—",
    complaints: normalizeSheetValue(entry.complaints),
    anamnesis: normalizeSheetValue(entry.anamnesis),
    objective: normalizeSheetValue(entry.objective_data),
    diagnosis: normalizeSheetValue(entry.diagnosis),
    mkb10: normalizeSheetValue(entry.mkb10),
    conclusion: normalizeSheetValue(entry.conclusion),
  }));

  const knownBackendKeys = new Set(
    backendEntries.map((entry) => `${entry.doctorName}|${entry.entryDate}|${entry.diagnosis}`),
  );

  const localEntries = (Array.isArray(exams) ? exams : [])
    .filter((exam) => exam?.isCompleted)
    .map((exam) => ({
      id: exam.id,
      source: "exam",
      backendId: null,
      doctorRoleId: exam.doctorRoleId || "",
      doctorName: getDoctorDisplayName(exam.doctorRoleId) || "Врач",
      entryDate: formatApiDate(exam.updatedAt) || "—",
      complaints: normalizeSheetValue(getExamFieldValue(exam, ["complaints", "complaintsPreset"])),
      anamnesis: normalizeSheetValue(getExamFieldValue(exam, ["anamnesis", "epidAnamnesis", "allergyAnamnesis"])),
      objective: normalizeSheetValue(
        getExamFieldValue(exam, [
          "objective",
          "objectiveData",
          "state",
          "visualFields",
          "visualFieldsRight",
          "visualFieldsLeft",
          "ocularFundus",
          "studyName",
          "conclusion",
        ]),
      ),
      diagnosis: normalizeSheetValue(getExamFieldValue(exam, ["diagnosis"])),
      mkb10: normalizeSheetValue(getExamFieldValue(exam, ["mkb10"])),
      conclusion: normalizeSheetValue(getExamFieldValue(exam, ["conclusion", "recommendation", "note"])),
    }))
    .filter((entry) => !knownBackendKeys.has(`${entry.doctorName}|${entry.entryDate}|${entry.diagnosis}`));

  return [...backendEntries, ...localEntries];
}

function renderMedicalRecordBackendBlock(selectedClient, exams = []) {
  const record = data.medicalRecords?.[0] || {};
  if (!selectedClient && !Object.keys(record).length) {
    return `
      <article class="card">
        <h3>Медицинская карта 025/у</h3>
        <p class="muted">По выбранному клиенту пока нет данных для амбулаторной карты. После выбора пациента и загрузки данных здесь появится форма 025/у.</p>
      </article>
    `;
  }

  const draft = buildMedicalRecordDraft(selectedClient, record, data.medicalRecordEntries);
  const entries = buildAmbulatorySheetEntries(data.medicalRecordEntries, exams);
  const chairmanExam = getCompletedChairmanExam(exams);
  const chairmanMedicalRecordData = buildChairmanMedicalRecordData(chairmanExam?.fields || {});
  const primaryEntries = entries.slice(0, 3);
  const secondaryEntries = entries.slice(3, 6);
  const entriesHeight = getMedicalRecordPanelHeight();
  const cardNumber = draft.cardNumber;
  const openedAt = draft.openedAt;
  const diagnosis = chairmanMedicalRecordData.diagnosis || draft.diagnosis;
  const mkb10 = chairmanMedicalRecordData.mkb10 || draft.mkb10;
  const bloodGroup = chairmanMedicalRecordData.bloodGroup || draft.bloodGroup;
  const rhFactor = chairmanMedicalRecordData.rhFactor || draft.rhFactor;
  const jobLine = [draft.workPlace, draft.position].map((item) => String(item || "").trim()).filter(Boolean).join(", ");
  const clinicName = normalizeSheetValue(selectedClient?.center || "Медцентр");
  const clinicDetails = [
    selectedClient?.organization,
    selectedClient?.registration,
    selectedClient?.phone ? `тел. ${selectedClient.phone}` : "",
  ]
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .join(", ");
  const healthGroup = draft.healthGroup;
  const serviceDiagnosis = draft.dispensaryObservation || diagnosis;
  const chairmanName = normalizeSheetValue(selectedClient?.chairman || selectedClient?.therapist);
  const visibleEntries = data.medicalRecordEditMode ? draft.entries : entries;
  const memberNames = normalizeSheetValue(visibleEntries.map((entry) => entry.doctorName).slice(0, 4).join(", "));
  const commissionDate = (data.medicalRecordEditMode ? draft.entries : primaryEntries)[0]?.entryDate || openedAt;
  const commissionText =
    chairmanMedicalRecordData.recordNotes ||
    draft.recordNotes ||
    "В соответствии с постановлением Совета Министров - Правительства Российской Федерации медицинских противопоказаний не выявлено.";
  const stampStatus = (Array.isArray(exams) ? exams : []).some(
    (entry) => String(entry?.doctorRoleId || "") === "chairman" && entry?.isCompleted && entry?.fields?.stampApplied,
  )
    ? "Поставлена"
    : "Не указана";

  const renderDoctorEntryCards = (entryList, offset = 0) =>
    entryList.length
      ? entryList
          .map((entry, index) => {
            const entryIndex = offset + index;
            if (!data.medicalRecordEditMode) {
              return `
                <article class="ambulatory-entry" data-ambulatory-entry-id="${escapeHtml(entry.id)}">
                  <div class="ambulatory-entry__head">
                    <div class="ambulatory-entry__line"><span>Врач (специальность)</span><strong>${escapeHtml(entry.doctorName)}</strong></div>
                    <div class="ambulatory-entry__line"><span>Дата осмотра</span><strong>${escapeHtml(entry.entryDate)}</strong></div>
                  </div>
                  <div class="ambulatory-entry__row"><span>Жалобы пациента</span><p>${escapeHtml(entry.complaints)}</p></div>
                  <div class="ambulatory-entry__row"><span>Анамнез заболевания, жизни</span><p>${escapeHtml(entry.anamnesis)}</p></div>
                  <div class="ambulatory-entry__row"><span>Объективные данные</span><p>${escapeHtml(entry.objective)}</p></div>
                  <div class="ambulatory-entry__footer">
                    <div class="ambulatory-entry__line ambulatory-entry__line--wide"><span>Диагноз основного заболевания</span><strong>${escapeHtml(entry.diagnosis)}</strong></div>
                  </div>
                </article>
              `;
            }

            return `
              <article class="ambulatory-entry" data-ambulatory-entry-editor="${entryIndex}">
                <input type="hidden" name="entryBackendId_${entryIndex}" value="${escapeHtml(entry.backendId || "")}" />
                <input type="hidden" name="entryDoctorRoleId_${entryIndex}" value="${escapeHtml(entry.doctorRoleId || "")}" />
                <div class="ambulatory-entry__head">
                  <div class="ambulatory-entry__line">
                    <span>Врач (специальность)</span>
                    ${renderMedicalRecordControl(`entryDoctorName_${entryIndex}`, entry.doctorName, { placeholder: "Например, Терапевт" })}
                  </div>
                  <div class="ambulatory-entry__line">
                    <span>Дата осмотра</span>
                    ${renderMedicalRecordControl(`entryDate_${entryIndex}`, entry.entryDate, { dateMask: true, placeholder: "дд.мм.гггг" })}
                  </div>
                </div>
                <div class="ambulatory-entry__row">
                  <span>Жалобы пациента</span>
                  ${renderMedicalRecordControl(`entryComplaints_${entryIndex}`, entry.complaints, { multiline: true, rows: 3 })}
                </div>
                <div class="ambulatory-entry__row">
                  <span>Анамнез заболевания, жизни</span>
                  ${renderMedicalRecordControl(`entryAnamnesis_${entryIndex}`, entry.anamnesis, { multiline: true, rows: 3 })}
                </div>
                <div class="ambulatory-entry__row">
                  <span>Объективные данные</span>
                  ${renderMedicalRecordControl(`entryObjective_${entryIndex}`, entry.objective, { multiline: true, rows: 3 })}
                </div>
                <div class="ambulatory-entry__footer">
                  <div class="ambulatory-entry__line">
                    <span>Диагноз основного заболевания</span>
                    ${renderMedicalRecordControl(`entryDiagnosis_${entryIndex}`, entry.diagnosis)}
                  </div>
                  <div class="ambulatory-entry__line">
                    <span>Код по МКБ-10</span>
                    ${renderMedicalRecordControl(`entryMkb10_${entryIndex}`, entry.mkb10)}
                  </div>
                  <div class="ambulatory-entry__line ambulatory-entry__line--wide">
                    <span>Заключение / рекомендации</span>
                    ${renderMedicalRecordControl(`entryConclusion_${entryIndex}`, entry.conclusion, { multiline: true, rows: 2 })}
                  </div>
                </div>
              </article>
            `;
          })
          .join("")
      : `
          <article class="ambulatory-entry ambulatory-entry--blank">
            <div class="ambulatory-entry__head">
              <div class="ambulatory-entry__line"><span>Врач (специальность)</span><strong>-</strong></div>
              <div class="ambulatory-entry__line"><span>Дата осмотра</span><strong>-</strong></div>
            </div>
            <div class="ambulatory-entry__row"><span>Жалобы пациента</span><p>-</p></div>
            <div class="ambulatory-entry__row"><span>Анамнез заболевания, жизни</span><p>-</p></div>
            <div class="ambulatory-entry__row"><span>Объективные данные</span><p>-</p></div>
            <div class="ambulatory-entry__footer">
              <div class="ambulatory-entry__line ambulatory-entry__line--wide"><span>Диагноз основного заболевания</span><strong>-</strong></div>
            </div>
          </article>
        `;

  return `
    <form class="ambulatory-sheet card" id="ambulatoryCardForm">
      <div class="ambulatory-sheet__topline">
        <span>В соответствии с постановлением Совета Министров - Правительства Российской Федерации</span>
        <span>Код формы по ОКУД ________</span>
        <span>Учетная форма № 025/у</span>
      </div>

      <div class="ambulatory-sheet__toolbar">
        <div class="ambulatory-sheet__toolbar-text">
          <strong>Форма 025/у</strong>
          <span>${data.medicalRecordEditMode ? "Изменения сохраняются прямо в карту пациента." : "Данные подтягиваются из клиента, осмотров и медицинской карты."}</span>
        </div>
        <div class="chart-page__actions">
          ${
            data.medicalRecordEditMode
              ? `
                <button type="button" class="ghost-button" id="cancelMedicalRecordEditButton">Отмена</button>
                <button type="submit" class="primary-button" id="saveMedicalRecordButton">${data.medicalRecordSaving ? "Сохранение..." : "Сохранить"}</button>
              `
              : `<button type="button" class="primary-button" id="editMedicalRecordButton">Редактировать в карте</button>`
          }
        </div>
      </div>
      ${
        data.medicalRecordSaveError
          ? `<div class="empty" style="margin-top:12px;">${escapeHtml(data.medicalRecordSaveError)}</div>`
          : ""
      }

      <div class="ambulatory-sheet__header">
        <div class="ambulatory-sheet__clinic">
          <strong>${escapeHtml(clinicName)}</strong>
          <span>${escapeHtml(normalizeSheetValue(clinicDetails))}</span>
        </div>
        <div class="ambulatory-sheet__title">
          <div>МЕДИЦИНСКАЯ КАРТА</div>
          <div>ПАЦИЕНТА, ПОЛУЧАЮЩЕГО МЕДИЦИНСКУЮ ПОМОЩЬ</div>
          <div>
            В АМБУЛАТОРНЫХ УСЛОВИЯХ №
            ${
              data.medicalRecordEditMode
                ? renderMedicalRecordControl("cardNumber", cardNumber, { className: " ambulatory-sheet__control--inline" })
                : escapeHtml(normalizeSheetValue(cardNumber))
            }
          </div>
          <div class="ambulatory-sheet__subtitle">Утверждена приказом Минздрава России</div>
        </div>
      </div>

      <div class="ambulatory-sheet__grid">
        <div class="ambulatory-sheet__line ambulatory-sheet__line--wide"><span>1. Дата заполнения медицинской карты</span>${renderMedicalRecordControl("openedAt", openedAt, { dateMask: true, placeholder: "дд.мм.гггг" })}</div>
        <div class="ambulatory-sheet__line ambulatory-sheet__line--wide"><span>2. Фамилия, имя, отчество</span>${renderMedicalRecordControl("fullName", draft.fullName, { placeholder: "Фамилия Имя Отчество" })}</div>
        <div class="ambulatory-sheet__line"><span>3. Пол</span>${renderMedicalRecordControl("sex", draft.sex, { type: "select", choices: [{ value: "", label: "—" }, { value: "мужской", label: "мужской" }, { value: "женский", label: "женский" }] })}</div>
        <div class="ambulatory-sheet__line"><span>4. Дата рождения</span>${renderMedicalRecordControl("birthDate", draft.birthDate, { dateMask: true, placeholder: "дд.мм.гггг" })}</div>
        <div class="ambulatory-sheet__line ambulatory-sheet__line--wide"><span>5. Место регистрации: субъект Российской Федерации</span>${renderMedicalRecordControl("addressSubject", draft.addressSubject)}</div>
        <div class="ambulatory-sheet__line"><span>район</span>${renderMedicalRecordControl("addressDistrict", draft.addressDistrict)}</div>
        <div class="ambulatory-sheet__line"><span>город</span>${renderMedicalRecordControl("addressCity", draft.addressCity)}</div>
        <div class="ambulatory-sheet__line"><span>населенный пункт</span>${renderMedicalRecordControl("addressLocality", draft.addressLocality)}</div>
        <div class="ambulatory-sheet__line"><span>улица</span>${renderMedicalRecordControl("addressStreet", draft.addressStreet)}</div>
        <div class="ambulatory-sheet__line"><span>тел.</span>${renderMedicalRecordControl("phone", draft.phone)}</div>
        <div class="ambulatory-sheet__line ambulatory-sheet__line--wide"><span>дом / кв.</span>${renderMedicalRecordControl("addressHouse", draft.addressHouse)}</div>
        <div class="ambulatory-sheet__line"><span>6. Местность: городская - 1, сельская - 2</span><strong>1</strong></div>
        <div class="ambulatory-sheet__line"><span>7. Полис ОМС: серия</span>${renderMedicalRecordControl("omsPolicySeries", draft.omsPolicySeries)}</div>
        <div class="ambulatory-sheet__line"><span>№</span>${renderMedicalRecordControl("omsPolicyNumber", draft.omsPolicyNumber)}</div>
        <div class="ambulatory-sheet__line"><span>8. СНИЛС</span>${renderMedicalRecordControl("snils", draft.snils)}</div>
        <div class="ambulatory-sheet__line ambulatory-sheet__line--wide"><span>9. Наименование страховой медицинской организации</span>${renderMedicalRecordControl("insuranceOrg", draft.insuranceOrg)}</div>
        <div class="ambulatory-sheet__line"><span>10. Код категории льготы</span><strong>-</strong></div>
        <div class="ambulatory-sheet__line"><span>11. Документ</span>${renderMedicalRecordControl("documentType", draft.documentType)}</div>
        <div class="ambulatory-sheet__line"><span>серия</span>${renderMedicalRecordControl("documentSeries", draft.documentSeries)}</div>
        <div class="ambulatory-sheet__line"><span>№</span>${renderMedicalRecordControl("documentNumber", draft.documentNumber)}</div>
      </div>

      <div class="ambulatory-sheet__section">
        <div class="ambulatory-sheet__section-title">12. Заболевания, по поводу которых осуществляется диспансерное наблюдение</div>
        <div class="ambulatory-sheet__table ambulatory-sheet__table--dispensary">
          <div>Дата начала диспансерного наблюдения</div>
          <div>Дата прекращения диспансерного наблюдения</div>
          <div>Диагноз</div>
          <div>Код по МКБ-10</div>
          <div>Врач</div>
          ${renderMedicalRecordTableCell("dispensaryStartAt", draft.dispensaryObservation ? openedAt : "", { dateMask: true })}
          ${renderMedicalRecordTableCell("dispensaryEndAt", "")}
          ${renderMedicalRecordTableCell("dispensaryObservation", serviceDiagnosis)}
          ${renderMedicalRecordTableCell("mkb10", mkb10)}
          <div>${escapeHtml(normalizeSheetValue(selectedClient?.therapist || "Терапевт"))}</div>
        </div>
      </div>

      <div class="ambulatory-sheet__grid ambulatory-sheet__grid--compact">
        <div class="ambulatory-sheet__line ambulatory-sheet__line--wide"><span>13. Семейное положение</span>${renderMedicalRecordControl("maritalStatus", draft.maritalStatus)}</div>
        <div class="ambulatory-sheet__line"><span>14. Образование</span>${renderMedicalRecordControl("education", draft.education)}</div>
        <div class="ambulatory-sheet__line"><span>15. Занятость</span>${renderMedicalRecordControl("employmentStatus", draft.employmentStatus)}</div>
        <div class="ambulatory-sheet__line ambulatory-sheet__line--wide"><span>16. Инвалидность (первичная, повторная, группа, дата)</span>${renderMedicalRecordControl("disability", draft.disability)}</div>
        <div class="ambulatory-sheet__line"><span>17. Место работы</span>${renderMedicalRecordControl("workPlace", draft.workPlace)}</div>
        <div class="ambulatory-sheet__line"><span>Должность</span>${renderMedicalRecordControl("position", draft.position)}</div>
        <div class="ambulatory-sheet__line"><span>18. Изменение места работы</span><strong>-</strong></div>
        <div class="ambulatory-sheet__line"><span>19. Изменение места регистрации</span><strong>-</strong></div>
      </div>

      <div class="ambulatory-sheet__section">
        <div class="ambulatory-sheet__section-title">20. Лист записи заключительных (уточненных) диагнозов</div>
        <div class="ambulatory-sheet__table ambulatory-sheet__table--diagnosis">
          <div>Дата (число, месяц, год)</div>
          <div>Заключительные (уточненные) диагнозы</div>
          <div>Установленные впервые или повторно</div>
          <div>Врач</div>
          ${renderMedicalRecordTableCell("openedAtDiagnosis", openedAt, { dateMask: true })}
          ${renderMedicalRecordTableCell("diagnosis", diagnosis)}
          <div>установлен</div>
          <div>${escapeHtml(normalizeSheetValue(selectedClient?.therapist || "Терапевт"))}</div>
        </div>
      </div>

      <div class="ambulatory-sheet__grid ambulatory-sheet__grid--compact">
        <div class="ambulatory-sheet__line"><span>21. Группа крови</span>${renderMedicalRecordControl("bloodGroup", bloodGroup)}</div>
        <div class="ambulatory-sheet__line"><span>22. Rh-фактор</span>${renderMedicalRecordControl("rhFactor", rhFactor)}</div>
        <div class="ambulatory-sheet__line ambulatory-sheet__line--wide"><span>23. Аллергические реакции</span>${renderMedicalRecordControl("allergies", draft.allergies, { multiline: true, rows: 2 })}</div>
      </div>

      <div class="ambulatory-sheet__section">
        <div class="ambulatory-sheet__single-field"><span>Диагноз основного заболевания</span>${renderMedicalRecordControl("diagnosisMain", diagnosis, { multiline: data.medicalRecordEditMode, rows: 2 })}</div>
      </div>

      <div class="ambulatory-sheet__factors">
        <div class="ambulatory-sheet__factors-head">Осложнения</div>
        <div class="ambulatory-sheet__factors-head">Сопутствующие заболевания</div>
        <div class="ambulatory-sheet__factors-head">Код по МКБ-10</div>
        <div class="ambulatory-sheet__factors-head">Внешняя причина при травмах (отравлениях)</div>
        <div class="ambulatory-sheet__factors-head">Группа здоровья / диспансерное наблюдение</div>
        <div>-</div>
        <div>-</div>
        <div>${data.medicalRecordEditMode ? renderMedicalRecordControl("mkb10Factors", mkb10) : escapeHtml(normalizeSheetValue(mkb10))}</div>
        <div>-</div>
        <div>${data.medicalRecordEditMode ? renderMedicalRecordControl("healthGroup", healthGroup) : escapeHtml(normalizeSheetValue(healthGroup))}</div>
      </div>

      <div class="ambulatory-sheet__section">
        <div class="ambulatory-sheet__section-title">24. Записи врачей-специалистов</div>
        <div class="ambulatory-sheet__entries" data-medical-record-panel style="height:${entriesHeight}px;">
          ${renderDoctorEntryCards(data.medicalRecordEditMode ? draft.entries.slice(0, 3) : primaryEntries, 0)}
        </div>
        <button type="button" class="chart-record-resizer" data-medical-record-resize aria-label="Изменить высоту блока записей врачей"></button>
      </div>

      <div class="ambulatory-sheet__factors ambulatory-sheet__factors--secondary">
        <div class="ambulatory-sheet__factors-head">Осложнения</div>
        <div class="ambulatory-sheet__factors-head">Сопутствующие заболевания</div>
        <div class="ambulatory-sheet__factors-head">Код по МКБ-10</div>
        <div class="ambulatory-sheet__factors-head">Внешняя причина при травмах (отравлениях)</div>
        <div class="ambulatory-sheet__factors-head">Группа здоровья / диспансерное наблюдение</div>
        <div>-</div>
        <div>-</div>
        <div>${data.medicalRecordEditMode ? renderMedicalRecordControl("mkb10Secondary", mkb10) : escapeHtml(normalizeSheetValue(mkb10))}</div>
        <div>-</div>
        <div>${data.medicalRecordEditMode ? renderMedicalRecordControl("healthGroupSecondary", healthGroup) : escapeHtml(normalizeSheetValue(healthGroup))}</div>
      </div>

      <div class="ambulatory-sheet__section">
        <div class="ambulatory-sheet__section-title">28. Заключение врачебной комиссии</div>
        <div class="ambulatory-sheet__commission">
          <div class="ambulatory-sheet__commission-grid">
            <div class="ambulatory-sheet__line"><span>Врач</span><strong>${escapeHtml(chairmanName)}</strong></div>
            <div class="ambulatory-sheet__line"><span>Дата</span><strong>${escapeHtml(commissionDate)}</strong></div>
          </div>
          <div class="ambulatory-sheet__line ambulatory-sheet__line--wide"><span>Проведенное обследование и лечение</span>${renderMedicalRecordControl("recordNotes", chairmanMedicalRecordData.recordNotes || draft.recordNotes, { multiline: true, rows: 3 })}</div>
          <div class="ambulatory-sheet__commission-grid ambulatory-sheet__commission-grid--triple">
            <div class="ambulatory-sheet__line"><span>Флюорография</span><strong>-</strong></div>
            <div class="ambulatory-sheet__line"><span>Диагноз основного заболевания</span>${renderMedicalRecordControl("diagnosisCommission", diagnosis)}</div>
            <div class="ambulatory-sheet__line"><span>Код по МКБ-10</span>${renderMedicalRecordControl("mkb10Commission", mkb10)}</div>
          </div>
          <div class="ambulatory-sheet__footer-note">${escapeHtml(commissionText)}</div>
          <div class="ambulatory-sheet__signature-table">
            <div class="ambulatory-sheet__signature-label">Председатель</div>
            <div class="ambulatory-sheet__signature-sign">(подпись)</div>
            <div class="ambulatory-sheet__signature-name">${escapeHtml(chairmanName)}</div>
            <div class="ambulatory-sheet__signature-label">Члены комиссии</div>
            <div class="ambulatory-sheet__signature-sign">(подпись)</div>
            <div class="ambulatory-sheet__signature-name">${escapeHtml(memberNames)}</div>
          </div>
          <div class="ambulatory-sheet__stamp-line"><span>Печать</span><strong>${escapeHtml(stampStatus)}</strong></div>
        </div>
      </div>

      <div class="ambulatory-sheet__section">
        <div class="ambulatory-sheet__section-title">24. Записи врачей-специалистов</div>
        <div class="ambulatory-sheet__entries ambulatory-sheet__entries--secondary">
          ${renderDoctorEntryCards(data.medicalRecordEditMode ? draft.entries.slice(3, 6) : secondaryEntries, 3)}
        </div>
      </div>
    </form>
  `;
}

async function saveMedicalRecordForm() {
  if (!data.medicalRecordEditMode) return;

  const selectedClient = getSelectedClient();
  const raw = selectedClient?.rawApiClient || {};
  const backendClientId = raw.id || selectedClient?.backendId || selectedClient?.id;
  const form = document.getElementById("ambulatoryCardForm");
  if (!selectedClient || !backendClientId || !form || !window.apiRequest) {
    data.medicalRecordSaveError = "Не удалось определить пациента для сохранения карты";
    renderApp();
    return;
  }

  const formData = new FormData(form);
  const pickValue = (...names) =>
    names.map((name) => getMedicalRecordTextValue(formData, name)).find((value) => value !== null) || null;
  const fullName = splitFullName(formData.get("fullName"));
  const addressText = [
    formData.get("addressSubject"),
    formData.get("addressDistrict"),
    formData.get("addressCity"),
    formData.get("addressLocality"),
    formData.get("addressStreet"),
    formData.get("addressHouse"),
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean)
    .join(", ");
  const omsPolicy = [formData.get("omsPolicySeries"), formData.get("omsPolicyNumber")]
    .map((value) => String(value || "").trim())
    .filter(Boolean)
    .join(" ");

  const saveButton = document.getElementById("saveMedicalRecordButton");
  if (saveButton) {
    saveButton.disabled = true;
    saveButton.textContent = "Сохранение...";
  }

  try {
    const savedClient = await apiRequest(`/clients/${encodeURIComponent(backendClientId)}`, {
      method: "PUT",
      body: JSON.stringify({
        last_name: fullName.lastName || raw.last_name || "Без фамилии",
        first_name: fullName.firstName || raw.first_name || "Без имени",
        middle_name: fullName.middleName || raw.middle_name || null,
        birth_date: parseRuDateToIso(formData.get("birthDate")) || raw.birth_date || "1900-01-01",
        sex: formatMedicalRecordSexForApi(formData.get("sex")) ?? raw.sex ?? null,
        phone: getMedicalRecordTextValue(formData, "phone"),
        email: raw.email || null,
        document_type: getMedicalRecordTextValue(formData, "documentType"),
        document_series: getMedicalRecordTextValue(formData, "documentSeries"),
        document_number: getMedicalRecordTextValue(formData, "documentNumber"),
        document_issued_by: raw.document_issued_by || null,
        document_issued_date: raw.document_issued_date || null,
        snils: getMedicalRecordTextValue(formData, "snils"),
        oms_policy: omsPolicy || null,
        address_text: addressText || null,
        notes: raw.notes || selectedClient.note || null,
        registration_text: addressText || null,
        admission_category: raw.admission_category || null,
        reference_number: raw.reference_number || selectedClient.referenceNumber || null,
        doctor_gynecologist: raw.doctor_gynecologist || null,
        doctor_stomatologist: raw.doctor_stomatologist || null,
        doctor_dermatologist: raw.doctor_dermatologist || null,
        doctor_neurologist: raw.doctor_neurologist || null,
        doctor_surgeon: raw.doctor_surgeon || null,
        doctor_otolaryngologist: raw.doctor_otolaryngologist || null,
        doctor_ophthalmologist: raw.doctor_ophthalmologist || null,
        doctor_therapist: raw.doctor_therapist || null,
        doctor_psychiatrist: raw.doctor_psychiatrist || null,
        doctor_infectionist: raw.doctor_infectionist || null,
        doctor_phthisiatrician: raw.doctor_phthisiatrician || null,
        doctor_uzist: raw.doctor_uzist || null,
        indications: pickValue("dispensaryObservation", "diagnosisMain", "diagnosis"),
        encounter_date_text: raw.encounter_date_text || null,
        card_number: getMedicalRecordTextValue(formData, "cardNumber"),
        journal_number: raw.journal_number || null,
        no_number: raw.no_number || null,
        flg: raw.flg || null,
        profession: getMedicalRecordTextValue(formData, "position"),
        work_place: getMedicalRecordTextValue(formData, "workPlace"),
        organization: raw.organization || null,
        mkb10: pickValue("mkb10", "mkb10Factors", "mkb10Commission"),
        real_date_text: raw.real_date_text || null,
        legacy_payload_json: raw.legacy_payload_json || null,
      }),
    });

    const mappedClient = savedClient ? upsertClientInMemory(savedClient) : selectedClient;
    const currentRecord = data.medicalRecords?.[0];
    const medicalRecordPayload = {
      client_id: backendClientId,
      center_id: currentRecord?.center_id ?? null,
      card_number: getMedicalRecordTextValue(formData, "cardNumber"),
      opened_at: parseRuDateToIso(formData.get("openedAt"), "") || null,
      insurance_org: getMedicalRecordTextValue(formData, "insuranceOrg"),
      oms_policy: omsPolicy || null,
      marital_status: getMedicalRecordTextValue(formData, "maritalStatus"),
      education: getMedicalRecordTextValue(formData, "education"),
      employment_status: getMedicalRecordTextValue(formData, "employmentStatus"),
      work_place: getMedicalRecordTextValue(formData, "workPlace"),
      position: getMedicalRecordTextValue(formData, "position"),
      disability: getMedicalRecordTextValue(formData, "disability"),
      blood_group: getMedicalRecordTextValue(formData, "bloodGroup"),
      rh_factor: getMedicalRecordTextValue(formData, "rhFactor"),
      allergies: getMedicalRecordTextValue(formData, "allergies"),
      dispensary_observation: pickValue("dispensaryObservation", "diagnosisMain", "diagnosis"),
      health_group: pickValue("healthGroup", "healthGroupSecondary"),
      diagnosis: pickValue("diagnosisMain", "diagnosisCommission", "diagnosis"),
      mkb10: pickValue("mkb10", "mkb10Factors", "mkb10Commission"),
      notes: getMedicalRecordTextValue(formData, "recordNotes"),
    };

    const savedRecord = await apiRequest(
      currentRecord?.id ? `/medical-records/${encodeURIComponent(currentRecord.id)}` : "/medical-records",
      {
        method: currentRecord?.id ? "PUT" : "POST",
        body: JSON.stringify(medicalRecordPayload),
      },
    );

    const entryRequests = [];
    for (let index = 0; index < 6; index += 1) {
      const doctorName = getMedicalRecordTextValue(formData, `entryDoctorName_${index}`);
      const entryDateValue = String(formData.get(`entryDate_${index}`) || "").trim();
      const complaints = getMedicalRecordTextValue(formData, `entryComplaints_${index}`);
      const anamnesis = getMedicalRecordTextValue(formData, `entryAnamnesis_${index}`);
      const objectiveData = getMedicalRecordTextValue(formData, `entryObjective_${index}`);
      const diagnosis = getMedicalRecordTextValue(formData, `entryDiagnosis_${index}`);
      const mkb10 = getMedicalRecordTextValue(formData, `entryMkb10_${index}`);
      const conclusion = getMedicalRecordTextValue(formData, `entryConclusion_${index}`);
      const doctorRoleId = getMedicalRecordTextValue(formData, `entryDoctorRoleId_${index}`);
      const backendEntryId = getMedicalRecordTextValue(formData, `entryBackendId_${index}`);
      const hasContent = [doctorName, entryDateValue, complaints, anamnesis, objectiveData, diagnosis, mkb10, conclusion].some(Boolean);
      if (!hasContent) continue;

      const payload = {
        medical_record_id: savedRecord.id,
        encounter_id: null,
        doctor_exam_id: null,
        entry_date: parseRuDateToIso(entryDateValue, "") || null,
        doctor_role_id: doctorRoleId,
        doctor_name: doctorName,
        complaints,
        anamnesis,
        objective_data: objectiveData,
        diagnosis,
        mkb10,
        recommendations: conclusion,
        conclusion,
      };

      entryRequests.push(
        apiRequest(
          backendEntryId ? `/medical-records/entries/${encodeURIComponent(backendEntryId)}` : "/medical-records/entries",
          {
            method: backendEntryId ? "PUT" : "POST",
            body: JSON.stringify(payload),
          },
        ),
      );
    }

    if (entryRequests.length) {
      await Promise.all(entryRequests);
    }

    data.medicalRecordEditMode = false;
    data.medicalRecordSaveError = "";
    await loadClientWorkspace(mappedClient || selectedClient);
    renderApp();
    showToast("Амбулаторная карта обновлена");
  } catch (error) {
    data.medicalRecordSaveError = humanizeApiError(error, "Не удалось сохранить амбулаторную карту");
    renderApp();
  } finally {
    if (saveButton) {
      saveButton.disabled = false;
      saveButton.textContent = "Сохранить";
    }
  }
}

async function openAmbulatoryCardForCurrentClient() {
  const selectedClient = getSelectedClient();
  appState.page = "chart";
  persistDemoState();
  renderApp();

  if (selectedClient) {
    await loadClientWorkspace(selectedClient);
  } else if (!data.workflowDataLoading) {
    await loadWorkflowData();
  }

  window.scrollTo({ top: 0, behavior: "auto" });
}

function renderGeneratedDocumentsTable(items = data.generatedDocuments) {
  const documents = Array.isArray(items) ? items : [];
  return `
    <article class="card">
      <h3>Выданные документы</h3>
      ${
        documents.length
          ? `
            <div class="chart-list">
              ${documents
                .map(
                  (item) => `
                    <div class="chart-list__row">
                      <div>
                        <strong>${escapeHtml(item.title || item.fileName || "Документ")}</strong>
                        <small>${escapeHtml(formatDateTime(item.createdAt))}</small>
                        <small>${escapeHtml([item.series, item.number].filter(Boolean).join(" ") || item.fileName || "")}</small>
                        ${item.blankNumber ? `<small class="blank-badge">№ бланка: ${escapeHtml(item.blankNumber)}</small>` : ""}
                      </div>
                      <button class="ghost-button" data-open-document-id="${escapeHtml(item.id)}">Открыть</button>
                    </div>
                  `,
                )
                .join("")}
            </div>
          `
          : `<p class="muted">Пока нет документов, выданных через backend. Сформируй договор, справку или XML по обращению.</p>`
      }
    </article>
  `;
}

function renderDocumentJournalsTable() {
  const journals = Array.isArray(data.documentJournals) ? data.documentJournals : [];
  return `
    <article class="card">
      <h3>Журналы выдачи</h3>
      ${
        journals.length
          ? `
            <div class="chart-list">
              ${journals
                .map(
                  (item) => `
                    <div class="chart-list__row">
                      <div>
                        <strong>${escapeHtml(item.journal_name || item.journal_code)}</strong>
                        <small>${escapeHtml(formatApiDate(item.issued_at))}</small>
                        <small>${escapeHtml([item.series, item.number].filter(Boolean).join(" ") || item.result_text || "")}</small>
                      </div>
                      <span class="calendar-status calendar-status--planned">${escapeHtml(item.journal_code)}</span>
                    </div>
                  `,
                )
                .join("")}
            </div>
          `
          : `<p class="muted">Записей в журналах пока нет. Для водительской справки после генерации создается запись в журнале 344.</p>`
      }
    </article>
  `;
}

function renderSpoiledBlanksTable() {
  const blanks = Array.isArray(data.spoiledBlanks) ? data.spoiledBlanks : [];
  return `
    <article class="card">
      <h3>Испорченные бланки</h3>
      ${
        blanks.length
          ? `
            <div class="chart-list">
              ${blanks
                .map(
                  (item) => `
                    <div class="chart-list__row">
                      <div>
                        <strong>${escapeHtml([item.series, item.number].filter(Boolean).join(" ") || item.number)}</strong>
                        <small>${escapeHtml(formatApiDate(item.spoiled_at))}</small>
                        <small>${escapeHtml(item.reason || "Причина не указана")}</small>
                      </div>
                    </div>
                  `,
                )
                .join("")}
            </div>
          `
          : `<p class="muted">Испорченных бланков пока нет.</p>`
      }
    </article>
  `;
}

function renderPatientConsentsTable() {
  const consents = Array.isArray(data.patientConsents) ? data.patientConsents : [];
  return `
    <article class="card">
      <h3>Согласия пациента</h3>
      ${
        consents.length
          ? `
            <div class="chart-list">
              ${consents
                .map(
                  (item) => `
                    <div class="chart-list__row">
                      <div>
                        <strong>${escapeHtml(item.title || item.consent_type)}</strong>
                        <small>${escapeHtml(formatApiDate(item.signed_at))}</small>
                        ${item.representative_name ? `<small>${escapeHtml(item.representative_name)}</small>` : ""}
                      </div>
                    </div>
                  `,
                )
                .join("")}
            </div>
          `
          : `<p class="muted">Согласий пока нет. Таблица уже есть в базе, интерфейс покажет историю, когда документы начнут сохраняться как согласия.</p>`
      }
    </article>
  `;
}

function renderBlanksPage() {
  if (typeof window.renderBlanksPage === "function") {
    return window.renderBlanksPage();
  }
  return `
    <section class="card">
      <h3>Учёт номерных бланков</h3>
      <p class="muted">Загрузка модуля бланков...</p>
    </section>
  `;
}

function renderDocumentsPageLegacy() {
  const selectedClient = getSelectedClient();
  const activeVisit = selectedClient ? getCurrentVisitForClient(selectedClient.id) : null;
  const visitDocuments = activeVisit ? getDocumentsForVisit(activeVisit.id) : [];

  return `
    ${renderBlanksPage()}
    <section class="card">
      <h3>Документы по обращению</h3>
      ${
        selectedClient && activeVisit
          ? `
            <p class="muted">Клиент: ${escapeHtml(selectedClient.fullName)}. ${escapeHtml(getVisitTitle(activeVisit))}</p>
            <div class="document-actions">
              <button class="primary-button" data-generate-document="contract">Договор</button>
              <button class="primary-button" data-generate-document="medical">Медицинская справка</button>
              <button class="ghost-button" data-generate-document="driver">Водительская справка</button>
              <button class="ghost-button" data-generate-document="xml">XML-заготовка</button>
            </div>
          `
          : `<p class="muted">Сначала на главной найди клиента и создай обращение. После этого здесь появится генерация документов по выбранному обращению.</p>`
      }
    </section>
  `;
}

function buildDemoDocumentLegacy(type) {
  const client = getSelectedClient();
  const visit = client ? getCurrentVisitForClient(client.id) : null;
  if (!client || !visit) return "";

  const services = (visit.serviceNames || client.services || []).join(", ") || "услуги не выбраны";
  const amount = Number(visit.amount || 0).toLocaleString("ru-RU");

  if (type === "xml") {
    return `<Visit><Client>${escapeHtml(client.fullName)}</Client><BirthDate>${escapeHtml(client.birthDate)}</BirthDate><Date>${escapeHtml(visit.visitDate)}</Date><Services>${escapeHtml(services)}</Services><Amount>${amount}</Amount></Visit>`;
  }

  const title = type === "driver" ? "Водительская справка" : "Медицинская справка";
  return [
    title,
    "",
    `Клиент: ${client.fullName}`,
    `Дата рождения: ${client.birthDate}`,
    `Документ: ${client.document}`,
    `Обращение: ${visit.visitDate}`,
    `Услуги: ${services}`,
    `Сумма: ${amount} ₽`,
    "",
    "Это демо-предпросмотр. Реальная DOCX/XML-генерация будет выполняться backend-модулем документов.",
  ].join("\n");
}

function openDemoDocumentLegacy(type) {
  const content = buildDemoDocument(type);
  if (!content) {
    showToast("Сначала выбери клиента и обращение");
    return;
  }

  openActionModal(
    "Предпросмотр документа",
    `
      <pre class="document-preview">${escapeHtml(content)}</pre>
      <div class="client-create-actions">
        <button type="button" class="primary-button" id="closeDocumentPreview">ОК</button>
      </div>
    `,
  );

  document.getElementById("closeDocumentPreview")?.addEventListener("click", () => {
    actionModal.classList.add("hidden");
  });
}

function buildDemoDocument(type) {
  const client = getSelectedClient();
  const visit = client ? getCurrentVisitForClient(client.id) : null;
  if (!client || !visit) return "";

  const services = (visit.serviceNames || client.services || []).join(", ") || "услуги не выбраны";
  const amount = Number(visit.amount || 0).toLocaleString("ru-RU");
  const comment = visit.comment ? `Комментарий: ${visit.comment}` : "Комментарий: не указан";

  if (type === "xml") {
    return [
      `<?xml version="1.0" encoding="UTF-8"?>`,
      `<Visit>`,
      `  <Client>${escapeHtml(client.fullName)}</Client>`,
      `  <PatientNumber>${escapeHtml(client.patientNumber ?? client.id)}</PatientNumber>`,
      `  <BirthDate>${escapeHtml(client.birthDate)}</BirthDate>`,
      `  <Document>${escapeHtml(client.document)}</Document>`,
      `  <VisitDate>${escapeHtml(visit.visitDate)}</VisitDate>`,
      `  <Center>${escapeHtml(visit.center || client.center || "")}</Center>`,
      `  <PaymentType>${escapeHtml(visit.paymentType || "")}</PaymentType>`,
      `  <Services>${escapeHtml(services)}</Services>`,
      `  <Amount>${amount}</Amount>`,
      `  <Comment>${escapeHtml(visit.comment || "")}</Comment>`,
      `</Visit>`,
    ].join("\n");
  }

  const title = getDocumentTitle(type).toUpperCase();
  return [
    title,
    "",
    `Пациент: ${client.fullName}`,
    `Дата рождения: ${client.birthDate}`,
    `Телефон: ${client.phone || "не указан"}`,
    `Документ: ${client.document || "не указан"}`,
    `СНИЛС: ${client.snils || "не указан"}`,
    "",
    `Обращение: ${visit.visitDate}`,
    `Центр: ${visit.center || client.center || "не указан"}`,
    `Услуги: ${services}`,
    `Оплата: ${visit.paymentType || "не указана"}`,
    `Сумма: ${amount} ₽`,
    comment,
    "",
    "Заключение: по результатам оформления данные подготовлены для печатной формы.",
    "",
    "М.П.                         Подпись __________________",
  ].join("\n");
}

function getDocumentTitle(type) {
  if (type === "contract") return "Договор на оказание платных медицинских услуг";
  if (type === "driver") return "Водительская справка";
  if (type === "xml") return "XML-файл по обращению";
  if (type === "prof") return "Заключение 29Н";
  if (type === "prof_extract") return "Выписка профосмотра";
  return "Медицинская справка";
}

function getDocumentsForVisit(visitId) {
  ensureVisitsStore();
  const visit = data.visits.find((item) => String(item.id) === String(visitId));
  const encounterId = visit?.backendId ? String(visit.backendId) : null;
  const localDocuments = (data.documents || [])
    .filter((documentItem) => String(documentItem.visitId) === String(visitId))
    .map((documentItem) => ({ ...documentItem, __source: "local" }));
  const backendDocuments = encounterId
    ? (data.generatedDocuments || [])
        .filter((documentItem) => String(documentItem.encounterId || "") === encounterId)
        .map((documentItem) => ({ ...documentItem, __source: "backend" }))
    : [];
  const seen = new Set();

  return [...backendDocuments, ...localDocuments]
    .filter((documentItem) => {
      const key = documentItem.backendId ? `backend-${documentItem.backendId}` : `local-${documentItem.id}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => new Date(b.createdAt || 0) - new Date(a.createdAt || 0));
}

function pickDocumentTemplate(type, visit = null, client = null) {
  const templates = Array.isArray(data.documentTemplates) ? data.documentTemplates : [];
  if (!templates.length) return null;

  const normalizedType = String(type || "").toLowerCase();
  const serviceText = (visit?.serviceNames || []).join(" ").toLowerCase();
  const usableTemplates = templates.filter((template) => !String(template.file_name || template.name || "").includes("_5.docx"));
  const getTemplateFieldTexts = (template) =>
    [template.name, template.code, template.file_name, repairDemoText(template.name || ""), repairDemoText(template.code || ""), repairDemoText(template.file_name || "")]
      .map((value) => String(value || "").toLowerCase())
      .filter(Boolean);
  const normalizeTemplateKey = (value) =>
    String(value || "")
      .toLowerCase()
      .replace(/\.(docx|xml|xls)$/i, "")
      .replace(/ё/g, "е")
      .replace(/[c]/g, "с")
      .replace(/[a]/g, "а")
      .replace(/[e]/g, "е")
      .replace(/[o]/g, "о")
      .replace(/[p]/g, "р")
      .replace(/[x]/g, "х")
      .replace(/[b]/g, "в")
      .replace(/[h]/g, "н")
      .replace(/[k]/g, "к")
      .replace(/[m]/g, "м")
      .replace(/[t]/g, "т")
      .replace(/[y]/g, "у")
      .replace(/[._()[\]{}!"'`«»№,:;]+/g, " ")
      .replace(/[-–—+/\\]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  const getTemplateKeys = (template) => getTemplateFieldTexts(template).map(normalizeTemplateKey).filter(Boolean);
  const matchesAny = (template, keywords) => {
    const text = getTemplateFieldTexts(template).join(" ");
    return keywords.some((keyword) => text.includes(keyword));
  };
  const docxTemplates = usableTemplates.filter((template) => template.template_type === "docx");
  const xlsTemplates = usableTemplates.filter((template) => template.template_type === "xls");
  const xmlTemplates = usableTemplates.filter((template) => template.template_type === "xml");
  const findDocx = (keywords) => docxTemplates.find((template) => matchesAny(template, keywords)) || null;
  const findXls = (keywords) => xlsTemplates.find((template) => matchesAny(template, keywords)) || null;
  const findXml = (keywords) => xmlTemplates.find((template) => matchesAny(template, keywords)) || null;
  const findTemplateByPreferredKeys = (templateList, preferredKeys) => {
    const keys = preferredKeys.map(normalizeTemplateKey).filter(Boolean);
    for (const key of keys) {
      const found = templateList.find((template) => getTemplateKeys(template).some((templateKey) => templateKey === key));
      if (found) return found;
    }
    return null;
  };
  const findTemplateSafely = (templateList, preferredKeys, fallbackKeywords = [], excludedKeywords = []) =>
    findTemplateByPreferredKeys(templateList, preferredKeys) ||
    templateList.find(
      (template) =>
        fallbackKeywords.length &&
        matchesAny(template, fallbackKeywords) &&
        !excludedKeywords.some((keyword) => matchesAny(template, [keyword])),
    ) ||
    null;
  const findDocxSafely = (preferredKeys, fallbackKeywords = [], excludedKeywords = []) =>
    findTemplateSafely(docxTemplates, preferredKeys, fallbackKeywords, excludedKeywords);
  const findStandaloneEkgTemplate = () => findDocxSafely(["экг_шаблон", "экг шаблон"], ["экг"], ["спорт"]);
  const getClientSexKey = () => {
    const sex = String(client?.sex || client?.rawApiClient?.sex || client?.gender || client?.rawApiClient?.gender || "").toLowerCase();
    if (/^(f|female|woman|ж|жен|женский)$/.test(sex) || sex.includes("жен")) return "female";
    if (/^(m|male|man|м|муж|мужской)$/.test(sex) || sex.includes("муж")) return "male";
    const patronymic = String(client?.fullName || "").trim().split(/\s+/)[2] || "";
    if (/(вна|чна|ична)$/i.test(patronymic)) return "female";
    if (/(вич|ич)$/i.test(patronymic)) return "male";
    return "";
  };
  const find086Template = () => {
    const sex = getClientSexKey();
    if (sex === "male") {
      return findDocxSafely(["086у.муж_шаблон", "086у муж шаблон", "086у.муж_шаблон_2", "086у муж шаблон 2"], ["086у.муж", "086у муж"], ["жен"]);
    }
    if (sex === "female") {
      return findDocxSafely(["086у.жен_шаблон", "086у жен шаблон", "086у.жен_шаблон_2", "086у жен шаблон 2"], ["086у.жен", "086у жен"], ["муж"]);
    }
    return findDocxSafely(["086у.муж_шаблон", "086у.жен_шаблон"], ["086"], []);
  };

  if (normalizedType === "contract") {
    return findDocx(["договор_шаблон_2", "договор"]) || null;
  }

  if (normalizedType === "xml") {
    if (serviceText.includes("трактор")) return findXml(["трактор"]) || xmlTemplates[0] || null;
    if (serviceText.includes("чод") || serviceText.includes("охран")) return findXml(["чод"]) || xmlTemplates[0] || null;
    return findXml(["водительская_шаблон2", "водительская_шаблон", "водитель"]) || xmlTemplates[0] || null;
  }

  if (normalizedType === "070") return findDocxSafely(["070 новый шабл"], ["070"], ["13070"]);
  if (normalizedType === "071") return findDocxSafely(["cправка_мед. осмотр_шаблон", "справка_мед. осмотр_шаблон", "справка шаблон"], ["071", "мед. осмотр"]);
  if (normalizedType === "072") return findDocxSafely(["072у_шаблон", "072 сюрина ноый шабл"], ["072"], ["13072"]);
  if (normalizedType === "082") return findDocxSafely(["082у_шаблон"], ["082у"], ["13082"]);
  if (normalizedType === "086") return find086Template();
  if (normalizedType === "095") return findDocxSafely(["095у_справка_шаблон"], ["095"], []);
  if (normalizedType === "gsu") return findDocxSafely(["гсу001_шаблон"], ["гсу001", "001"], []);
  if (normalizedType === "gostaina") return findDocxSafely(["гос.тайна_шаблон", "гос тайна шаблон"], ["гостайн", "гос.тайн", "989"], []);
  if (normalizedType === "gto") return findDocxSafely(["гто1144_шаблон"], ["гто1144", "1144", "гто"], []);
  if (normalizedType === "pool") return findDocxSafely(["cправкабассейн_шаблон", "справкабассейн_шаблон"], ["бассейн"], []);
  if (normalizedType === "sport") return findDocxSafely(["cпортэкг_шаблон", "спортэкг_шаблон"], ["спортэкг", "спорт"], []);
  if (normalizedType === "ekg") return findStandaloneEkgTemplate();
  if (normalizedType === "lmk") return findDocxSafely(["лмк_шаблон"], ["лмк"], []);
  if (normalizedType === "gims") return findDocxSafely(["гимс"], ["гимс"], []);
  if (normalizedType === "chod" || normalizedType === "guard") {
    return findDocxSafely(["охрана_шаблон"], ["охрана"], []) || findTemplateSafely(xmlTemplates, ["чод_новый", "чод"], ["чод"], []);
  }
  if (normalizedType === "prof_extract") {
    return findDocxSafely(["профосмотрвыписка_шаблон", "профосмотр выписка шаблон"], ["профосмотрвыписка", "выписка"], []);
  }
  if (normalizedType === "prof") return findDocxSafely(["заключение29н_шаблон"], ["заключение29н", "профосмотр", "29н"], []);
  if (normalizedType === "drug") return findDocxSafely(["драг тест морская шаблон"], ["драг"], []);
  if (normalizedType === "marine") return findDocxSafely(["серт морская шаблон"], ["морская", "marine", "seafarer"], ["драг"]);
  if (normalizedType === "13082") return findDocxSafely(["13082"], ["13082"], []);
  if (normalizedType === "13098") return findDocxSafely(["13098"], ["13098"], []);

  if (normalizedType === "driver" || serviceText.includes("водител")) {
    return (
      findXls(["все нужные шаблоны", "водительская", "тракторная"]) ||
      findDocx(["водительскаясправка_шаблон.docx", "водительскаясправка_шаблон"]) ||
      findDocx(["водитель"]) ||
      null
    );
  }

  if (serviceText.includes("082") || serviceText.includes("границ")) return findDocxSafely(["082у_шаблон"], ["082у"], ["13082"]);
  if (serviceText.includes("086")) return find086Template();
  if (serviceText.includes("095")) return findDocxSafely(["095у_справка_шаблон"], ["095"], []);
  if (serviceText.includes("бассейн")) return findDocxSafely(["cправкабассейн_шаблон", "справкабассейн_шаблон"], ["бассейн"], []);
  if (serviceText.includes("070") || serviceText.includes("путевк")) {
    return findDocxSafely(["070 новый шабл"], ["070"], ["13070"]);
  }
  if (serviceText.includes("гто")) return findDocxSafely(["гто1144_шаблон"], ["гто1144", "1144", "гто"], []);
  if (serviceText.includes("гимс")) return findDocxSafely(["гимс"], ["гимс"], []);
  if (serviceText.includes("гостайн") || serviceText.includes("гос.тайн")) return findDocxSafely(["гос.тайна_шаблон", "гос тайна шаблон"], ["гос.тайна"], []);
  if (serviceText.includes("гсу") || serviceText.includes("госслуж")) return findDocxSafely(["гсу001_шаблон"], ["гсу001"], []);
  if (serviceText.includes("охран") || serviceText.includes("чод")) return findDocxSafely(["охрана_шаблон"], ["охрана"], []) || findTemplateSafely(xmlTemplates, ["чод_новый", "чод"], ["чод"], []);
  if (serviceText.includes("трактор")) return findDocx(["трактроная", "трактор"]) || null;
  if (serviceText.includes("спорт")) return findDocxSafely(["cпортэкг_шаблон", "спортэкг_шаблон"], ["спортэкг", "спорт"], []);
  if (serviceText.includes("экг")) return findStandaloneEkgTemplate();
  if (serviceText.includes("лмк")) return findDocxSafely(["лмк_шаблон"], ["лмк"], []);
  if (serviceText.includes("профосмотр") || serviceText.includes("29н")) return findDocxSafely(["заключение29н_шаблон"], ["заключение29н", "профосмотр"], ["выписка"]);
  if (serviceText.includes("санатор")) {
    return findDocxSafely(["072у_шаблон", "072 сюрина ноый шабл"], ["072"], []);
  }
  if (serviceText.includes("драг") || serviceText.includes("drug") || serviceText.includes("alcohol")) {
    return findDocxSafely(["драг тест морская шаблон"], ["драг"], []);
  }
  if (serviceText.includes("морск") || serviceText.includes("marine") || serviceText.includes("seafar")) {
    return findDocxSafely(["серт морская шаблон"], ["морская", "marine", "seafarer"], ["драг"]);
  }

  const haystack = `${normalizedType} ${(visit?.serviceNames || []).join(" ")}`.toLowerCase();
  return (
    docxTemplates.find((template) => haystack && haystack.includes(String(template.name || "").toLowerCase())) ||
    findDocx(["справка_шаблон"]) ||
    docxTemplates[0] ||
    null
  );
}

function getChairmanTemplatePrintType(visit, printKind = "conclusion") {
  const config = getChairmanFormConfigForVisit(visit);
  if (config.type === "prof" && printKind === "extract") return "prof_extract";
  return config.templateType;
}

const CHAIRMAN_NUMBERED_CERTIFICATE_SERIES = new Map([
  ["086", "086У"],
  ["095", "095У"],
]);

function getChairmanNumberedCertificateSeries(printType) {
  return CHAIRMAN_NUMBERED_CERTIFICATE_SERIES.get(String(printType || "").toLowerCase()) || "";
}

const CHAIRMAN_CERTIFICATE_PRINT_FLOWS = new Map([
  ["sport", { preselectedSeries: "40", certificateTypes: ["sport", "gto"], selectedCertificateType: "sport" }],
  ["gto", { preselectedSeries: "40", certificateTypes: ["sport", "gto"], selectedCertificateType: "gto" }],
]);

function getChairmanCertificatePrintFlowOptions(printType) {
  return CHAIRMAN_CERTIFICATE_PRINT_FLOWS.get(String(printType || "").toLowerCase()) || null;
}

function registerGeneratedDocument(result, type, client, visit) {
  const documentItem = {
    id: result.generated_document_id || generateId("document"),
    backendId: result.generated_document_id || null,
    type: result.template_type || type,
    title: result.template_name || getDocumentTitle(type),
    clientId: client.id,
    visitId: visit.id,
    createdAt: new Date().toISOString(),
    content: `Файл сформирован: ${result.output_file_name}`,
    fileName: result.output_file_name,
    downloadUrl: buildGeneratedDocumentUrl(result.output_file_name),
    generatedFields: result.generated_fields || {},
    blankFormId: result.blank_form_id ?? null,
    blankNumber: result.blank_number || "",
  };

  const existingIndex = data.documents.findIndex(
    (item) => documentItem.backendId && String(item.backendId || "") === String(documentItem.backendId),
  );
  if (existingIndex >= 0) {
    data.documents.splice(existingIndex, 1);
  }
  data.documents.unshift(documentItem);
  visit.documentIds = Array.isArray(visit.documentIds) ? visit.documentIds : [];
  if (!visit.documentIds.includes(documentItem.id)) {
    visit.documentIds.unshift(documentItem.id);
  }
  return documentItem;
}

async function refreshDocumentWorkflowState(clientId, encounterId) {
  persistDemoState();
  await loadWorkflowData({
    clientId,
    encounterId,
  });
  if (typeof window.loadBlanksData === "function") {
    await window.loadBlanksData({ force: true });
  }
}

function getAutoGeneratedMedicalDocumentConfig(visit) {
  const serviceText = (Array.isArray(visit?.serviceNames) ? visit.serviceNames : []).join(" ").toLowerCase();
  if (!serviceText) return null;

  if (serviceText.includes("072") || serviceText.includes("санатор")) {
    return {
      toast: "Карта 072 сформирована",
      errorMessage: "Не удалось автоматически сформировать санаторно-курортную карту",
    };
  }

  if (serviceText.includes("070") || serviceText.includes("путевк")) {
    return {
      toast: "Справка 070 сформирована",
      errorMessage: "Не удалось автоматически сформировать справку 070",
    };
  }

  if (serviceText.includes("драг") || serviceText.includes("drug") || serviceText.includes("alcohol")) {
    return {
      toast: "Драг-тест сформирован",
      errorMessage: "Не удалось автоматически сформировать драг-тест",
    };
  }

  if (serviceText.includes("морск") || serviceText.includes("marine") || serviceText.includes("seafar")) {
    return {
      toast: "Морской сертификат сформирован",
      errorMessage: "Не удалось автоматически сформировать морской сертификат",
    };
  }

  return null;
}

function hasGeneratedTemplateForVisit(visit, template) {
  if (!visit || !template) return false;

  const visitDocuments = getDocumentsForVisit(visit.id);
  return visitDocuments.some((documentItem) => {
    if (template.id && String(documentItem.templateId || "") === String(template.id)) return true;
    const haystack = `${documentItem.title || ""} ${documentItem.fileName || ""}`.toLowerCase();
    return haystack.includes(String(template.file_name || "").toLowerCase()) || haystack.includes(String(template.name || "").toLowerCase());
  });
}

async function createDocumentForVisit(type, client, visit, options = {}) {
  if (!client || !visit) return null;
  if (!data.documentTemplatesLoaded) {
    await loadDocumentTemplatesFromBackend();
  }

  await syncVisitToBackend(visit, client);

  const template = pickDocumentTemplate(type, visit, client);
  if (!template) {
    throw new Error("Не найден подходящий шаблон документа");
  }

  const clientId = client.backendId || client.id;
  const endpoint = options.print ? "/documents/print" : "/documents/generate";
  const payload = {
    template_id: template.id,
    client_id: Number(clientId),
    encounter_id: visit.backendId ? Number(visit.backendId) : null,
  };
  if (options.blankFormId) {
    payload.blank_form_id = Number(options.blankFormId);
  }
  if (options.printVariant) {
    payload.print_variant = options.printVariant;
  }
  const result = await apiRequest(endpoint, {
    method: "POST",
    body: JSON.stringify(payload),
  });

  const documentItem = registerGeneratedDocument(result, type, client, visit);
  await refreshDocumentWorkflowState(clientId, visit.backendId || null);
  return documentItem;
}

async function printDocumentForVisit(type, client, visit, options = {}) {
  const documentItem = await createDocumentForVisit(type, client, visit, { ...options, print: true });
  await openGeneratedDocumentDirectly(documentItem, { targetWindow: options.targetWindow });
  return documentItem;
}

async function printChairmanDocumentFromExam(examId, options = {}) {
  const exam = data.doctorExams.find((item) => String(item.id) === String(examId));
  const client = exam
    ? getClientPool().find((item) => String(item.id) === String(exam.clientId))
    : getSelectedClient();
  const visit = exam
    ? data.visits.find((item) => String(item.id) === String(exam.visitId))
    : client
      ? getCurrentVisitForClient(client.id)
      : null;
  if (!client || !visit) {
    showToast("Не удалось подготовить печать из окна председателя");
    return null;
  }

  const printType = getChairmanTemplatePrintType(visit);
  const formInfo = getChairmanFormInfo(visit, client);
  const numberedCertificateSeries = getChairmanNumberedCertificateSeries(printType);
  const certificatePrintFlowOptions = getChairmanCertificatePrintFlowOptions(printType);
  if (formInfo.printMode === "driver-flow" || numberedCertificateSeries || certificatePrintFlowOptions) {
    window.closeSportCard?.();
    await openDriverPrintFlow({
      ...(certificatePrintFlowOptions || {}),
      ...(numberedCertificateSeries
        ? {
            preselectedSeries: numberedCertificateSeries,
            certificateTypes: printType ? [printType] : [],
            selectedCertificateType: printType || "",
            compactCertificateFlow: true,
          }
        : {}),
    });
    return null;
  }

  if (!printType) {
    showToast("Не найден шаблон для печати");
    return null;
  }

  try {
    const documentItem = await printDocumentForVisit(printType, client, visit, { targetWindow });
    window.closeSportCard?.();
    showToast(`Документ открыт: ${documentItem?.title || "документ"}`);
    return documentItem;
  } catch (error) {
    console.error(error);
    showToast(humanizeApiError(error, "Не удалось открыть шаблон"));
    return null;
  }
}

async function createDemoDocument(type) {
  ensureVisitsStore();
  const client = getSelectedClient();
  const visit = client ? getCurrentVisitForClient(client.id) : null;
  return createDocumentForVisit(type, client, visit);
}

function normalizeBlankSeries(series) {
  return String(series ?? "").trim();
}

const DRIVER_PRINT_SERIES_STORAGE_KEY = "driverPrint.lastSeries";
const DRIVER_PRINT_VARIANTS = [
  { id: "driver_front", label: "Печатать лицевую часть", errorLabel: "лицевую сторону водительской справки" },
  { id: "driver_back", label: "Печатать оборот", errorLabel: "оборот водительской справки" },
  { id: "tractor_front", label: "Лицевая трактора", errorLabel: "лицевую сторону тракторной справки" },
  { id: "tractor_back", label: "Оборот трактора", errorLabel: "оборот тракторной справки" },
];

const PREENTERED_BLANK_SERIES = ["40", "4026", "ЛМК", "ГИМС"];
const PREENTERED_BLANK_SERIES_SET = new Set(PREENTERED_BLANK_SERIES.map((item) => item.toLowerCase()));
const CERTIFICATE_PRINT_SERIES_OPTIONS = [
  "070У",
  "071У",
  "072У",
  "082У",
  "086У",
  "095У",
  "001 ГСУ",
  "989Н",
  "ГТО",
  "БАСС",
  "СПОРТ",
  "ЭКГ",
  "ЭКГР",
  "ЭКГН",
  "ЛМК",
  "ГИМС",
  "4026",
  "29Н",
  "ДРАГ",
  "МОРСКАЯ",
  "13082",
  "13098",
];
const CERTIFICATE_PRINT_SERIES_TO_TYPE = new Map([
  ["070", "070"],
  ["070у", "070"],
  ["071", "071"],
  ["071у", "071"],
  ["072", "072"],
  ["072у", "072"],
  ["082", "082"],
  ["082у", "082"],
  ["086", "086"],
  ["086у", "086"],
  ["095", "095"],
  ["095у", "095"],
  ["001", "gsu"],
  ["001 гсу", "gsu"],
  ["гсу", "gsu"],
  ["989", "gostaina"],
  ["989н", "gostaina"],
  ["гостайна", "gostaina"],
  ["гос.тайна", "gostaina"],
  ["гто", "gto"],
  ["1144", "gto"],
  ["басс", "pool"],
  ["бассейн", "pool"],
  ["спорт", "sport"],
  ["спорт экг", "sport"],
  ["экг", "ekg"],
  ["экгр", "ekg"],
  ["экгн", "ekg"],
  ["лмк", "lmk"],
  ["гимс", "gims"],
  ["4026", "chod"],
  ["чод", "chod"],
  ["охран", "guard"],
  ["охрана", "guard"],
  ["29н", "prof"],
  ["проф", "prof"],
  ["драг", "drug"],
  ["морская", "marine"],
  ["морск", "marine"],
  ["13082", "13082"],
  ["13098", "13098"],
]);
const CERTIFICATE_PRINT_TYPE_LABELS = {
  "070": "Справка 070У",
  "071": "Справка 071У",
  "072": "Справка 072У",
  "082": "Справка 082У",
  "086": "Справка 086У",
  "095": "Справка 095У",
  gsu: "Справка 001 ГСУ",
  gostaina: "Справка гостайна",
  gto: "Справка ГТО",
  pool: "Справка в бассейн",
  sport: "Справка Спорт",
  ekg: "ЭКГ",
  lmk: "ЛМК",
  gims: "ГИМС",
  chod: "Справка ЧОД",
  guard: "Справка охрана",
  prof: "Заключение 29Н",
  drug: "Drug/alcohol test",
  marine: "Морская справка",
  "13082": "13082",
  "13098": "13098",
};
const SERVICE_SERIES_OVERRIDES = new Map([
  ["071у", "071У"],
  ["профосмотр", "29Н"],
  ["первичный профосмотр 29н", "29Н"],
  ["санаторно-курортная карта", "072У"],
  ["санаторно-курортная карта 072у", "072У"],
  ["справка для получения путевки 070у", "070У"],
  ["справка 001 гсу для работы на госслужбе", "001 ГСУ"],
  ["справка формы 001 гсу", "001 ГСУ"],
  ["справка 002 чод (для охраны)", "4026"],
  ["справка в бассейн", "БАСС"],
  ["справка для посещения бассейна", "БАСС"],
  ["справка выезжающих за границу 082у", "082У"],
  ["справка для выезжающих за границу 082у", "082У"],
  ["справка гостайна, форма 989н", "989Н"],
  ["справка для работы с гостайной формы 989н", "989Н"],
  ["справка гто 1144", "ГТО"],
  ["справка для поступления 086у", "086У"],
  ["справка формы 086у", "086У"],
  ["справка по форме 095у", "095У"],
  ["справка 095/у о временной нетрудоспособности", "095У"],
  ["справка для участия в соревнованиях", "СПОРТ"],
  ["справка спорт + экг", "СПОРТ"],
  ["электрокардиография (экг)", "ЭКГ"],
  ["морская медицинская комиссия", "МОРСКАЯ"],
  ["drug/alcohol test № 96", "ДРАГ"],
  ["узи брюшной полости", "УЗИ ОБП"],
  ["узи молочных желез", "УЗИ МЖ"],
  ["узи предстательной железы", "УЗИ ПЖ"],
  ["экг без расшифровки", "ЭКГ"],
  ["экг при нагрузке с расшифровкой", "ЭКГН"],
  ["экг с расшифровкой", "ЭКГР"],
]);

function getStoredDriverPrintSeries() {
  try {
    return normalizeBlankSeries(window.localStorage?.getItem(DRIVER_PRINT_SERIES_STORAGE_KEY));
  } catch (error) {
    console.warn("Не удалось прочитать последнюю серию бланка", error);
    return "";
  }
}

function setStoredDriverPrintSeries(series) {
  const normalized = normalizeBlankSeries(series);
  try {
    if (normalized) {
      window.localStorage?.setItem(DRIVER_PRINT_SERIES_STORAGE_KEY, normalized);
    } else {
      window.localStorage?.removeItem(DRIVER_PRINT_SERIES_STORAGE_KEY);
    }
  } catch (error) {
    console.warn("Не удалось сохранить последнюю серию бланка", error);
  }
}

function getDriverPrintCertificateType(series) {
  const normalized = normalizeBlankSeries(series).toLowerCase();
  if (CERTIFICATE_PRINT_SERIES_TO_TYPE.has(normalized)) return CERTIFICATE_PRINT_SERIES_TO_TYPE.get(normalized);
  if (/^0?70у?$/.test(normalized)) return "070";
  if (/^0?71у?$/.test(normalized)) return "071";
  if (/^0?72у?$/.test(normalized)) return "072";
  if (/^0?82у?$/.test(normalized)) return "082";
  if (/^0?86у?$/.test(normalized)) return "086";
  if (/^0?95у?$/.test(normalized)) return "095";
  if (normalized.includes("гсу") || normalized.includes("001")) return "gsu";
  if (normalized.includes("гостайн") || normalized.includes("гос.тайн") || normalized.includes("989")) return "gostaina";
  if (normalized.includes("гто") || normalized.includes("1144")) return "gto";
  if (normalized.includes("басс")) return "pool";
  if (normalized.includes("спорт")) return "sport";
  if (normalized.includes("экг")) return "ekg";
  if (normalized.includes("лмк")) return "lmk";
  if (normalized.includes("гимс")) return "gims";
  if (normalized.includes("4026") || normalized.includes("чод")) return "chod";
  if (normalized.includes("охран")) return "guard";
  if (normalized.includes("29н") || normalized.includes("проф")) return "prof";
  if (normalized.includes("драг")) return "drug";
  if (normalized.includes("морск") || normalized.includes("marine") || normalized.includes("seafar")) return "marine";
  if (normalized === "13082" || normalized === "13098") return normalized;
  return "";
}

function getCertificatePrintTypeLabel(type) {
  return CERTIFICATE_PRINT_TYPE_LABELS[String(type || "").toLowerCase()] || "Печать документа";
}

function isCertificatePrintSeries(series) {
  return Boolean(getDriverPrintCertificateType(series));
}

function isNumberedCertificatePrintType(type) {
  return new Set(["086", "095"]).has(String(type || "").toLowerCase());
}

function isNumberedCertificatePrintSeries(series) {
  return isNumberedCertificatePrintType(getDriverPrintCertificateType(series));
}

function resolveNumberedCertificateLookupSeries(selectedSeries, certificateType, seriesOptions = []) {
  const normalizedSelected = normalizeBlankSeries(selectedSeries).toLowerCase();
  const normalizedType = String(certificateType || "").toLowerCase();
  const options = (Array.isArray(seriesOptions) ? seriesOptions : [])
    .map((item) => normalizeBlankSeries(item?.series || item))
    .filter(Boolean);

  const exact = options.find((series) => series.toLowerCase() === normalizedSelected);
  if (exact) return exact;

  if (isNumberedCertificatePrintType(normalizedType)) {
    const marker = normalizedType === "086" ? "086" : "095";
    const matching = options.find((series) => series.toLowerCase().includes(marker));
    if (matching) return matching;
  }

  return normalizeBlankSeries(selectedSeries);
}

function isPreenteredBlankSeries(series) {
  return PREENTERED_BLANK_SERIES_SET.has(normalizeBlankSeries(series).toLowerCase());
}

function buildServiceSeriesAbbreviation(service) {
  const name = String(service?.name || "").trim();
  const normalizedName = name.toLowerCase();
  if (!name) return "";
  if (
    isDriverService(service) ||
    isTractorService(service) ||
    isGimsService(service) ||
    isLmkService(service) ||
    normalizedName.includes("лмк")
  ) {
    return "";
  }
  if (SERVICE_SERIES_OVERRIDES.has(normalizedName)) {
    return SERVICE_SERIES_OVERRIDES.get(normalizedName);
  }

  const words = name
    .replace(/[()]/g, " ")
    .split(/[\s,./+-]+/)
    .map((word) => word.trim())
    .filter((word) => word && !["для", "при", "без", "с", "на", "по", "форма", "форме", "врача"].includes(word.toLowerCase()));
  const important = words.filter((word) => /\d/.test(word) || word.length > 2).slice(0, 3);
  const source = important.length ? important : words.slice(0, 2);
  return source
    .map((word) => (/\d/.test(word) ? word.toUpperCase() : word.slice(0, 3).toUpperCase()))
    .join(" ")
    .trim();
}

function getAutoServiceSeriesOptions() {
  const source = Array.isArray(data.serverServices) && data.serverServices.length ? data.serverServices : structuredServices;
  return (Array.isArray(source) ? source : [])
    .filter((service) => service?.isActive !== false)
    .map(buildServiceSeriesAbbreviation)
    .filter((series) => series && !isPreenteredBlankSeries(series));
}

function getDriverPrintSeriesPickerOptions(seriesOptions = []) {
  const ordered = [...PREENTERED_BLANK_SERIES, ...CERTIFICATE_PRINT_SERIES_OPTIONS, ...getAutoServiceSeriesOptions()];
  (Array.isArray(seriesOptions) ? seriesOptions : []).forEach((item) => {
    const series = normalizeBlankSeries(item?.series);
    if (series) ordered.push(series);
  });

  return ordered.filter((series, index, list) => list.findIndex((item) => item.toLowerCase() === series.toLowerCase()) === index);
}

function closeDriverPrintSeriesPicker() {
  document.querySelector("[data-driver-series-picker]")?.remove();
}

function openDriverPrintSeriesPicker({ value, options, onSelect }) {
  closeDriverPrintSeriesPicker();

  let selectedValue = normalizeBlankSeries(value) || options[0] || "";
  const overlay = document.createElement("div");
  overlay.className = "driver-series-picker";
  overlay.dataset.driverSeriesPicker = "true";
  overlay.innerHTML = `
    <div class="driver-series-picker__panel" role="dialog" aria-modal="true" aria-label="Выбор серии">
      <div class="driver-series-picker__head">
        <strong>Введите строку или выберите из имеющихся</strong>
        <button type="button" class="driver-series-picker__close" data-driver-series-close aria-label="Закрыть">×</button>
      </div>
      <div class="driver-series-picker__top">
        <input class="driver-series-picker__search" data-driver-series-search value="" placeholder="${escapeHtml(selectedValue)}" />
        <button type="button" class="driver-series-picker__ok" data-driver-series-ok>OK</button>
      </div>
      <div class="driver-series-picker__list" data-driver-series-list></div>
      <div class="driver-series-picker__selected" data-driver-series-selected>${escapeHtml(selectedValue)}</div>
    </div>
  `;

  const panel = overlay.querySelector(".driver-series-picker__panel");
  const searchInput = overlay.querySelector("[data-driver-series-search]");
  const listNode = overlay.querySelector("[data-driver-series-list]");
  const selectedNode = overlay.querySelector("[data-driver-series-selected]");

  const applySelection = () => {
    onSelect(normalizeBlankSeries(selectedValue || searchInput?.value));
    closeDriverPrintSeriesPicker();
  };

  const renderList = () => {
    const query = normalizeBlankSeries(searchInput?.value).toLowerCase();
    const visibleOptions = options.filter((item) => !query || item.toLowerCase().includes(query));
    listNode.innerHTML = visibleOptions
      .map(
        (item) => `
          <button type="button" class="driver-series-picker__item${item.toLowerCase() === selectedValue.toLowerCase() ? " driver-series-picker__item--active" : ""}" data-driver-series-value="${escapeHtml(item)}">
            ${escapeHtml(item)}
          </button>
        `,
      )
      .join("");

    listNode.querySelectorAll("[data-driver-series-value]").forEach((button) => {
      button.addEventListener("click", () => {
        selectedValue = normalizeBlankSeries(button.dataset.driverSeriesValue);
        if (searchInput) searchInput.value = "";
        if (selectedNode) selectedNode.textContent = selectedValue;
        renderList();
      });
      button.addEventListener("dblclick", applySelection);
    });
  };

  overlay.addEventListener("mousedown", (event) => {
    if (!panel?.contains(event.target)) {
      closeDriverPrintSeriesPicker();
    }
  });
  overlay.querySelector("[data-driver-series-close]")?.addEventListener("click", closeDriverPrintSeriesPicker);
  overlay.querySelector("[data-driver-series-ok]")?.addEventListener("click", applySelection);
  searchInput?.addEventListener("input", () => {
    selectedValue = normalizeBlankSeries(searchInput.value);
    if (selectedNode) selectedNode.textContent = selectedValue;
    renderList();
  });
  searchInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      applySelection();
    }
    if (event.key === "Escape") {
      event.preventDefault();
      closeDriverPrintSeriesPicker();
    }
  });

  document.body.appendChild(overlay);
  renderList();
  searchInput?.focus();
  searchInput?.select();
}

function buildBlankSeriesLabel(item) {
  const seriesLabel = normalizeBlankSeries(item?.series) || "без серии";
  const nextLabel = item?.next_full_number ? `, следующий: ${item.next_full_number}` : "";
  return `${seriesLabel} (${Number(item?.free_count || 0)} шт.${nextLabel})`;
}

function getDriverPrintBlankParts(blank, selectedSeries) {
  const series = normalizeBlankSeries(blank?.series) || normalizeBlankSeries(selectedSeries);
  const fullNumber = String(blank?.full_number || "").trim();
  const number = series && fullNumber.startsWith(series)
    ? fullNumber.slice(series.length).trim()
    : fullNumber;
  const primaryDate = formatApiDate(blank?.issued_at || blank?.created_at || new Date().toISOString());
  return {
    series,
    number,
    fullNumber,
    primaryDate,
  };
}

function normalizeDriverPrintBlank(blank) {
  if (!blank || typeof blank !== "object") return blank;
  return {
    ...blank,
    id: blank.id ?? blank.next_form_id ?? blank.form_id ?? null,
    full_number: blank.full_number || blank.next_full_number || "",
    series: normalizeBlankSeries(blank.series),
  };
}

function renderDriverPrintResultPrompt({ printedDocument, printMessage }) {
  return `
    <div class="document-preview">
      <strong>${escapeHtml(printedDocument?.title || "Водительская справка")}</strong>
      <p>${escapeHtml(printMessage || "Документ открыт.")}</p>
      <p>После печати подтвердите результат. Если бланк испорчен, мы сразу спишем его и подберем следующий номер.</p>
      <div class="card" style="margin-top:12px;">
        <strong>Инструкция по двусторонней печати</strong>
        <ol style="margin:10px 0 0 18px; padding:0; display:grid; gap:8px;">
          <li>Достаньте стопку распечатанных страниц из выходного лотка.</li>
          <li>Положите ее в лоток 1, не меняя ориентацию.</li>
          <li>Подтвердите продолжение печати кнопкой ` + "`Да`" + `, если бланк напечатан нормально.</li>
        </ol>
      </div>
      <div class="client-create-actions" style="margin-top:16px;">
        <button type="button" class="ghost-button" id="driverPrintFailed">Нет, бланк испорчен</button>
        <button type="button" class="primary-button" id="driverPrintSuccess">Да, все нормально</button>
      </div>
    </div>
  `;
}

function isFrontDriverPrintVariant(variantId) {
  return variantId === "driver_front" || variantId === "tractor_front";
}

function renderDriverPrintInstructionPrompt() {
  return `
    <div class="driver-print-instruction">
      <div class="driver-print-instruction__intro">
        После завершения печати на одной стороне документа следуйте инструкциям по печати на второй стороне каждой страницы.
      </div>
      <div class="driver-print-instruction__steps">
        <div class="driver-print-instruction__step">
          <div class="driver-print-instruction__head">
            <span class="driver-print-instruction__number">1</span>
            <p>При появлении запроса на подачу бумаги вручную извлеките стопку распечатанных страниц из выходного лотка.</p>
          </div>
          <div class="printer-illustration printer-illustration--remove">
            <div class="printer-illustration__body">
              <div class="printer-illustration__top-paper"></div>
              <div class="printer-illustration__slot"></div>
              <div class="printer-illustration__tray"></div>
              <div class="printer-illustration__paper"></div>
            </div>
            <div class="printer-illustration__arrow printer-illustration__arrow--out"></div>
          </div>
        </div>
        <div class="driver-print-instruction__step">
          <div class="driver-print-instruction__head">
            <span class="driver-print-instruction__number">2</span>
            <p>Поместите стопку распечатанных страниц в лоток 1, не меняя ее ориентацию.</p>
          </div>
          <div class="printer-illustration printer-illustration--load">
            <div class="printer-illustration__body">
              <div class="printer-illustration__top-paper"></div>
              <div class="printer-illustration__slot"></div>
              <div class="printer-illustration__tray"></div>
              <div class="printer-illustration__paper"></div>
            </div>
            <div class="printer-illustration__arrow printer-illustration__arrow--in"></div>
          </div>
        </div>
        <div class="driver-print-instruction__step">
          <div class="driver-print-instruction__head">
            <span class="driver-print-instruction__number">3</span>
            <p>Нажмите клавишу "Go" или "OK".</p>
          </div>
        </div>
      </div>
      <div class="driver-print-instruction__footer">
        <button type="button" class="driver-print-instruction__button" id="driverPrintContinue">Перейти</button>
      </div>
    </div>
  `;
}

function renderDriverFrontCheckPrompt() {
  return `
    <div class="driver-front-check">
      <div class="driver-front-check__icon">?</div>
      <div class="driver-front-check__text">
        <p>Справка напечатана нормально.</p>
        <p>Нажмите "Да" для продолжения.</p>
        <p>Нажмите "Нет" если бланк испорчен.</p>
      </div>
      <div class="driver-front-check__actions">
        <button type="button" class="driver-front-check__button" id="driverFrontCheckYes">Да</button>
        <button type="button" class="driver-front-check__button" id="driverFrontCheckNo">Нет</button>
      </div>
    </div>
  `;
}

async function openDriverPrintFlow(options = {}) {
  ensureVisitsStore();
  const client = getSelectedClient();
  const visit = client ? getCurrentVisitForClient(client.id) : null;
  if (!client || !visit) {
    showToast("Сначала выбери клиента и обращение");
    return;
  }
  if (!data.documentTemplatesLoaded) {
    await loadDocumentTemplatesFromBackend();
  }

  await syncVisitToBackend(visit, client);

  const preselectedSeries = normalizeBlankSeries(options.preselectedSeries);
  const requestedCertificateTypes = Array.isArray(options.certificateTypes)
    ? options.certificateTypes.map((type) => String(type || "").toLowerCase()).filter(Boolean)
    : [];
  const compactCertificateFlow = Boolean(options.compactCertificateFlow);
  const preselectedCertificateType = getDriverPrintCertificateType(preselectedSeries);
  const template = pickDocumentTemplate("driver", visit, client);
  if (!template && !preselectedCertificateType && !requestedCertificateTypes.length) {
    showToast("Не найден шаблон водительской справки");
    return;
  }

  const clientId = client.backendId || client.id;
  const centerId = await resolveCenterIdForVisit(visit, client);
  const blankType = template?.blank_type || "driver_medical_certificate";

  let seriesOptions = [];
  let fallbackBlank = options.preselectedBlank || null;
  try {
    const query = new URLSearchParams({
      blank_type: blankType,
      center_id: String(centerId),
    });
    seriesOptions = await apiRequest(`/blanks/series?${query.toString()}`);
  } catch (error) {
    console.warn("Не удалось загрузить свободные серии бланков", error);
  }

  const seriesOptionMap = new Map();
  (Array.isArray(seriesOptions) ? seriesOptions : []).forEach((item) => {
    const series = normalizeBlankSeries(item?.series);
    if (series) seriesOptionMap.set(series.toLowerCase(), item);
  });
  getDriverPrintSeriesPickerOptions(seriesOptions).forEach((series) => {
    const normalizedKey = normalizeBlankSeries(series).toLowerCase();
    if (!seriesOptionMap.has(normalizedKey)) {
      seriesOptionMap.set(normalizedKey, {
        series,
        free_count: isPreenteredBlankSeries(series) ? 0 : "",
        next_form_id: null,
        next_full_number: "",
      });
    }
  });
  seriesOptions = Array.from(seriesOptionMap.values());

  if (!Array.isArray(seriesOptions) || !seriesOptions.length) {
    try {
      const query = new URLSearchParams({
        blank_type: blankType,
        center_id: String(centerId),
      });
      fallbackBlank = fallbackBlank || (await apiRequest(`/blanks/forms/next?${query.toString()}`));
      if (fallbackBlank?.series) {
        seriesOptions = [
          {
            series: fallbackBlank.series,
            free_count: "",
            next_form_id: fallbackBlank.id ?? null,
            next_full_number: fallbackBlank.full_number ?? "",
          },
        ];
      }
    } catch (error) {
      console.warn("Не удалось подобрать свободный бланк напрямую", error);
    }
  }

  if (!Array.isArray(seriesOptions) || !seriesOptions.length) {
    showToast("Для водительской справки нет свободных номерных бланков");
    return;
  }

  const flowState = {
    client,
    visit,
    clientId: Number(clientId),
    centerId: Number(centerId),
    template,
    blankType,
    seriesOptions,
    selectedSeries:
      preselectedSeries ||
      getStoredDriverPrintSeries() ||
      normalizeBlankSeries(seriesOptions[0]?.series),
    selectedCertificateType: "",
    certificateTypes: requestedCertificateTypes,
    compactCertificateFlow,
    currentBlank: normalizeDriverPrintBlank(fallbackBlank),
    loading: false,
    error: "",
  };
  flowState.selectedCertificateType =
    String(options.selectedCertificateType || "").toLowerCase() ||
    getDriverPrintCertificateType(flowState.selectedSeries) ||
    flowState.certificateTypes[0] ||
    "";

  const seriesHints = flowState.seriesOptions
    .map((item) => normalizeBlankSeries(item.series))
    .filter(Boolean);
  if (!seriesHints.includes(flowState.selectedSeries)) {
    flowState.selectedSeries = flowState.selectedSeries || normalizeBlankSeries(seriesOptions[0]?.series);
  }

  if (!flowState.currentBlank && isPreenteredBlankSeries(flowState.selectedSeries)) {
    try {
      const query = new URLSearchParams({
        blank_type: flowState.blankType,
        center_id: String(flowState.centerId),
      });
      query.set("series", flowState.selectedSeries || "");
      flowState.currentBlank = normalizeDriverPrintBlank(await apiRequest(`/blanks/forms/next?${query.toString()}`));
    } catch (error) {
      flowState.error = humanizeApiError(error, "Не удалось подобрать свободный бланк");
    }
  }

  const renderPrintActions = () => {
    const certificateTypes = flowState.certificateTypes.length
      ? flowState.certificateTypes
      : flowState.selectedCertificateType
        ? [flowState.selectedCertificateType]
        : [];
    if (certificateTypes.length) {
      return certificateTypes
        .map(
          (certificateType) => `
            <button type="button" class="driver-print-classic__button" data-driver-print-selected-certificate="${escapeHtml(certificateType)}" ${flowState.loading || !flowState.currentBlank?.id ? "disabled" : ""}>${escapeHtml(getCertificatePrintTypeLabel(certificateType))}</button>
          `,
        )
        .join("");
    }

    return `
      <button type="button" class="driver-print-classic__button" data-driver-print-variant="driver_front" ${flowState.loading || !flowState.currentBlank || !flowState.template ? "disabled" : ""}>Печатать лицевую часть</button>
      <button type="button" class="driver-print-classic__button" data-driver-print-variant="driver_back" ${flowState.loading || !flowState.currentBlank || !flowState.template ? "disabled" : ""}>Печатать оборот</button>
      <button type="button" class="driver-print-classic__button" data-driver-print-variant="tractor_front" ${flowState.loading || !flowState.currentBlank || !flowState.template ? "disabled" : ""}>Лицевая трактора</button>
      <button type="button" class="driver-print-classic__button" data-driver-print-variant="tractor_back" ${flowState.loading || !flowState.currentBlank || !flowState.template ? "disabled" : ""}>Оборот трактора</button>
    `;
  };

  const markPrintedDocument = async (generatedDocumentId, success, reason = null) => {
    return apiRequest("/documents/print-result", {
      method: "POST",
      body: JSON.stringify({
        generated_document_id: Number(generatedDocumentId),
        success,
        reason,
      }),
    });
  };

  const restartDriverPrintFlow = async () => {
    await refreshDocumentWorkflowState(flowState.clientId, flowState.visit.backendId || null);
    await openDriverPrintFlow({
      preselectedSeries: flowState.selectedSeries,
      certificateTypes: flowState.certificateTypes,
      selectedCertificateType: flowState.selectedCertificateType,
      compactCertificateFlow: flowState.compactCertificateFlow,
    });
  };

  const handleSpoiledBlank = async (generatedDocumentId) => {
    try {
      await markPrintedDocument(generatedDocumentId, false, "Испорчен при печати");
      await restartDriverPrintFlow();
      showToast("Бланк отмечен как испорченный. Начните печать заново.");
    } catch (error) {
      showToast(humanizeApiError(error, "Не удалось отметить бланк как испорченный"));
    }
  };

  const handleStandardPrintResult = async (result, printedDocument) => {
    openActionModal(
      "Результат печати",
      renderDriverPrintResultPrompt({
        printedDocument,
        printMessage: result.message,
      }),
    );

    document.getElementById("driverPrintSuccess")?.addEventListener("click", async () => {
      try {
        await markPrintedDocument(result.generated_document_id, true);
        await refreshDocumentWorkflowState(flowState.clientId, flowState.visit.backendId || null);
        actionModal.classList.add("hidden");
        showToast(`Печать подтверждена: ${printedDocument.blankNumber || printedDocument.title}`);
      } catch (error) {
        showToast(humanizeApiError(error, "Не удалось подтвердить печать"));
      }
    });

    document.getElementById("driverPrintFailed")?.addEventListener("click", async () => {
      await handleSpoiledBlank(result.generated_document_id);
    });
  };

  const handleFrontPrintResult = async (result, backVariantId) => {
    openActionModal("Инструкции по печати на обеих сторонах", renderDriverPrintInstructionPrompt(), "modal--print-instruction");
    document.getElementById("driverPrintContinue")?.addEventListener("click", async () => {
      openActionModal("Результат печати:", renderDriverFrontCheckPrompt(), "modal--front-print-check");
      document.getElementById("driverFrontCheckNo")?.addEventListener("click", async () => {
        await handleSpoiledBlank(result.generated_document_id);
      });
      document.getElementById("driverFrontCheckYes")?.addEventListener("click", async () => {
        try {
          await markPrintedDocument(result.generated_document_id, true);
          await printVariant(backVariantId, { skipConfirmation: true });
        } catch (error) {
          showToast(humanizeApiError(error, "Не удалось подтвердить лицевую сторону"));
        }
      });
    });
  };

  const printVariant = async (variantId, options = {}) => {
    const skipConfirmation = Boolean(options.skipConfirmation);
    const variant = DRIVER_PRINT_VARIANTS.find((item) => item.id === variantId);
    if (!variant || !flowState.currentBlank?.id) return;
    if (!flowState.template) {
      flowState.error = "Не найден шаблон водительской справки";
      renderFlow();
      return;
    }
    flowState.loading = true;
    flowState.error = "";
    renderFlow();
    try {
      const result = await apiRequest("/documents/print", {
        method: "POST",
        body: JSON.stringify({
          template_id: flowState.template.id,
          client_id: flowState.clientId,
          encounter_id: flowState.visit.backendId ? Number(flowState.visit.backendId) : null,
          blank_form_id: Number(flowState.currentBlank.id),
          print_variant: variant.id,
        }),
      });
      const printedDocument = registerGeneratedDocument(result, "driver", flowState.client, flowState.visit);
      await openGeneratedDocumentDirectly(printedDocument, { targetWindow: options.targetWindow });
      await refreshDocumentWorkflowState(flowState.clientId, flowState.visit.backendId || null);
      if (skipConfirmation) {
        try {
          await markPrintedDocument(result.generated_document_id, true);
          actionModal.classList.add("hidden");
          showToast(`Документ открыт: ${printedDocument.blankNumber || printedDocument.title}`);
        } catch (error) {
          showToast(humanizeApiError(error, "Не удалось подтвердить открытие оборота"));
        }
      } else if (isFrontDriverPrintVariant(variant.id)) {
        const backVariantId = variant.id === "tractor_front" ? "tractor_back" : "driver_back";
        await handleFrontPrintResult(result, backVariantId);
      } else {
        await handleStandardPrintResult(result, printedDocument);
      }
    } catch (error) {
      if (options.targetWindow && !options.targetWindow.closed) {
        options.targetWindow.close();
      }
      flowState.error = humanizeApiError(error, `Не удалось открыть ${variant.errorLabel}`);
      flowState.loading = false;
      renderFlow();
    }
  };

  const printSelectedCertificate = async (certificateType = flowState.selectedCertificateType, options = {}) => {
    const finalCertificateType = String(certificateType || "").toLowerCase();
    if (!finalCertificateType) return;
    if (!flowState.currentBlank?.id) {
      if (options.targetWindow && !options.targetWindow.closed) {
        options.targetWindow.close();
      }
      flowState.error = isPreenteredBlankSeries(flowState.selectedSeries)
        ? "Сначала нажмите \"Найти номер\", чтобы подобрать свободный бланк из заведенного диапазона."
        : "Сначала нажмите \"Найти номер\", чтобы присвоить следующий 7-значный номер.";
      renderFlow();
      return;
    }
    flowState.loading = true;
    flowState.error = "";
    renderFlow();
    try {
      const printOptions = { blankFormId: Number(flowState.currentBlank.id) };
      const documentItem = await createDocumentForVisit(finalCertificateType, client, visit, { ...printOptions, print: true });
      await openGeneratedDocumentDirectly(documentItem, { targetWindow: options.targetWindow });
      showToast(`Документ открыт: ${documentItem?.title || "документ"}`);
    } catch (error) {
      if (options.targetWindow && !options.targetWindow.closed) {
        options.targetWindow.close();
      }
      console.error(error);
      flowState.error = humanizeApiError(error, "Не удалось отправить справку в печать");
    } finally {
      flowState.loading = false;
      renderFlow();
    }
  };

  const renderFlow = () => {
    const blankParts = getDriverPrintBlankParts(flowState.currentBlank, flowState.selectedSeries);
    const findButtonDisabled = flowState.loading;

    openActionModal(
      "Печать результатов:",
      `
        <div class="driver-print-classic">
          <input class="driver-print-classic__fio" value="${escapeHtml(client.fullName || "Клиент")}" readonly />

          <div class="driver-print-classic__caption">Укажите серию и номер бланка:</div>
          <div class="driver-print-classic__lookup">
            <input id="driverBlankSeries" class="driver-print-classic__input driver-print-classic__input--series" value="${escapeHtml(flowState.selectedSeries)}" readonly />
            <input id="driverBlankNumber" class="driver-print-classic__input" value="${escapeHtml(blankParts.number)}" readonly />
            <button type="button" class="driver-print-classic__button driver-print-classic__button--find" id="driverFindBlank" ${findButtonDisabled ? "disabled" : ""}>Найти номер</button>
          </div>

          ${
            flowState.compactCertificateFlow
              ? ""
              : '<button type="button" class="driver-print-classic__button driver-print-classic__button--duplicate" disabled>Печать дубликата</button>'
          }

          ${
            flowState.compactCertificateFlow
              ? ""
              : `
                <div class="driver-print-classic__caption driver-print-classic__caption--primary">Серия, номер, дата первоначального бланка:</div>
                <div class="driver-print-classic__primary">
                  <input class="driver-print-classic__input driver-print-classic__input--series" value="${escapeHtml(blankParts.series)}" readonly />
                  <input class="driver-print-classic__input" value="${escapeHtml(blankParts.fullNumber || blankParts.number)}" readonly />
                  <input class="driver-print-classic__input driver-print-classic__input--date" value="${escapeHtml(blankParts.primaryDate)}" readonly />
                </div>
              `
          }

          ${flowState.error ? `<div class="driver-print-classic__error">${escapeHtml(flowState.error)}</div>` : ""}

          <div class="driver-print-classic__actions driver-print-classic__actions--driver">
            ${renderPrintActions()}
          </div>
          ${
            flowState.compactCertificateFlow
              ? ""
              : `
                <button type="button" class="driver-print-classic__button driver-print-classic__button--wide" data-driver-print-extra="court">справка Суда</button>
                <button type="button" class="driver-print-classic__button driver-print-classic__button--wide" data-driver-print-extra="ambulatory">Амб. Карта 25У</button>
              `
          }
        </div>
      `,
      "modal--driver-print",
    );

    const seriesInput = document.getElementById("driverBlankSeries");
    const selectSeries = (value) => {
      flowState.selectedSeries = normalizeBlankSeries(value);
      flowState.selectedCertificateType = getDriverPrintCertificateType(flowState.selectedSeries);
      setStoredDriverPrintSeries(flowState.selectedSeries);
      flowState.currentBlank = null;
      flowState.error = "";
      renderFlow();
    };
    const openSeriesPicker = (event) => {
      event.preventDefault();
      event.stopPropagation();
      openDriverPrintSeriesPicker({
        value: flowState.selectedSeries,
        options: getDriverPrintSeriesPickerOptions(flowState.seriesOptions),
        onSelect: selectSeries,
      });
    };
    seriesInput?.addEventListener("pointerdown", openSeriesPicker);
    seriesInput?.addEventListener("mousedown", openSeriesPicker);
    seriesInput?.addEventListener("click", openSeriesPicker);
    seriesInput?.addEventListener("focus", openSeriesPicker);

    document.getElementById("driverFindBlank")?.addEventListener("click", async () => {
      flowState.loading = true;
      flowState.error = "";
      const lookupSeries = resolveNumberedCertificateLookupSeries(
        flowState.selectedSeries,
        flowState.selectedCertificateType,
        flowState.seriesOptions,
      );
      setStoredDriverPrintSeries(lookupSeries || flowState.selectedSeries);
      renderFlow();
      try {
        const query = new URLSearchParams({
          blank_type: flowState.blankType,
          center_id: String(flowState.centerId),
        });
        if (lookupSeries) {
          query.set("series", lookupSeries);
        } else {
          query.set("series", "");
        }
        if (!isPreenteredBlankSeries(lookupSeries || flowState.selectedSeries)) {
          query.set("auto_create", "true");
        }
        flowState.currentBlank = normalizeDriverPrintBlank(await apiRequest(`/blanks/forms/next?${query.toString()}`));
        if (flowState.currentBlank?.series) {
          flowState.selectedSeries = normalizeBlankSeries(flowState.currentBlank.series);
          flowState.selectedCertificateType = getDriverPrintCertificateType(flowState.selectedSeries) || flowState.selectedCertificateType;
          setStoredDriverPrintSeries(flowState.selectedSeries);
        }
      } catch (error) {
        flowState.currentBlank = null;
        flowState.error = humanizeApiError(error, "Не удалось подобрать свободный бланк");
      } finally {
        flowState.loading = false;
        renderFlow();
      }
    });

    document.querySelectorAll("[data-driver-print-variant]").forEach((button) => {
      button.addEventListener("click", async () => {
        const targetWindow = window.open("about:blank", "_blank");
        await printVariant(button.dataset.driverPrintVariant || "", { targetWindow });
      });
    });

    document.querySelectorAll("[data-driver-print-selected-certificate]").forEach((button) => {
      button.addEventListener("click", async () => {
        const targetWindow = window.open("about:blank", "_blank");
        await printSelectedCertificate(button.dataset.driverPrintSelectedCertificate || "", { targetWindow });
      });
    });
  };

  renderFlow();
}

function renderDocumentHistory(visitDocuments) {
  return `
    <div class="document-history">
      <strong>Сформированные документы</strong>
      ${
        visitDocuments.length
          ? visitDocuments
              .map(
                (documentItem) => `
                  <button class="document-history__row" data-open-document-id="${escapeHtml(documentItem.id)}">
                    <span>${escapeHtml(documentItem.title)}</span>
                    <small>${escapeHtml(formatDateTime(documentItem.createdAt))}</small>
                    ${documentItem.blankNumber ? `<small class="blank-badge">№ бланка: ${escapeHtml(documentItem.blankNumber)}</small>` : ""}
                  </button>
                `,
              )
              .join("")
          : `<p class="muted">Пока документов по этому обращению нет. Нажми нужную кнопку выше, чтобы сформировать.</p>`
      }
    </div>
  `;
}

function renderDocumentsPage() {
  const selectedClient = getSelectedClient();
  const activeVisit = selectedClient ? getCurrentVisitForClient(selectedClient.id) : null;
  const visitDocuments = activeVisit ? getDocumentsForVisit(activeVisit.id) : [];
  const backendEncounterId = activeVisit?.backendId || null;
  const visibleGeneratedDocuments = backendEncounterId
    ? data.generatedDocuments.filter((item) => String(item.encounterId || "") === String(backendEncounterId))
    : data.generatedDocuments;

  return `
    ${renderBlanksPage()}
    ${renderWorkflowLoadState()}
    <section class="card">
      <h3>Документы по обращению</h3>
      ${
        selectedClient && activeVisit
          ? `
            <p class="muted">Клиент: ${escapeHtml(selectedClient.fullName)}. ${escapeHtml(getVisitTitle(activeVisit))}</p>
            <div class="document-actions">
              <button class="primary-button" data-generate-document="contract">Договор</button>
              <button class="primary-button" data-generate-document="medical">Медицинская справка</button>
              <button class="ghost-button" data-generate-document="driver">Водительская справка</button>
              <button class="ghost-button" data-generate-document="xml">XML-файл</button>
            </div>
            ${renderDocumentHistory(visitDocuments)}
          `
          : `<p class="muted">Сначала на главной найди клиента и создай обращение. После этого здесь появится генерация документов по выбранному обращению.</p>`
      }
    </section>
    <div class="two-col chart-main-grid">
      ${renderGeneratedDocumentsTable(visibleGeneratedDocuments)}
      ${renderDocumentJournalsTable()}
    </div>
    <div class="two-col chart-main-grid">
      ${renderSpoiledBlanksTable()}
      ${renderPatientConsentsTable()}
    </div>
  `;
}

async function openDemoDocument(typeOrId, options = {}) {
  const { autoOpenFile = false } = options;
  const existingDocument =
    data.documents?.find((documentItem) => String(documentItem.id) === String(typeOrId)) ||
    data.generatedDocuments?.find((documentItem) => String(documentItem.id) === String(typeOrId));
  let documentItem = existingDocument;

  try {
    documentItem = documentItem || await createDemoDocument(typeOrId);
  } catch (error) {
    showToast(error.message || "Не удалось сформировать документ");
    return;
  }

  if (!documentItem) {
    showToast("Сначала выбери клиента и обращение");
    return;
  }

  if (documentItem.downloadUrl && (autoOpenFile || isContractDocument(documentItem))) {
    try {
      if (await openGeneratedDocumentInBrowser(documentItem)) {
        showToast(`Открыт документ: ${documentItem.title}`);
        return;
      }
    } catch (error) {
      showToast(humanizeApiError(error, "Не удалось открыть документ"));
    }
  }

  openActionModal(
    documentItem.title,
    `
      <div class="document-preview">
        <strong>${escapeHtml(documentItem.fileName || documentItem.title)}</strong>
        <p>${escapeHtml(documentItem.content || "Документ сформирован на сервере.")}</p>
      </div>
      <div class="client-create-actions">
        ${documentItem.downloadUrl ? '<button type="button" class="primary-button" id="printDocumentPreview">Открыть Word</button>' : ""}
        ${documentItem.downloadUrl ? '<button type="button" class="ghost-button" id="openDocumentPreview">Открыть без печати</button>' : ""}
        <button type="button" class="primary-button" id="closeDocumentPreview">ОК</button>
      </div>
    `,
  );

  document.getElementById("printDocumentPreview")?.addEventListener("click", async () => {
    const targetWindow = window.open("about:blank", "_blank");
    try {
      await openGeneratedDocumentDirectly(documentItem, { targetWindow });
      showToast("Документ открыт");
    } catch (error) {
      if (targetWindow && !targetWindow.closed) {
        targetWindow.close();
      }
      showToast(humanizeApiError(error, "Не удалось открыть документ"));
    }
  });

  document.getElementById("openDocumentPreview")?.addEventListener("click", async () => {
    try {
      if (!(await openGeneratedDocumentInBrowser(documentItem))) {
        showToast("Браузер заблокировал окно документа. Разрешите всплывающие окна для демо.");
      }
    } catch (error) {
      showToast(humanizeApiError(error, "Не удалось открыть документ"));
    }
  });

  document.getElementById("closeDocumentPreview")?.addEventListener("click", () => {
    actionModal.classList.add("hidden");
    renderApp();
  });
}

function parseCalendarDate(value) {
  if (!value) return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  const text = String(value).trim();
  const ruMatch = text.match(/^(\d{2})\.(\d{2})\.(\d{4}|\d{2})/);
  if (ruMatch) {
    const year = ruMatch[3].length === 2 ? expandTwoDigitYear(ruMatch[3]) : ruMatch[3];
    const date = new Date(Number(year), Number(ruMatch[2]) - 1, Number(ruMatch[1]));
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatCalendarDate(value) {
  const date = parseCalendarDate(value);
  if (!date) return "";
  return date.toLocaleDateString("ru-RU", RU_DATE_FORMAT_OPTIONS);
}

function getCalendarStatusMeta(item) {
  if (item.status === "called") return { label: "Обзвонили", className: "done" };
  if (item.status === "skipped") return { label: "Пропуск", className: "skipped" };
  if (item.status === "rescheduled") return { label: "Перенесено", className: "rescheduled" };
  if (Number(item.days_left) < 0) return { label: "Просрочено", className: "overdue" };
  if (Number(item.days_left) === 0) return { label: "Сегодня", className: "today" };
  if (Number(item.days_left) <= 7) return { label: "Скоро", className: "soon" };
  return { label: "В плане", className: "planned" };
}

function getFallbackRecallDays(serviceName) {
  const text = String(serviceName || "").toLowerCase();
  if (!text) return null;
  if (text.includes("бассейн")) return 180;
  if (
    text.includes("водител") ||
    text.includes("гимс") ||
    text.includes("трактор") ||
    text.includes("лмк") ||
    text.includes("флюор") ||
    text.includes("086") ||
    text.includes("095") ||
    text.includes("гто") ||
    text.includes("экг") ||
    text.includes("профосмотр")
  ) {
    return 365;
  }
  return null;
}

function buildLocalRecallItems() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const items = [];
  const clients = getClientPool();

  data.visits.forEach((visit) => {
    const client = clients.find((item) => String(item.id) === String(visit.clientId));
    if (!client) return;
    const encounterDate = parseCalendarDate(visit.visitDate || visit.createdAt);
    if (!encounterDate) return;

    (visit.serviceNames || []).forEach((serviceName) => {
      const service = getServerServiceByName(serviceName);
      const recallAfterDays = Number(service?.recallAfterDays || getFallbackRecallDays(serviceName) || 0);
      if (!recallAfterDays) return;
      const plannedDate = new Date(encounterDate);
      plannedDate.setDate(plannedDate.getDate() + recallAfterDays);
      plannedDate.setHours(0, 0, 0, 0);
      const daysLeft = Math.round((plannedDate - today) / 86400000);
      if (daysLeft > 45) return;

      items.push({
        client_id: client.backendId || client.id,
        patient_number: client.patientNumber,
        full_name: client.fullName,
        phone: client.phone,
        encounter_id: visit.backendId || visit.id,
        encounter_date: encounterDate.toISOString().slice(0, 10),
        service_id: service?.backendId || service?.id || null,
        service_name: serviceName,
        service_category_id: service?.groupId || null,
        service_category_name: serviceGroups.find((group) => String(group.id) === String(service?.groupId))?.name || null,
        recall_after_days: recallAfterDays,
        planned_date: plannedDate.toISOString().slice(0, 10),
        days_left: daysLeft,
        status: "planned",
        comment: "",
        localOnly: true,
      });
    });
  });

  return items.sort((a, b) => String(a.planned_date).localeCompare(String(b.planned_date)));
}

function getVisibleRecallItems() {
  const source = data.recallItemsLoaded ? data.recallItems : buildLocalRecallItems();
  return source.filter((item) => {
    if (
      appState.calendarServiceGroupFilter !== "all" &&
      String(item.service_category_id || "") !== String(appState.calendarServiceGroupFilter)
    ) {
      return false;
    }
    if (appState.calendarFilter === "all") return true;
    if (appState.calendarFilter === "done") return item.status === "called" || item.status === "skipped";
    if (appState.calendarFilter === "overdue") return Number(item.days_left) < 0 && item.status !== "called";
    return item.status !== "called" && item.status !== "skipped";
  });
}

async function loadRecallCalendar() {
  data.recallItemsLoading = true;
  data.recallItemsError = "";
  renderApp();
  try {
    data.recallItems = await apiRequest("/recalls/due?horizon_days=45&include_done=true");
    data.recallItemsLoaded = true;
  } catch (error) {
    data.recallItemsError = humanizeApiError(error, "Не удалось загрузить календарь сроков");
  } finally {
    data.recallItemsLoading = false;
    renderApp();
  }
}

async function loadReportsSummary() {
  if (!canAccessReportsWorkspace()) {
    data.reportLoading = false;
    data.reportError = "Отчеты доступны только председателю.";
    renderApp();
    return;
  }

  data.reportLoading = true;
  data.reportError = "";
  renderApp();
  try {
    const dateFrom = normalizeCashFilterDate(appState.reportDateFrom) || getLocalDateInputValue();
    const dateTo = normalizeCashFilterDate(appState.reportDateTo) || dateFrom;
    const [fromValue, toValue] = dateFrom <= dateTo ? [dateFrom, dateTo] : [dateTo, dateFrom];
    data.reportSummary = await apiRequest(
      `/reports/daily-summary?date_from=${encodeURIComponent(fromValue)}&date_to=${encodeURIComponent(toValue)}`,
    );
  } catch (error) {
    data.reportError = humanizeApiError(error, "Не удалось загрузить отчет");
  } finally {
    data.reportLoading = false;
    renderApp();
  }
}

async function markRecall(item, status) {
  if (item.localOnly || !item.service_id || !item.encounter_id) {
    showToast("Сначала сохрани обращение в базе, потом можно отмечать обзвон");
    return;
  }

  const commentMap = {
    called: "Обзвонили",
    skipped: "Пропуск",
    rescheduled: "Перенесено на 7 дней",
  };
  const nextPlannedDate = parseCalendarDate(item.planned_date) || new Date();
  if (status === "rescheduled") {
    nextPlannedDate.setDate(nextPlannedDate.getDate() + 7);
  }

  try {
    await apiRequest("/recalls/mark", {
      method: "POST",
      body: JSON.stringify({
        client_id: Number(item.client_id),
        encounter_id: Number(item.encounter_id),
        service_id: Number(item.service_id),
        planned_date: status === "rescheduled" ? nextPlannedDate.toISOString().slice(0, 10) : item.planned_date,
        status,
        comment: commentMap[status] || "",
      }),
    });
    await loadRecallCalendar();
    showToast(commentMap[status] || "Статус обновлен");
  } catch (error) {
    showToast(humanizeApiError(error, "Не удалось обновить статус"));
  }
}

function renderRecallCalendarPage() {
  const source = data.recallItemsLoaded ? data.recallItems : buildLocalRecallItems();
  const items = getVisibleRecallItems();
  const totalActive = source.filter((item) => item.status !== "called" && item.status !== "skipped");
  const overdue = totalActive.filter((item) => Number(item.days_left) < 0);
  const week = totalActive.filter((item) => Number(item.days_left) >= 0 && Number(item.days_left) <= 7);
  const calendarGroups = getSortedServiceGroups().filter((group) =>
    source.some((item) => String(item.service_category_id || "") === String(group.id)),
  );

  return `
    <section class="calendar-page">
      <div class="calendar-page__header">
        <div>
          <h3>Календарь сроков</h3>
        </div>
      </div>

      <div class="calendar-summary">
        <div><span>Активные</span><strong>${totalActive.length}</strong></div>
        <div><span>Просрочено</span><strong>${overdue.length}</strong></div>
        <div><span>На 7 дней</span><strong>${week.length}</strong></div>
      </div>

      <div class="calendar-filters">
        ${[
          ["active", "Активные"],
          ["overdue", "Просрочено"],
          ["done", "Отмеченные"],
          ["all", "Все"],
        ]
          .map(
            ([id, label]) => `
              <button class="${appState.calendarFilter === id ? "active" : ""}" data-calendar-filter="${id}">
                ${label}
              </button>
            `,
          )
          .join("")}
      </div>

      <div class="calendar-filters calendar-filters--groups">
        <button class="${appState.calendarServiceGroupFilter === "all" ? "active" : ""}" data-calendar-service-group="all">
          Все услуги
        </button>
        ${calendarGroups
          .map(
            (group) => `
              <button
                class="${String(appState.calendarServiceGroupFilter) === String(group.id) ? "active" : ""}"
                data-calendar-service-group="${group.id}"
              >
                ${escapeHtml(group.name)}
              </button>
            `,
          )
          .join("")}
      </div>

      ${
        data.recallItemsLoading
          ? `<div class="card"><p class="muted">Загружаю сроки...</p></div>`
          : data.recallItemsError
            ? `<div class="card"><p class="muted">${escapeHtml(data.recallItemsError)}</p></div>`
            : items.length
              ? `
                <div class="calendar-list">
                  ${items
                    .map((item, index) => {
                      const meta = getCalendarStatusMeta(item);
                      return `
                        <article class="calendar-row">
                          <div class="calendar-row__date">
                            <strong>${escapeHtml(formatCalendarDate(item.planned_date))}</strong>
                            <span>${Number(item.days_left) < 0 ? `${Math.abs(Number(item.days_left))} дн. назад` : `через ${Number(item.days_left)} дн.`}</span>
                          </div>
                          <div class="calendar-row__main">
                            <button class="calendar-row__client" data-calendar-client-id="${escapeHtml(item.client_id)}">
                              ${escapeHtml(item.full_name)}
                            </button>
                            <span>${escapeHtml(item.service_name)}</span>
                            <small>${escapeHtml(item.service_category_name || "Без группы")}</small>
                            <small>Оформлено: ${escapeHtml(formatCalendarDate(item.encounter_date))}. Срок: ${Number(item.recall_after_days)} дн.</small>
                          </div>
                          <div class="calendar-row__phone">${escapeHtml(item.phone || "телефон не указан")}</div>
                          <div class="calendar-status calendar-status--${meta.className}">${meta.label}</div>
                          <div class="calendar-actions">
                            <button type="button" data-recall-action="called" data-recall-index="${index}">Обзвонили</button>
                            <button type="button" data-recall-action="skipped" data-recall-index="${index}">Пропуск</button>
                            <button type="button" data-recall-action="rescheduled" data-recall-index="${index}">Перенести</button>
                          </div>
                        </article>
                      `;
                    })
                    .join("")}
                </div>
              `
              : `<div class="card"><p class="muted">На ближайшие 45 дней сроков нет.</p></div>`
      }
    </section>
  `;
}

function renderContent() {
  if (appState.page === "dashboard") return renderSketchHome();
  if (appState.page === "chart") return renderAmbulatoryCardPage();
  if (appState.page === "services" && window.renderServicesPage) return window.renderServicesPage();
  if (appState.page === "calendar") return renderRecallCalendarPage();
  if (appState.page === "upload") return renderClientImportPage();
  if (appState.page === "doctors") return renderDoctorsPage();
  if (appState.page === "templates") return renderTemplatesPage();
  if (appState.page === "blanks") return renderDocumentsPage();
  if (appState.page === "cash") return renderCashPage();
  if (appState.page === "reports") return renderReportsPage();
  if (appState.page === "employee") return renderEmployeePage();

  const item = navItems.find((navItem) => navItem.id === appState.page);
  return renderStubPage(item?.label || "Раздел");
}

function openActionModal(title, html, className = "") {
  if (!actionModalTitle || !actionModalContent || !actionModal) return;
  actionModal.className = "modal hidden";
  if (className) {
    actionModal.classList.add(className);
  }
  actionModalTitle.textContent = repairDemoText(title);
  actionModalContent.innerHTML = repairDemoText(html);
  actionModal.classList.remove("hidden");
}

function formatDateInput(value) {
  const digits = String(value || "").replace(/\D/g, "").slice(0, 8);
  const parts = [];
  if (digits.slice(0, 2)) parts.push(digits.slice(0, 2));
  if (digits.slice(2, 4)) parts.push(digits.slice(2, 4));
  if (digits.slice(4, 8)) parts.push(digits.slice(4, 8));
  return parts.join(".");
}

function attachDateMask(root) {
  root.querySelectorAll("[data-date-mask]").forEach((input) => {
    input.addEventListener("input", (event) => {
      const nextValue = formatDateInput(event.target.value);
      event.target.value = nextValue;
    });
  });
}

let activeDatePicker = null;
let activeDatePickerInput = null;

const DATE_PICKER_WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const DATE_PICKER_MONTHS = [
  "январь",
  "февраль",
  "март",
  "апрель",
  "май",
  "июнь",
  "июль",
  "август",
  "сентябрь",
  "октябрь",
  "ноябрь",
  "декабрь",
];

function parseDateInputValue(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return new Date();
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(date.getTime()) ? new Date() : date;
}

function closeCustomDatePicker() {
  activeDatePicker?.remove();
  activeDatePicker = null;
  activeDatePickerInput = null;
}

function positionCustomDatePicker(input, picker) {
  const rect = input.getBoundingClientRect();
  picker.style.minWidth = `${Math.max(252, Math.ceil(rect.width))}px`;
  picker.style.left = `${Math.round(rect.left + window.scrollX)}px`;
  picker.style.top = `${Math.round(rect.bottom + window.scrollY + 6)}px`;

  const pickerRect = picker.getBoundingClientRect();
  const maxLeft = window.scrollX + window.innerWidth - pickerRect.width - 12;
  if (rect.left + pickerRect.width > window.innerWidth - 12) {
    picker.style.left = `${Math.max(12 + window.scrollX, Math.round(maxLeft))}px`;
  }
}

function renderCustomDatePickerMonth(input, monthDate) {
  if (!activeDatePicker || activeDatePickerInput !== input) return;

  const selectedValue = input.value;
  const todayValue = getLocalDateInputValue();
  const year = monthDate.getFullYear();
  const month = monthDate.getMonth();
  const firstDate = new Date(year, month, 1);
  const startOffset = (firstDate.getDay() + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  activeDatePicker.innerHTML = "";

  const header = document.createElement("div");
  header.className = "native-date-picker__header";

  const prevButton = document.createElement("button");
  prevButton.type = "button";
  prevButton.className = "native-date-picker__nav";
  prevButton.setAttribute("aria-label", "Предыдущий месяц");
  prevButton.textContent = "<";

  const title = document.createElement("div");
  title.className = "native-date-picker__title";
  title.textContent = `${DATE_PICKER_MONTHS[month]} ${year}`;

  const nextButton = document.createElement("button");
  nextButton.type = "button";
  nextButton.className = "native-date-picker__nav";
  nextButton.setAttribute("aria-label", "Следующий месяц");
  nextButton.textContent = ">";

  header.append(prevButton, title, nextButton);
  activeDatePicker.append(header);

  const grid = document.createElement("div");
  grid.className = "native-date-picker__grid";

  DATE_PICKER_WEEKDAYS.forEach((weekday) => {
    const cell = document.createElement("span");
    cell.className = "native-date-picker__weekday";
    cell.textContent = weekday;
    grid.append(cell);
  });

  for (let index = 0; index < startOffset; index += 1) {
    const spacer = document.createElement("span");
    spacer.className = "native-date-picker__spacer";
    grid.append(spacer);
  }

  for (let day = 1; day <= daysInMonth; day += 1) {
    const date = new Date(year, month, day);
    const value = getLocalDateInputValue(date);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "native-date-picker__day";
    if (value === selectedValue) button.classList.add("native-date-picker__day--selected");
    if (value === todayValue) button.classList.add("native-date-picker__day--today");
    button.textContent = String(day);
    button.addEventListener("click", () => {
      input.value = value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      closeCustomDatePicker();
    });
    grid.append(button);
  }

  activeDatePicker.append(grid);
  positionCustomDatePicker(input, activeDatePicker);

  prevButton.addEventListener("click", () => renderCustomDatePickerMonth(input, new Date(year, month - 1, 1)));
  nextButton.addEventListener("click", () => renderCustomDatePickerMonth(input, new Date(year, month + 1, 1)));
}

function openCustomDatePicker(input) {
  if (!input || input.disabled || input.readOnly) return;

  if (activeDatePickerInput === input && activeDatePicker) {
    positionCustomDatePicker(input, activeDatePicker);
    return;
  }

  closeCustomDatePicker();
  activeDatePickerInput = input;
  activeDatePicker = document.createElement("div");
  activeDatePicker.className = "native-date-picker";
  activeDatePicker.setAttribute("role", "dialog");
  activeDatePicker.setAttribute("aria-label", "Выбор даты");
  document.body.append(activeDatePicker);

  const selectedDate = parseDateInputValue(input.value);
  renderCustomDatePickerMonth(input, new Date(selectedDate.getFullYear(), selectedDate.getMonth(), 1));
}

function openNativeDatePicker(input) {
  if (!input || input.disabled || input.readOnly) return;
  openCustomDatePicker(input);
}

function attachNativeDatePickers(root) {
  root.querySelectorAll('input[type="date"]').forEach((input) => {
    if (input.dataset.nativeDatePickerBound === "true") return;
    input.dataset.nativeDatePickerBound = "true";

    input.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      input.focus({ preventScroll: true });
      openNativeDatePicker(input);
    });
    input.addEventListener("click", (event) => event.preventDefault());
    input.addEventListener("focus", () => openNativeDatePicker(input));
  });
}

document.addEventListener("pointerdown", (event) => {
  if (!activeDatePicker) return;
  if (event.target === activeDatePickerInput || activeDatePicker.contains(event.target)) return;
  closeCustomDatePicker();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeCustomDatePicker();
});

window.addEventListener("scroll", () => {
  if (activeDatePicker && activeDatePickerInput) {
    positionCustomDatePicker(activeDatePickerInput, activeDatePicker);
  }
}, true);

function getPageTitle() {
  if (appState.page === "dashboard") return "Главная";
  return navItems.find((item) => item.id === appState.page)?.label || "Главная";
}

function applyColumnResizeState() {
  if (!window.__columnWidths) return;
  Object.entries(window.__columnWidths).forEach(([key, width]) => {
    document.documentElement.style.setProperty(`--excel-col-${key}`, `${width}px`);
  });
}

function focusClientSearch() {
  const hasDoctorModalOpen = !!window.appState?.doctorExamModal?.isOpen;
  const hasActionModalOpen = actionModal && !actionModal.classList.contains("hidden");

  if (hasDoctorModalOpen || hasActionModalOpen) return;

  const input = document.getElementById("clientSearchInput");
  if (!input) return;

  input.focus();
  const caretPosition = input.value.length;
  input.setSelectionRange(caretPosition, caretPosition);
}

function updateDashboardStickyOffset() {
  if (appState.page !== "dashboard") {
    document.documentElement.style.removeProperty("--dashboard-sticky-offset");
    return;
  }

  const controls = contentRoot?.querySelector(".dashboard-sticky-controls");
  if (!controls) {
    document.documentElement.style.removeProperty("--dashboard-sticky-offset");
    return;
  }

  const height = Math.ceil(controls.getBoundingClientRect().height);
  document.documentElement.style.setProperty("--dashboard-sticky-offset", `${height}px`);
}

function bindDashboardTableScrollSync() {
  const headScroller = contentRoot?.querySelector("[data-dashboard-head-scroll]");
  const bodyScroller = contentRoot?.querySelector("[data-dashboard-table-scroll]");
  if (!headScroller || !bodyScroller) return;

  let isSyncing = false;
  const syncScroll = (source, target) => {
    if (isSyncing) return;
    isSyncing = true;
    target.scrollLeft = source.scrollLeft;
    window.requestAnimationFrame(() => {
      isSyncing = false;
    });
  };

  headScroller.addEventListener("scroll", () => syncScroll(headScroller, bodyScroller), { passive: true });
  bodyScroller.addEventListener("scroll", () => syncScroll(bodyScroller, headScroller), { passive: true });
}

function bindColumnResize() {
  const handles = contentRoot.querySelectorAll(".col-resize-handle");
  handles.forEach((handle) => {
    handle.addEventListener("mousedown", (event) => {
      event.preventDefault();
      const key = handle.dataset.resizeCol;
      const currentWidthValue = getComputedStyle(document.documentElement).getPropertyValue(`--excel-col-${key}`).trim();
      const initialWidth = Number.parseInt(currentWidthValue, 10) || 80;
      const startX = event.clientX;

      const onMove = (moveEvent) => {
        const nextWidth = Math.max(22, initialWidth + moveEvent.clientX - startX);
        window.__columnWidths = window.__columnWidths || {};
        window.__columnWidths[key] = nextWidth;
        document.documentElement.style.setProperty(`--excel-col-${key}`, `${nextWidth}px`);
      };

      const onUp = () => {
        persistColumnWidths();
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };

      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    });
  });
}

function readOperatorVisitForm(form) {
  const formData = new FormData(form);
  const serviceIds = Array.from(form.querySelectorAll('input[name="visitService"]:checked'))
    .map((input) => String(input.value || ""))
    .filter(Boolean);
  const serviceNames = serviceIds
    .map((serviceId) => getServiceById(serviceId)?.name)
    .filter(Boolean);
  const currentVisit = data.visits.find((item) => String(item.id) === String(form.dataset.visitId));
  const existingDetails = getVisitServiceDetails(currentVisit);
  const serviceDetails = {};

  serviceIds.forEach((serviceId) => {
    const service = getServiceById(serviceId);
    const previous = existingDetails[String(serviceId)] || {};
    serviceDetails[String(serviceId)] = {
      ...previous,
      unitPrice: Number(previous.unitPrice ?? service?.price ?? 0),
    };
  });

  const driverServiceId = serviceIds.find((serviceId) => isDriverService(getServiceById(serviceId)));
  if (driverServiceId) {
    const categories = Array.from(form.querySelectorAll('input[name="driverCategory"]:checked'))
      .map((input) => input.value)
      .filter(Boolean);
    const normalizedCategories = normalizeDriverCategories(categories);
    const driverPriceInput = String(formData.get("driverPrice") || "").replace(",", ".");
    serviceDetails[driverServiceId] = {
      ...(serviceDetails[driverServiceId] || {}),
      categories: normalizedCategories,
      unitPrice: Number(driverPriceInput) || getDriverCategoryPrice(normalizedCategories),
      autoDoctorRoles: getDriverRoleCodes(normalizedCategories),
    };
  }

  return {
    visitDate: String(formData.get("visitDate") || "").trim(),
    center: String(formData.get("center") || "").trim(),
    paymentType: String(formData.get("paymentType") || "Наличные").trim(),
    amount: Number(String(formData.get("amount") || "0").replace(",", ".")) || 0,
    comment: String(formData.get("comment") || "").trim(),
    serviceNames,
    serviceIds,
    serviceDetails,
  };
}

async function saveOperatorVisitForm({ recalculate = false, close = false } = {}) {
  const form = document.getElementById("operatorVisitForm");
  if (!form) return null;

  const selectedClient = getSelectedClient();
  const visitId = form.dataset.visitId;
  const patch = readOperatorVisitForm(form);

  if (recalculate) {
    patch.amount = calculateVisitAmountByIds(patch.serviceIds, patch.serviceDetails);
  }

  if (close) {
    patch.status = "closed";
    patch.closedAt = new Date().toISOString();
  }

  const visit = updateVisit(visitId, patch);
  syncClientServicesFromVisit(selectedClient, visit);
  if (!visit || !selectedClient) return visit;

  await syncVisitToBackend(visit, selectedClient);
  await ensureRequiredDoctorExamsForVisit(selectedClient, visit, { syncToBackend: true });
  await loadDashboardDoctorStatuses([selectedClient], { render: false });

  const autoDocumentConfig =
    !recalculate &&
    !close &&
    Boolean(visit.backendId)
      ? getAutoGeneratedMedicalDocumentConfig(visit)
      : null;

  if (autoDocumentConfig) {
    if (!data.documentTemplatesLoaded) {
      await loadDocumentTemplatesFromBackend();
    }
    const template = pickDocumentTemplate("medical", visit, selectedClient);
    if (template) {
        try {
          let documentItem = null;
          if (!hasGeneratedTemplateForVisit(visit, template)) {
            documentItem = await createDocumentForVisit("medical", selectedClient, visit);
          } else {
          documentItem =
            getDocumentsForVisit(visit.id).find((item) => String(item.templateId || "") === String(template.id)) || null;
        }

        appState.page = "blanks";
          await loadWorkflowData({
            clientId: selectedClient?.backendId || selectedClient?.id || null,
            encounterId: visit.backendId || null,
          });
          if (documentItem?.id) {
            appState.pendingAutoOpenDocumentId = documentItem.id;
            visit.__saveFeedbackToast = autoDocumentConfig.toast;
          }
        } catch (error) {
          console.warn("Failed to auto-generate medical document", error);
          showToast(error.message || autoDocumentConfig.errorMessage);
        }
    }
  }

  return visit;
}

function renderAppKeepingOperatorVisitPosition(form) {
  const formTop = form?.getBoundingClientRect().top ?? null;
  const serviceListScrollTop = form?.querySelector(".operator-service-list")?.scrollTop ?? 0;

  renderApp();

  const nextForm = document.getElementById("operatorVisitForm");
  if (nextForm && formTop !== null) {
    window.scrollBy(0, nextForm.getBoundingClientRect().top - formTop);
  }

  const nextServiceList = nextForm?.querySelector(".operator-service-list");
  if (nextServiceList) {
    nextServiceList.scrollTop = serviceListScrollTop;
  }
}

function bindContentEvents() {
  attachNativeDatePickers(contentRoot);

  const cashDateFromInput = document.getElementById("cashDateFrom");
  if (cashDateFromInput) {
    cashDateFromInput.addEventListener("input", (event) => {
      appState.cashDateFrom = event.target.value;
      persistDemoState();
      renderApp();
    });
  }

  const cashDateToInput = document.getElementById("cashDateTo");
  if (cashDateToInput) {
    cashDateToInput.addEventListener("input", (event) => {
      appState.cashDateTo = event.target.value;
      persistDemoState();
      renderApp();
    });
  }

  const cashPeriodTodayButton = document.getElementById("cashPeriodTodayButton");
  if (cashPeriodTodayButton) {
    cashPeriodTodayButton.addEventListener("click", () => {
      resetCashPeriodToToday();
      persistDemoState();
      renderApp();
    });
  }

  const reportDateFromInput = document.getElementById("reportDateFrom");
  if (reportDateFromInput) {
    reportDateFromInput.addEventListener("input", (event) => {
      appState.reportDateFrom = event.target.value;
      persistDemoState();
      loadReportsSummary();
    });
  }

  const reportDateToInput = document.getElementById("reportDateTo");
  if (reportDateToInput) {
    reportDateToInput.addEventListener("input", (event) => {
      appState.reportDateTo = event.target.value;
      persistDemoState();
      loadReportsSummary();
    });
  }

  const reportPeriodTodayButton = document.getElementById("reportPeriodTodayButton");
  if (reportPeriodTodayButton) {
    reportPeriodTodayButton.addEventListener("click", () => {
      const today = getLocalDateInputValue();
      appState.reportDateFrom = today;
      appState.reportDateTo = today;
      persistDemoState();
      loadReportsSummary();
    });
  }

  const clientSearchInput = document.getElementById("clientSearchInput");
  if (clientSearchInput) {
    clientSearchInput.value = formatClientSearchInputValue(clientSearchInput.value);
    clientSearchInput.addEventListener("input", (event) => {
      const formattedValue = formatClientSearchInputValue(event.target.value);
      const cursorPosition = event.target.selectionStart || formattedValue.length;
      if (event.target.value !== formattedValue) {
        event.target.value = formattedValue;
        event.target.setSelectionRange(cursorPosition, cursorPosition);
      }
      appState.clientSearch = formattedValue;
      appState.dashboardPage = 1;
      scheduleClientSearch(formattedValue, { render: false });
      rerenderAndRestoreInput("clientSearchInput", formattedValue, event.target.selectionStart || formattedValue.length);
    });
  }

  const applyClientPeriodFilterButton = document.getElementById("applyClientPeriodFilterButton");
  if (applyClientPeriodFilterButton) {
    applyClientPeriodFilterButton.addEventListener("click", () => {
      appState.clientEncounterDate = "";
      appState.clientEncounterDateFrom = document.getElementById("clientEncounterDateFromInput")?.value || "";
      appState.clientEncounterDateTo = document.getElementById("clientEncounterDateToInput")?.value || "";
      appState.dashboardPage = 1;
      appState.selectedClientId = null;
      appState.activeVisitId = null;
      persistDemoState();
      scheduleClientSearch(appState.clientSearch || "");
    });
  }

  const clearClientPeriodFilterButton = document.getElementById("clearClientPeriodFilterButton");
  if (clearClientPeriodFilterButton) {
    clearClientPeriodFilterButton.addEventListener("click", () => {
      appState.clientEncounterDate = "";
      appState.clientEncounterDateFrom = "";
      appState.clientEncounterDateTo = getLocalDateInputValue();
      appState.dashboardPage = 1;
      appState.selectedClientId = null;
      appState.activeVisitId = null;
      persistDemoState();
      scheduleClientSearch(appState.clientSearch || "");
    });
  }

  contentRoot.querySelectorAll("[data-dashboard-page]").forEach((button) => {
    button.addEventListener("click", async () => {
      const nextPage = Number(button.dataset.dashboardPage || 1);
      if (!Number.isFinite(nextPage) || nextPage < 1 || nextPage === appState.dashboardPage) return;
      appState.dashboardPage = nextPage;
      persistDemoState();
      await loadDashboardDoctorStatuses(getVisibleDashboardClients());
    });
  });

  const addClientButton = document.getElementById("addClientButton");
  if (addClientButton) {
    addClientButton.addEventListener("click", () => {
      if (window.openClientModal) {
        window.openClientModal();
      }
    });
  }

  const createVisitFromDashboardButton = document.getElementById("createVisitFromDashboardButton");
  if (createVisitFromDashboardButton) {
    createVisitFromDashboardButton.addEventListener("click", () => {
      const selectedClient = getSelectedClient();
      if (!selectedClient) {
        showToast("Сначала выбери клиента");
        return;
      }
      if (window.openClientModal) {
        window.openClientModal(selectedClient.id, { encounterMode: true });
      }
    });
  }

  const editSelectedClientButton = document.getElementById("editSelectedClientButton");
  if (editSelectedClientButton) {
    editSelectedClientButton.addEventListener("click", () => {
      if (window.openClientModal) {
        window.openClientModal(appState.selectedClientId);
      }
    });
  }

  const openAmbulatoryCardButton = document.getElementById("openAmbulatoryCardButton");
  if (openAmbulatoryCardButton) {
    openAmbulatoryCardButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      openAmbulatoryCardForCurrentClient();
    });
  }

  const chartBackToDashboard = document.getElementById("chartBackToDashboard");
  if (chartBackToDashboard) {
    chartBackToDashboard.addEventListener("click", () => {
      appState.page = "dashboard";
      renderApp();
    });
  }

  const chartEditClientButton = document.getElementById("chartEditClientButton");
  if (chartEditClientButton) {
    chartEditClientButton.addEventListener("click", () => {
      if (window.openClientModal) {
        window.openClientModal(appState.selectedClientId);
      }
    });
  }

  const editMedicalRecordButton = document.getElementById("editMedicalRecordButton");
  if (editMedicalRecordButton) {
    editMedicalRecordButton.addEventListener("click", () => {
      data.medicalRecordEditMode = true;
      data.medicalRecordSaveError = "";
      renderApp();
    });
  }

  const cancelMedicalRecordEditButton = document.getElementById("cancelMedicalRecordEditButton");
  if (cancelMedicalRecordEditButton) {
    cancelMedicalRecordEditButton.addEventListener("click", () => {
      data.medicalRecordEditMode = false;
      data.medicalRecordSaveError = "";
      renderApp();
    });
  }

  const ambulatoryCardForm = document.getElementById("ambulatoryCardForm");
  if (ambulatoryCardForm && data.medicalRecordEditMode) {
    attachDateMask(ambulatoryCardForm);
    ambulatoryCardForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      await saveMedicalRecordForm();
    });
  }

  const addServiceButton = document.getElementById("addServiceButton");
  if (addServiceButton) {
    addServiceButton.addEventListener("click", () => window.openServiceModal?.());
  }

  const clientImportFileInput = document.getElementById("clientImportFileInput");
  if (clientImportFileInput) {
    clientImportFileInput.addEventListener("change", async (event) => {
      const file = event.target.files?.[0];
      if (!file) return;
      data.importLoading = true;
      data.importFileName = file.name;
      resetClientImportState();
      renderApp();
      try {
        data.importFileBase64 = await fileToBase64(file);
        showToast(`Файл выбран: ${file.name}`);
      } catch (error) {
        data.importFileBase64 = "";
        data.importError = "Не удалось прочитать файл";
      } finally {
        data.importLoading = false;
        renderApp();
      }
    });
  }

  const previewClientImportButton = document.getElementById("previewClientImportButton");
  if (previewClientImportButton) {
    previewClientImportButton.addEventListener("click", () => previewClientImport());
  }

  const commitClientImportButton = document.getElementById("commitClientImportButton");
  if (commitClientImportButton) {
    commitClientImportButton.addEventListener("click", () => commitClientImport());
  }

  const refreshRecallCalendar = document.getElementById("refreshRecallCalendar");
  if (refreshRecallCalendar) {
    refreshRecallCalendar.addEventListener("click", () => loadRecallCalendar());
  }

  contentRoot.querySelectorAll("[data-calendar-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      appState.calendarFilter = button.dataset.calendarFilter || "active";
      persistDemoState();
      renderApp();
    });
  });

  contentRoot.querySelectorAll("[data-calendar-service-group]").forEach((button) => {
    button.addEventListener("click", () => {
      appState.calendarServiceGroupFilter = button.dataset.calendarServiceGroup || "all";
      persistDemoState();
      renderApp();
    });
  });

  contentRoot.querySelectorAll("[data-recall-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = getVisibleRecallItems()[Number(button.dataset.recallIndex)];
      if (!item) return;
      markRecall(item, button.dataset.recallAction);
    });
  });

  contentRoot.querySelectorAll("[data-calendar-client-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      appState.selectedClientId = Number(button.dataset.calendarClientId);
      if (!getClientPool().some((client) => String(client.id) === String(appState.selectedClientId))) {
        try {
          const loadedClient = await apiRequest(`/clients/${appState.selectedClientId}`);
          upsertClientInMemory(mapApiClient(loadedClient));
        } catch (error) {
          showToast(humanizeApiError(error, "Не удалось открыть клиента"));
          return;
        }
      }
      appState.page = "dashboard";
      appState.activeVisitId = getCurrentVisitForClient(appState.selectedClientId)?.id || null;
      persistDemoState();
      renderApp();
      await loadClientWorkspace(getSelectedClient());
    });
  });

  const createVisitButton = document.getElementById("createVisitButton");
  if (createVisitButton) {
    createVisitButton.addEventListener("click", () => {
      const selectedClient = getSelectedClient();
      if (!selectedClient) {
        showToast("Сначала выбери клиента");
        return;
      }
      if (window.openClientModal) {
        window.openClientModal(selectedClient.id, { encounterMode: true });
      }
    });
  }

  const operatorVisitForm = document.getElementById("operatorVisitForm");
    if (operatorVisitForm) {
      operatorVisitForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const visit = await saveOperatorVisitForm();
        renderApp();
        if (appState.pendingAutoOpenDocumentId) {
          const pendingDocumentId = appState.pendingAutoOpenDocumentId;
          delete appState.pendingAutoOpenDocumentId;
          window.setTimeout(() => {
            openDemoDocument(pendingDocumentId);
          }, 0);
        }
        const feedback = visit?.__saveFeedbackToast || "Обращение сохранено";
        if (visit && "__saveFeedbackToast" in visit) {
          delete visit.__saveFeedbackToast;
        }
        showToast(feedback);
    });

    operatorVisitForm.querySelectorAll('input[name="visitService"]').forEach((checkbox) => {
      checkbox.addEventListener("change", async () => {
        const patch = readOperatorVisitForm(operatorVisitForm);
        const amountInput = operatorVisitForm.querySelector('input[name="amount"]');
        if (amountInput) amountInput.value = String(calculateVisitAmountByIds(patch.serviceIds, patch.serviceDetails));
        await saveOperatorVisitForm({ recalculate: true });
        renderAppKeepingOperatorVisitPosition(operatorVisitForm);
      });
    });

    operatorVisitForm.querySelectorAll('input[name="driverCategory"]').forEach((checkbox) => {
      checkbox.addEventListener("change", async () => {
        const patch = readOperatorVisitForm(operatorVisitForm);
        const amountInput = operatorVisitForm.querySelector('input[name="amount"]');
        if (amountInput) amountInput.value = String(calculateVisitAmountByIds(patch.serviceIds, patch.serviceDetails));
        await saveOperatorVisitForm({ recalculate: true });
        renderAppKeepingOperatorVisitPosition(operatorVisitForm);
      });
    });
  }

  const visitServiceSearchInput = document.getElementById("visitServiceSearchInput");
  if (visitServiceSearchInput) {
    visitServiceSearchInput.addEventListener("input", async (event) => {
      await saveOperatorVisitForm();
      appState.visitServiceSearch = event.target.value;
      rerenderAndRestoreInput("visitServiceSearchInput", event.target.value, event.target.selectionStart || event.target.value.length);
    });
  }

  contentRoot.querySelectorAll("[data-visit-service-group]").forEach((button) => {
    button.addEventListener("click", async () => {
      await saveOperatorVisitForm();
      appState.visitServiceGroupFilter = button.dataset.visitServiceGroup;
      renderApp();
    });
  });

  const recalculateVisitAmountButton = document.getElementById("recalculateVisitAmountButton");
  if (recalculateVisitAmountButton) {
    recalculateVisitAmountButton.addEventListener("click", async () => {
      await saveOperatorVisitForm({ recalculate: true });
      renderApp();
      showToast("Сумма пересчитана по выбранным услугам");
    });
  }

  const openVisitDocumentsButton = document.getElementById("openVisitDocumentsButton");
  if (openVisitDocumentsButton) {
    openVisitDocumentsButton.addEventListener("click", async () => {
      const visit = await saveOperatorVisitForm();
      const selectedClient = getSelectedClient();
      appState.page = "blanks";
      await loadWorkflowData({
        clientId: selectedClient?.backendId || selectedClient?.id || null,
        encounterId: visit?.backendId || null,
      });
      if (typeof window.loadBlanksData === "function") {
        await window.loadBlanksData({ force: true });
      }
      renderApp();
      showToast("Открыты документы по обращению");
    });
  }

  const closeVisitButton = document.getElementById("closeVisitButton");
  if (closeVisitButton) {
    closeVisitButton.addEventListener("click", async () => {
      await saveOperatorVisitForm({ close: true });
      renderApp();
      showToast("Обращение завершено");
    });
  }

  const openEmployeeLoginButton = document.getElementById("openEmployeeLogin");
  if (openEmployeeLoginButton) {
    openEmployeeLoginButton.addEventListener("click", () => {
      loginModal?.classList.remove("hidden");
    });
  }

  const refreshEmployeeStaffButton = document.getElementById("refreshEmployeeStaff");
  if (refreshEmployeeStaffButton) {
    refreshEmployeeStaffButton.addEventListener("click", async () => {
      await loadStaffWorkspace();
      showToast("Список сотрудников обновлен");
    });
  }

  const employeeCreateForm = document.getElementById("employeeCreateForm");
  if (employeeCreateForm) {
    employeeCreateForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(employeeCreateForm);
      await createDemoStaffUser({
        full_name: String(formData.get("full_name") || "").trim(),
        login: String(formData.get("login") || "").trim(),
        password: String(formData.get("password") || "").trim(),
        email: String(formData.get("email") || "").trim(),
        role_code: String(formData.get("role_code") || "").trim(),
      });
    });
  }

  contentRoot.querySelectorAll("[data-delete-staff-user]").forEach((button) => {
    button.addEventListener("click", async () => {
      const userId = Number(button.dataset.deleteStaffUser || 0);
      const userName = button.dataset.deleteStaffName || "сотрудник";
      if (!userId) return;
      const confirmed = window.confirm(`Удалить сотрудника "${userName}"?`);
      if (!confirmed) return;
      await deleteDemoStaffUser(userId, userName);
    });
  });

  const employeeSignOutButton = document.getElementById("employeeSignOut");
  if (employeeSignOutButton) {
    employeeSignOutButton.addEventListener("click", () => {
      appState.auth = {
        accessToken: "",
        userName: "",
        roleCode: "",
        roleName: "",
      };
      data.staffUsers = [];
      data.staffRoles = [];
      data.staffError = "";
      data.staffCreateError = "";
      appState.page = "employee";
      renderApp();
      persistDemoState();
      showToast("Вы вышли из режима сотрудника");
    });
  }

  contentRoot.querySelectorAll("[data-select-visit-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      appState.activeVisitId = button.dataset.selectVisitId;
      persistDemoState();
      renderApp();
      await loadDoctorExamsForClient(getSelectedClient(), getCurrentVisitForClient(appState.selectedClientId));
      await loadWorkflowData();
      renderApp();
    });
  });

  contentRoot.querySelectorAll("[data-generate-document]").forEach((button) => {
    button.addEventListener("click", () => {
      const documentType = button.dataset.generateDocument;
      if (documentType === "driver") {
        openDriverPrintFlow();
        return;
      }
      openDemoDocument(documentType);
    });
  });

  contentRoot.querySelectorAll("[data-open-document-id]").forEach((button) => {
    button.addEventListener("click", () => {
      openDemoDocument(button.dataset.openDocumentId);
    });
  });

  contentRoot.querySelectorAll("[data-service-group]").forEach((button) => {
    button.addEventListener("click", () => {
      appState.serviceGroupFilter = button.dataset.serviceGroup;
      renderApp();
    });
  });

  contentRoot.querySelectorAll("[data-service-id]").forEach((button) => {
    button.addEventListener("click", () => {
      window.openServiceModal?.(button.dataset.serviceId);
    });
  });

  contentRoot.querySelectorAll("[data-client-id]").forEach((button) => {
    button.addEventListener("dblclick", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (clientRowClickTimer) {
        window.clearTimeout(clientRowClickTimer);
        clientRowClickTimer = null;
      }
      const nextClientId = Number(button.dataset.clientId);
      appState.selectedClientId = nextClientId;
      appState.activeVisitId = getCurrentVisitForClient(appState.selectedClientId)?.id || null;
      persistDemoState();
      let selectedClient = getSelectedClient();
      try {
        selectedClient = await ensureFullClientLoaded(selectedClient);
      } catch (error) {
        showToast(humanizeApiError(error, "Не удалось загрузить карточку клиента"));
        return;
      }
      if (selectedClient) await openAmbulatoryCardForCurrentClient();
    });

    button.addEventListener("click", async (event) => {
      event.preventDefault();
      const doctorCell = event.target.closest("[data-row-doctor-role-id]");
      const doctorRoleId = doctorCell?.dataset.rowDoctorRoleId || "";
      const nextClientId = Number(button.dataset.clientId);
      const wasSameSelectedClient = String(appState.selectedClientId) === String(nextClientId);
      if (
        doctorRoleId &&
        Number(window.__suppressDoctorCellClickUntil || 0) > Date.now()
      ) {
        return;
      }
      if (!doctorRoleId) {
        if (clientRowClickTimer) window.clearTimeout(clientRowClickTimer);
        clientRowClickTimer = window.setTimeout(async () => {
          clientRowClickTimer = null;
          appState.selectedClientId = nextClientId;
          appState.activeVisitId = getCurrentVisitForClient(appState.selectedClientId)?.id || null;
          persistDemoState();
          renderApp();
          let selectedClient = getSelectedClient();
          try {
            selectedClient = await ensureFullClientLoaded(selectedClient);
          } catch (error) {
            showToast(humanizeApiError(error, "Не удалось загрузить карточку клиента"));
            return;
          }
          renderApp();
          if (!wasSameSelectedClient) {
            await loadClientWorkspace(selectedClient);
          }
        }, CLIENT_ROW_SINGLE_CLICK_DELAY);
        return;
      }
      if (clientRowClickTimer) {
        window.clearTimeout(clientRowClickTimer);
        clientRowClickTimer = null;
      }
      appState.selectedClientId = nextClientId;
      appState.activeVisitId = getCurrentVisitForClient(appState.selectedClientId)?.id || null;
      persistDemoState();
      renderApp();
      let selectedClient = getSelectedClient();
      try {
        selectedClient = await ensureFullClientLoaded(selectedClient);
      } catch (error) {
        showToast(humanizeApiError(error, "Не удалось загрузить карточку клиента"));
        return;
      }
      renderApp();
      if (!doctorRoleId || !wasSameSelectedClient) {
        await loadClientWorkspace(selectedClient);
      }

      if (selectedClient && doctorRoleId) {
        const activeVisit = getCurrentVisitForClient(selectedClient.id) || getOrCreateDraftVisit(selectedClient.id);
        if (doctorRoleId === "print") {
          await openDriverPrintFlow();
          return;
        }
        await loadDoctorExamsForClient(selectedClient, activeVisit);
        const currentExam = getDoctorExam(selectedClient.id, activeVisit.id, doctorRoleId);
        if (currentExam?.isCompleted) {
          openCompletedDoctorExamActions({ selectedClient, activeVisit, doctorRoleId, currentExam });
          return;
        }
        openDoctorExamCard({
          clientId: selectedClient.id,
          visitId: activeVisit.id,
          doctorRoleId,
        });
      }
    });
  });

  contentRoot.querySelectorAll("[data-doctor-role-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const doctorRoleId = button.dataset.doctorRoleId;
      const selectedClient = getSelectedClient();

      if (!selectedClient) {
        showToast("Сначала выбери клиента");
        return;
      }

      if (!doctorRoleId) {
        const label = button.dataset.doctorLabel || "врач";
        showToast(`Для "${label}" шаблон пока не добавлен`);
        return;
      }

      const activeVisit = getOrCreateDraftVisit(selectedClient.id);
      await loadDoctorExamsForClient(selectedClient, activeVisit);
      openDoctorExamCard({
        clientId: selectedClient.id,
        visitId: activeVisit.id,
        doctorRoleId,
      });
    });
  });

  contentRoot.querySelectorAll("[data-template-preview-role-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const doctorRoleId = button.dataset.templatePreviewRoleId;
      const previewClient = getSelectedClient() || getClientPool()[0];

      if (!previewClient) {
        showToast("Нет клиента для предпросмотра формы");
        return;
      }

      appState.selectedClientId = previewClient.id;
      await loadDoctorExamsForClient(previewClient, getCurrentVisitForClient(previewClient.id));
      openDoctorExamCard({
        clientId: previewClient.id,
        doctorRoleId,
      });
    });
  });

  contentRoot.querySelector("[data-refresh-document-templates]")?.addEventListener("click", async () => {
    data.templateOperationStatus = "Перечитываем шаблоны...";
    renderApp();
    try {
      await refreshDocumentTemplatesFromBackend();
    } catch (error) {
      data.templateOperationStatus = humanizeApiError(error, "Не удалось перечитать шаблоны");
      renderApp();
    }
  });

  contentRoot.querySelectorAll("[data-open-document-template]").forEach((button) => {
    button.addEventListener("click", async () => {
      const templateId = button.dataset.openDocumentTemplate;
      if (!templateId) return;
      try {
        if (!(await openAuthorizedFileUrl(buildTemplateFileUrl(templateId)))) {
          showToast("Браузер заблокировал окно шаблона. Разрешите всплывающие окна для демо.");
        }
      } catch (error) {
        showToast(humanizeApiError(error, "Не удалось открыть шаблон"));
      }
    });
  });

  contentRoot.querySelectorAll("[data-replace-document-template]").forEach((button) => {
    button.addEventListener("click", () => {
      const templateId = button.dataset.replaceDocumentTemplate;
      const input = document.getElementById("documentTemplateUploadInput");
      if (!templateId || !input) return;
      input.dataset.templateId = templateId;
      input.click();
    });
  });

  document.getElementById("documentTemplateUploadInput")?.addEventListener("change", async (event) => {
    const input = event.target;
    const templateId = input.dataset.templateId;
    const file = input.files?.[0];
    if (!templateId || !file) return;
    data.templateOperationStatus = "Загружаем новый файл шаблона...";
    renderApp();
    try {
      await replaceDocumentTemplateFile(templateId, file);
    } catch (error) {
      data.templateOperationStatus = humanizeApiError(error, "Не удалось обновить шаблон");
      renderApp();
    } finally {
      input.value = "";
    }
  });

  contentRoot.querySelectorAll("[data-doctor-name-input]").forEach((input) => {
    input.addEventListener("input", (event) => {
      setDoctorFullName(input.dataset.doctorNameInput, event.target.value);
      persistDemoState();
    });
  });

  contentRoot.querySelectorAll("[data-demo-toast]").forEach((button) => {
    button.addEventListener("click", () => showToast(button.dataset.demoToast));
  });

  contentRoot.querySelectorAll("[data-copy-value]").forEach((button) => {
    const copyValue = async (event) => {
      event.preventDefault();
      event.stopPropagation();
      await copyTextToClipboard(button.dataset.copyValue, button.dataset.copyMessage || "Скопировано");
    };
    button.addEventListener("click", copyValue);
    button.addEventListener("dblclick", (event) => {
      event.preventDefault();
      event.stopPropagation();
    });
    button.addEventListener("keydown", async (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      await copyValue(event);
    });
  });

  const chairmanForm = contentRoot.querySelector('.chairman-form[data-doctor-role-id="chairman"]');
  const chairmanActions = chairmanForm?.querySelector(".chairman-actions");
  if (chairmanForm && chairmanActions && !chairmanActions.querySelector("[data-chairman-print]")) {
    const createPrintButton = (label, kind) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chairman-action-btn";
      button.dataset.chairmanPrint = kind;
      button.textContent = label;
      return button;
    };
    const printButtons = [createPrintButton("Печать", "conclusion")];
    printButtons
      .slice()
      .reverse()
      .forEach((button) => chairmanActions.prepend(button));

    const handleChairmanPrint = async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const printKind = event.currentTarget?.dataset.chairmanPrint || "conclusion";
      const actionLabel = printKind === "extract" ? "выписка" : "документ";
      const currentButton = event.currentTarget;
      const targetWindow = window.open("about:blank", "_blank");

      const examId = chairmanForm.dataset.examId;
      if (!examId) {
        if (targetWindow && !targetWindow.closed) targetWindow.close();
        showToast("Не удалось подготовить печать из окна председателя");
        return;
      }

      if (currentButton) currentButton.disabled = true;
      const values = collectChairmanModalFormValues(chairmanForm);
      const saved = await window.saveDoctorExam?.(examId, values);
      if (!saved) {
        if (targetWindow && !targetWindow.closed) targetWindow.close();
        if (currentButton) currentButton.disabled = false;
        return;
      }

      const exam = data.doctorExams.find((item) => String(item.id) === String(examId));
      const client = exam
        ? getClientPool().find((item) => String(item.id) === String(exam.clientId))
        : getSelectedClient();
      const visit = exam
        ? data.visits.find((item) => String(item.id) === String(exam.visitId))
        : client
          ? getCurrentVisitForClient(client.id)
          : null;
      const printType = getChairmanTemplatePrintType(visit, printKind);
      const formInfo = getChairmanFormInfo(visit, client);
      const numberedCertificateSeries = getChairmanNumberedCertificateSeries(printType);
      const certificatePrintFlowOptions = getChairmanCertificatePrintFlowOptions(printType);

      if (formInfo.printMode === "driver-flow" || numberedCertificateSeries || certificatePrintFlowOptions) {
        if (targetWindow && !targetWindow.closed) targetWindow.close();
        window.closeDoctorExamCard?.();
        await window.openDriverPrintFlow?.({
          ...(certificatePrintFlowOptions || {}),
          ...(numberedCertificateSeries
            ? {
                preselectedSeries: numberedCertificateSeries,
                certificateTypes: printType ? [printType] : [],
                selectedCertificateType: printType || "",
                compactCertificateFlow: true,
              }
            : {}),
        });
        return;
      }

      if (formInfo.printMode !== "driver-flow" && printType) {
        try {
          const documentItem = await printDocumentForVisit(printType, client, visit, { targetWindow });
          window.closeDoctorExamCard?.();
          showToast(`Документ открыт: ${documentItem?.title || actionLabel}`);
        } catch (error) {
          if (targetWindow && !targetWindow.closed) targetWindow.close();
          console.error(error);
          if (currentButton) currentButton.disabled = false;
          showToast(humanizeApiError(error, `Не удалось отправить ${actionLabel} в печать`));
        }
        return;
      }

      window.closeDoctorExamCard?.();
      await window.openDriverPrintFlow?.();
    };

    printButtons.forEach((button) => button.addEventListener("click", handleChairmanPrint));
  }

  window.bindBlanksHandlers?.();
  bindColumnResize();
  window.bindServiceCardHandlers?.();
}

function bindMedicalRecordPanelResize() {
  const panel = document.querySelector("[data-medical-record-panel]");
  const handle = document.querySelector("[data-medical-record-resize]");
  if (!panel || !handle || handle.dataset.bound === "true") return;

  handle.dataset.bound = "true";
  handle.addEventListener("mousedown", (event) => {
    event.preventDefault();
    const startY = event.clientY;
    const startHeight = panel.getBoundingClientRect().height;

    const onMove = (moveEvent) => {
      const nextHeight = Math.min(520, Math.max(160, startHeight + (moveEvent.clientY - startY)));
      panel.style.height = `${nextHeight}px`;
    };

    const onUp = () => {
      persistMedicalRecordPanelHeight(panel.getBoundingClientRect().height);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  });
}

function renderApp() {
  _clientPoolCache = null;
  if (appState.page === "reports" && !canAccessReportsWorkspace()) {
    appState.page = appState.auth.accessToken ? "employee" : "dashboard";
  }
  document.body.dataset.page = appState.page;

  if (authStatusLabel) {
    authStatusLabel.textContent = repairDemoText(
      appState.auth.accessToken
        ? `${appState.auth.userName || "Сотрудник"} · ${appState.auth.roleName || "Без роли"}`
        : "Гость",
    );
  }

  if (pageTitle) {
    pageTitle.textContent = repairDemoText(getPageTitle());
  }

  renderNav();

  if (contentRoot) {
    contentRoot.innerHTML = repairDemoText(`
      ${renderContent()}
      ${window.renderDoctorExamModal ? window.renderDoctorExamModal() : ""}
      ${window.renderServiceCardModals ? window.renderServiceCardModals() : ""}
    `);
  }

  applyColumnResizeState();
  bindMedicalRecordPanelResize();
  bindContentEvents();
  bindDashboardTableScrollSync();
  window.requestAnimationFrame(updateDashboardStickyOffset);

  if (appState.page === "dashboard" && !appState.restoreInputId) {
    window.setTimeout(focusClientSearch, 0);
  }
}

window.addEventListener("resize", () => {
  window.requestAnimationFrame(updateDashboardStickyOffset);
});

if (centerSelect) {
  centerSelect.addEventListener("change", (event) => {
    appState.centerFilter = event.target.value;
    appState.dashboardPage = 1;
    persistDemoState();
    renderApp();
  });
}

const showLoginButton = document.getElementById("showLogin");
if (showLoginButton) {
  showLoginButton.addEventListener("click", () => {
    loginModal?.classList.remove("hidden");
  });
}

document.getElementById("performLogin")?.addEventListener("click", async () => {
  const login = document.getElementById("loginInput")?.value || "";
  const password = document.getElementById("passwordInput")?.value || "";

  try {
    await loginDemoStaff(login, password);
    loginModal?.classList.add("hidden");
    showToast(`Вход выполнен: ${appState.auth.userName || login}`);
    if (appState.page === "employee" || appState.auth.roleCode === "admin" || appState.auth.roleCode === "chairman") {
      appState.page = "employee";
      await loadStaffWorkspace();
    } else {
      renderApp();
    }
  } catch (error) {
    showToast(humanizeApiError(error, "Не удалось войти"));
  }
});

document.getElementById("closeLogin")?.addEventListener("click", () => {
  loginModal?.classList.add("hidden");
});

document.getElementById("closeAction")?.addEventListener("click", () => {
  actionModal?.classList.add("hidden");
});

loginModal?.querySelector(".modal__backdrop")?.addEventListener("click", () => {
  loginModal.classList.add("hidden");
});

actionModal?.querySelector(".modal__backdrop")?.addEventListener("click", () => {
  actionModal.classList.add("hidden");
});

window.appState = appState;
window.data = data;
window.getSelectedClient = getSelectedClient;
window.getClientPool = getClientPool;
window.getDoctorTemplate = getDoctorTemplate;
window.getDoctorExam = getDoctorExam;
window.getDoctorExamById = getDoctorExamById;
window.getOrCreateDoctorExam = getOrCreateDoctorExam;
window.getOrCreateDraftVisit = getOrCreateDraftVisit;
window.getCurrentVisitForClient = getCurrentVisitForClient;
window.createVisitForClient = createVisitForClient;
window.createVisitForClientIfNeeded = createVisitForClientIfNeeded;
window.updateVisit = updateVisit;
window.ensureRequiredDoctorExamsForVisit = ensureRequiredDoctorExamsForVisit;
window.calculateVisitAmount = calculateVisitAmount;
window.calculateVisitAmountByIds = calculateVisitAmountByIds;
window.persistDemoState = persistDemoState;
window.markClientChanged = markClientChanged;
window.markServicesChanged = markServicesChanged;
window.openDoctorExamCard = openDoctorExamCard;
window.closeDoctorExamCard = closeDoctorExamCard;
window.saveDoctorExam = saveDoctorExam;
window.saveDoctorExamDraft = saveDoctorExamDraft;
window.deleteDoctorExam = deleteDoctorExam;
window.uncompleteDoctorExam = uncompleteDoctorExam;
window.openDemoDocument = openDemoDocument;
window.createDemoDocument = createDemoDocument;
window.printChairmanDocumentFromExam = printChairmanDocumentFromExam;
window.getChairmanFormInfo = getChairmanFormInfo;
window.openChairmanTemplateFile = openChairmanTemplateFile;
window.API_BASE_URL = API_BASE_URL;
window.apiRequest = apiRequest;
window.humanizeApiError = humanizeApiError;
window.mapApiService = mapApiService;
window.mapApiClient = mapApiClient;
window.upsertClientInMemory = upsertClientInMemory;
window.showClientInDashboardResults = showClientInDashboardResults;
window.parseRuDateToIso = parseRuDateToIso;
window.loadDashboardDoctorStatuses = loadDashboardDoctorStatuses;
window.loadServicesFromBackend = loadServicesFromBackend;
window.compareServicesForOperator = compareServicesForOperator;
window.getServiceById = getServiceById;
window.showToast = showToast;
window.escapeHtml = escapeHtml;
window.renderApp = renderApp;
window.openDriverPrintFlow = openDriverPrintFlow;

renderApp();
Promise.allSettled([loadClientsFromBackend(appState.clientSearch), loadServicesFromBackend(), loadDocumentTemplatesFromBackend()])
  .then(() => restoreWorkplaceSelection());
