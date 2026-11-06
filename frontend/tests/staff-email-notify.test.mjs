import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// Почта для уведомлений админа: кнопка «Почта» в строке админа в «Сотрудники», форма с полем почты и
// сохранение через PUT /staff/{id}/email. Уведомления уходят на эти адреса, поэтому проверяем связку
// в app.js по исходнику: модуль работает только внутри программы.

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8").replace(/\r\n/g, "\n");

function functionBody(name) {
  const start = appSource.search(new RegExp(`(async )?function ${name}\\(`));
  assert.ok(start >= 0, `Не найдена функция ${name}`);
  let depth = 0;
  for (let index = appSource.indexOf("{", appSource.indexOf(")", start)); index < appSource.length; index += 1) {
    if (appSource[index] === "{") depth += 1;
    if (appSource[index] === "}") {
      depth -= 1;
      if (depth === 0) return appSource.slice(start, index + 1);
    }
  }
  assert.fail(`Не удалось вырезать функцию ${name}`);
}

test("строка админа: кнопка «Почта» и строка с адресом только у админов", () => {
  assert.match(appSource, /user\.role\?\.code === "admin" \? `<button class="ghost-button" type="button" data-edit-staff-email=/);
  assert.match(appSource, /Почта для уведомлений: \$\{escapeHtml\(user\.email \|\| "не указана"\)\}/);
  assert.match(appSource, /Number\(data\.editingStaffEmailId\) === Number\(user\.id\)\s*\? renderStaffEmailEditForm\(user\)/);
});

test("форма почты: поле email с проверкой формата и ограничением длины", () => {
  const form = functionBody("renderStaffEmailEditForm");
  assert.match(form, /<input type="email" name="email"/);
  assert.match(form, /maxlength="255"/);
  assert.match(form, /data-staff-email-form=/);
  assert.match(form, /data-cancel-staff-email/);
});

test("сохранение: PUT /staff/{id}/email, пустое поле убирает почту, ошибка остается в форме", () => {
  const save = functionBody("updateDemoStaffEmail");
  assert.match(save, /apiRequest\(`\/staff\/\$\{encodeURIComponent\(userId\)\}\/email`, \{\s*method: "PUT"/);
  assert.match(save, /JSON\.stringify\(\{ email: email \|\| null \}\)/);
  assert.match(save, /return humanizeApiError\(error, "Не удалось сохранить почту"\);/);

  const submit = appSource.slice(appSource.indexOf("[data-staff-email-form]"));
  assert.match(submit, /const error = await updateDemoStaffEmail\(userId, email\);/);
  assert.match(submit, /showStaffEmailEditError\(form, error\);/);
});

test("выход сбрасывает открытую форму почты", () => {
  const signOut = functionBody("signOutDemoStaff");
  assert.match(signOut, /data\.editingStaffEmailId = null;/);
});
