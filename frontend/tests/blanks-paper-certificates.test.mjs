import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(resolve(import.meta.dirname, "../public/demo/blanks-page.js"), "utf8");

function renderBlanks({ tab, forms = [], batches = [], filterType = "all" }) {
  const window = {
    appState: { page: "blanks", blanksTab: tab, blanksFilterType: filterType, blanksFilterStatus: "all" },
    data: {
      blanksTypes: [
        { code: "driver_medical_certificate", name: "Водительская" },
        { code: "gims_medical_certificate", name: "ГИМС" },
      ],
      blanksForms: forms,
      blanksFormsTotal: forms.length,
      blanksFormsLimit: 50,
      blanksFormsOffset: 0,
      blanksStats: [],
      blanksBatches: batches,
      blanksLoaded: true,
    },
    escapeHtml(value) {
      return String(value ?? "");
    },
    getWorkspaceCenterName() {
      return "Медцентр 1";
    },
  };
  vm.runInNewContext(source, { window, URLSearchParams, Date });
  return window.renderBlanksPage();
}

const driverBlank = {
  id: 1,
  blank_type: "driver_medical_certificate",
  series: "40",
  full_number: "400000001",
  status: "issued",
  client_full_name: "Иванов Иван",
  document_label: "водительская лицевая.xls",
  issued_at: "2026-09-30T10:00:00Z",
};
const gtoNumber = {
  id: 2,
  blank_type: "driver_medical_certificate",
  series: "ГТО",
  full_number: "ГТО0000120",
  status: "issued",
  is_paper_certificate: true,
  client_full_name: "Тест 263",
  document_label: "ГТО_шаблон.docx",
  issued_at: "2026-09-30T11:00:00Z",
};

function historyGroup(html, code) {
  const start = html.indexOf(`data-blank-history-group="${code}"`);
  assert.notEqual(start, -1, `нет группы ${code}`);
  const next = html.indexOf("data-blank-history-group=", start + 1);
  return html.slice(start, next === -1 ? undefined : next);
}

test("history keeps paper certificates out of the driver group", () => {
  const html = renderBlanks({ tab: "history", forms: [driverBlank, gtoNumber] });

  const driver = historyGroup(html, "driver_medical_certificate");
  const paper = historyGroup(html, "paper_certificates");
  assert.match(driver, /400000001/);
  assert.doesNotMatch(driver, /ГТО0000120/);
  assert.match(paper, /ГТО0000120/);
  assert.match(html, /Справки на бумаге/);
});

test("number list names paper certificates by their own type", () => {
  const html = renderBlanks({ tab: "forms", forms: [driverBlank, gtoNumber] });

  const rows = html.split("<tr>").filter((row) => row.includes("<td>"));
  const gtoRow = rows.find((row) => row.includes("ГТО0000120"));
  const driverRow = rows.find((row) => row.includes("400000001"));
  assert.match(gtoRow, /Справки на бумаге/);
  assert.doesNotMatch(gtoRow, /Водительская/);
  assert.match(driverRow, /Водительская/);
});

test("type filter offers paper certificates and keeps the choice", () => {
  const html = renderBlanks({ tab: "forms", forms: [gtoNumber], filterType: "paper_certificates" });

  assert.match(html, /<option value="paper_certificates" selected>Справки на бумаге<\/option>/);
});

test("batch list names paper certificate batches by their own type", () => {
  const html = renderBlanks({
    tab: "batches",
    batches: [
      { id: 1, blank_type: "driver_medical_certificate", series: "40", number_from: 1, number_to: 5, number_width: 7, quantity: 5 },
      {
        id: 2,
        blank_type: "driver_medical_certificate",
        series: "095У",
        number_from: 1,
        number_to: 3,
        number_width: 7,
        quantity: 3,
        is_paper_certificate: true,
      },
    ],
  });

  const rows = html.split("<tr>").filter((row) => row.includes("<td>"));
  assert.match(rows.find((row) => row.includes("095У")), /Справки на бумаге/);
  assert.match(rows.find((row) => row.includes("<td>40</td>")), /Водительская/);
});
