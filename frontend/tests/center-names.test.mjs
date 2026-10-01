import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");

const OPENERS = { "(": ")", "[": "]", "{": "}" };
const CLOSERS = new Set([")", "]", "}"]);

// Вырезает объявление верхнего уровня целиком, считая скобки.
function extractDeclaration(name) {
  const start = ["function " + name + "(", "const " + name + " ="]
    .map((marker) => appSource.indexOf(marker))
    .find((index) => index >= 0);
  assert.ok(typeof start === "number", `Не найдено объявление ${name}`);

  let depth = 0;
  for (let index = start; index < appSource.length; index += 1) {
    const char = appSource[index];
    if (OPENERS[char]) depth += 1;
    else if (CLOSERS.has(char)) {
      depth -= 1;
      if (depth === 0 && char === "}") return appSource.slice(start, index + 1);
    } else if (char === ";" && depth === 0) return appSource.slice(start, index + 1);
  }
  assert.fail(`Не удалось вырезать объявление ${name}`);
}

function loadRenamer() {
  const context = vm.createContext({});
  vm.runInContext(
    `${extractDeclaration("LEGACY_CENTER_NAMES")}
${extractDeclaration("renameLegacyCentersInSavedState")}
this.renameLegacyCentersInSavedState = renameLegacyCentersInSavedState;`,
    context,
  );
  return context.renameLegacyCentersInSavedState;
}

test("сохранение вкладки со старыми названиями центров переезжает на новые", () => {
  const rename = loadRenamer();
  const saved = {
    appState: { centerFilter: "Медцентр 2" },
    createdClients: [{ id: 1, center: "Медцентр 1" }, { id: 2, center: "" }],
    visits: [{ id: 5, center: "Медцентр 2" }, { id: 6, center: "Медилэнд" }],
    clientOverrides: { 1: { id: 1, center: "Медцентр 1" }, 2: { id: 2, phone: "1" } },
    doctorDirectoryByCenter: {
      "Медцентр 1": { therapist: "Иванов И.И." },
      "Медцентр 2": { therapist: "Петров П.П." },
    },
  };

  rename(saved);

  assert.equal(saved.appState.centerFilter, "Медилэнд");
  assert.deepEqual(
    saved.createdClients.map((client) => client.center),
    ["Мед-Авто", ""],
  );
  assert.deepEqual(
    saved.visits.map((visit) => visit.center),
    ["Медилэнд", "Медилэнд"],
  );
  assert.equal(saved.clientOverrides[1].center, "Мед-Авто");
  assert.equal(saved.clientOverrides[2].center, undefined);
  assert.deepEqual(saved.doctorDirectoryByCenter, {
    "Мед-Авто": { therapist: "Иванов И.И." },
    "Медилэнд": { therapist: "Петров П.П." },
  });
});

test("справочник врачей под новым названием не затирается кэшем под старым", () => {
  const rename = loadRenamer();
  const saved = {
    doctorDirectoryByCenter: {
      "Медцентр 1": { therapist: "Старый" },
      "Мед-Авто": { therapist: "Новый" },
    },
  };

  rename(saved);

  assert.deepEqual(saved.doctorDirectoryByCenter, { "Мед-Авто": { therapist: "Новый" } });
});

test("сохранение без центров и с чужими названиями не ломается", () => {
  const rename = loadRenamer();

  const empty = {};
  rename(empty);
  assert.deepEqual(empty, {});

  const custom = { appState: { centerFilter: "Другой центр" }, visits: [null, "text", { center: 7 }] };
  rename(custom);
  assert.equal(custom.appState.centerFilter, "Другой центр");
  assert.deepEqual(custom.visits, [null, "text", { center: 7 }]);
});
