import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { resolve } from "node:path";

const appSource = readFileSync(resolve(import.meta.dirname, "../public/demo/app.js"), "utf8");

function sourceBetween(startMarker, endMarker) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return appSource.slice(start, end);
}

test("template cards download the original file without a popup", () => {
  const templatePage = sourceBetween("function renderTemplatesPage", "function renderWorkflowLoadState");
  const handlers = sourceBetween(
    'contentRoot.querySelectorAll("[data-download-document-template]")',
    'contentRoot.querySelectorAll("[data-replace-document-template]")',
  );

  assert.match(templatePage, /data-download-document-template/);
  assert.match(templatePage, />Скачать<\/button>/);
  assert.match(handlers, /downloadAuthorizedFileUrl\(buildTemplateFileUrl\(templateId\), fileName\)/);
  assert.match(handlers, /template\?\.file_name/);
  assert.doesNotMatch(handlers, /openAuthorizedFileUrl/);
  assert.doesNotMatch(handlers, /всплывающие окна/);
});
