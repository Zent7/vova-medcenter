function getServiceGroupName(groupId) {
  return serviceGroups.find((group) => String(group.id) === String(groupId))?.name || "Без группы";
}

function getDoctorRoleNames(ids = []) {
  if (!Array.isArray(ids) || !ids.length) return "—";
  return ids
    .map((id) => doctorRoles.find((role) => String(role.id) === String(id))?.name)
    .filter(Boolean)
    .join(", ");
}

function formatPrice(value) {
  const number = Number(value || 0);
  return `${number.toLocaleString("ru-RU")} ₽`;
}

function formatRecallDays(value) {
  const days = Number(value || 0);
  if (!days) return "не задан";
  return `${days} дн.`;
}

function getNextServiceId() {
  return structuredServices.length
    ? Math.max(...structuredServices.map((service) => Number(service.id) || 0)) + 1
    : 1;
}

function renderServicesPage() {
  const groups = serviceGroups
    .filter((group) => group.isActive !== false)
    .slice()
    .sort((a, b) => (a.sortOrder || 0) - (b.sortOrder || 0));

  const services = structuredServices
    .filter((service) => {
      if (service.isActive === false) return false;
      if (appState.serviceGroupFilter === "all") return true;
      return String(service.groupId) === String(appState.serviceGroupFilter);
    })
    .slice();

  if (!structuredServices.length) {
    return `
      <section class="card">
        <p class="muted">Данные услуг пока не подключены.</p>
      </section>
    `;
  }

  return `
    <section class="card services-page">
      <div class="services-page__header">
        <div>
          <p class="muted" style="margin:6px 0 0 0;">Справочник услуг для выбора и настройки</p>
        </div>
      </div>

      <div class="sketch-doctors sketch-doctors--top" style="margin-bottom:16px;">
        <button
          class="doctor-pill ${appState.serviceGroupFilter === "all" ? "active" : ""}"
          data-service-group="all"
        >
          Все
        </button>

        ${groups
          .map(
            (group) => `
              <button
                class="doctor-pill ${String(appState.serviceGroupFilter) === String(group.id) ? "active" : ""}"
                data-service-group="${group.id}"
              >
                ${escapeHtml(group.name)}
              </button>
            `,
          )
          .join("")}
        <button class="primary-button services-add-inline" id="addServiceButton">Добавить услугу</button>
      </div>

      <div class="services-table">
        <div class="services-table__grid services-table__grid--head">
          <span class="sketch-head-cell sketch-head-cell--resizable">
            ID
            <button class="col-resize-handle" data-resize-col="serviceId" aria-label="Изменить ширину столбца ID"></button>
          </span>
          <span class="sketch-head-cell sketch-head-cell--resizable">
            Наименование
            <button class="col-resize-handle" data-resize-col="serviceName" aria-label="Изменить ширину столбца Наименование"></button>
          </span>
          <span class="sketch-head-cell sketch-head-cell--resizable">
            Группа
            <button class="col-resize-handle" data-resize-col="serviceGroup" aria-label="Изменить ширину столбца Группа"></button>
          </span>
          <span class="sketch-head-cell sketch-head-cell--resizable">
            Цена
            <button class="col-resize-handle" data-resize-col="servicePrice" aria-label="Изменить ширину столбца Цена"></button>
          </span>
          <span class="sketch-head-cell sketch-head-cell--resizable">
            Срок действия
            <button class="col-resize-handle" data-resize-col="serviceRecall" aria-label="Изменить ширину столбца Срок действия"></button>
          </span>
          <span class="sketch-head-cell sketch-head-cell--resizable">
            Примечание
            <button class="col-resize-handle" data-resize-col="serviceNote" aria-label="Изменить ширину столбца Примечание"></button>
          </span>
          <span class="sketch-head-cell sketch-head-cell--resizable">
            Врачи
            <button class="col-resize-handle" data-resize-col="serviceDoctors" aria-label="Изменить ширину столбца Врачи"></button>
          </span>
          <span class="sketch-head-cell sketch-head-cell--resizable">
            Статус
            <button class="col-resize-handle" data-resize-col="serviceStatus" aria-label="Изменить ширину столбца Статус"></button>
          </span>
        </div>

        ${
          services.length
            ? services
                .map(
                  (service) => `
                    <button
                      class="services-table__grid services-table__grid--row"
                      data-service-id="${service.id}"
                    >
                      <span>${service.id}</span>
                      <span>${escapeHtml(service.name)}</span>
                      <span>${escapeHtml(getServiceGroupName(service.groupId))}</span>
                      <span>${formatPrice(service.price)}</span>
                      <span>${escapeHtml(formatRecallDays(service.recallAfterDays))}</span>
                      <span>${escapeHtml(service.notes || "—")}</span>
                      <span>${escapeHtml(getDoctorRoleNames(service.doctorRoleIds))}</span>
                      <span>${service.isActive ? "Активна" : "Выключена"}</span>
                    </button>
                  `,
                )
                .join("")
            : `<div class="empty">По выбранной группе услуг не найдено</div>`
        }
      </div>
    </section>
  `;
}

function openServiceModal(serviceId = null) {
  const editingService = serviceId
    ? structuredServices.find((service) => String(service.id) === String(serviceId))
    : null;

  const selectedDoctorIds = new Set(
    Array.isArray(editingService?.doctorRoleIds) ? editingService.doctorRoleIds.map((id) => String(id)) : [],
  );

  openActionModal(
    editingService ? "Редактировать услугу" : "Новая услуга",
    `
      <form class="client-create-form" id="serviceCreateForm">
        <div class="client-create-grid client-create-grid--top">
          <label class="field field--wide">
            <span>Наименование</span>
            <input name="name" value="${escapeHtml(editingService?.name || "")}" />
          </label>

          <label class="field">
            <span>Группа</span>
            <select name="groupId">
              ${serviceGroups
                .slice()
                .sort((a, b) => (a.sortOrder || 0) - (b.sortOrder || 0))
                .map(
                  (group) => `
                    <option value="${group.id}" ${String(editingService?.groupId ?? "") === String(group.id) ? "selected" : ""}>
                      ${escapeHtml(group.name)}
                    </option>
                  `,
                )
                .join("")}
            </select>
          </label>

          <label class="field">
            <span>Цена</span>
            <input name="price" type="number" min="0" step="100" value="${escapeHtml(editingService?.price ?? 0)}" />
          </label>

          <label class="field">
            <span>Срок действия, дней</span>
            <input name="recallAfterDays" type="number" min="0" step="1" value="${escapeHtml(editingService?.recallAfterDays ?? "")}" placeholder="например 365" />
          </label>
        </div>

        <label class="field">
          <span>Примечание</span>
          <textarea name="notes" rows="2">${escapeHtml(editingService?.notes || "")}</textarea>
        </label>

        <div class="client-services-block">
          <div class="client-services-block__title">Врачи, входящие в услугу</div>
          <div class="client-services-list">
            ${doctorRoles
              .slice()
              .sort((a, b) => (a.sortOrder || 0) - (b.sortOrder || 0))
              .map(
                (role) => `
                  <label class="client-service-chip">
                    <input
                      type="checkbox"
                      name="doctorRoleIds"
                      value="${role.id}"
                      ${selectedDoctorIds.has(String(role.id)) ? "checked" : ""}
                    />
                    <span>${escapeHtml(role.name)}</span>
                  </label>
                `,
              )
              .join("")}
          </div>
        </div>

        <label class="field" style="margin-top:12px;">
          <span>Статус</span>
          <select name="isActive">
            <option value="true" ${editingService?.isActive !== false ? "selected" : ""}>Активна</option>
            <option value="false" ${editingService?.isActive === false ? "selected" : ""}>Выключена</option>
          </select>
        </label>

        <div class="client-create-actions">
          <button type="button" class="ghost-button" id="cancelServiceCreate">Отмена</button>
          <button type="submit" class="primary-button">Сохранить</button>
        </div>
      </form>
    `,
  );

  const form = document.getElementById("serviceCreateForm");
  const cancel = document.getElementById("cancelServiceCreate");

  cancel?.addEventListener("click", () => {
    actionModal.classList.add("hidden");
  });

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(form);

    const targetService =
      editingService ||
      {
        id: getNextServiceId(),
        sortOrder:
          structuredServices.filter((service) => String(service.groupId) === String(formData.get("groupId"))).length * 10 + 10,
      };

    targetService.name = String(formData.get("name") || "").trim() || "Новая услуга";
    targetService.groupId = Number(formData.get("groupId"));
    targetService.price = Number(formData.get("price") || 0);
    targetService.recallAfterDays = formData.get("recallAfterDays")
      ? Number(formData.get("recallAfterDays"))
      : null;
    targetService.notes = String(formData.get("notes") || "").trim();
    targetService.isActive = String(formData.get("isActive")) === "true";
    targetService.doctorRoleIds = formData.getAll("doctorRoleIds").map((id) => Number(id));

    if (editingService?.backendId && window.apiRequest) {
      try {
        const updated = await window.apiRequest(`/services/${editingService.backendId}`, {
          method: "PUT",
          body: JSON.stringify({
            category_id: targetService.groupId,
            name: targetService.name,
            price: targetService.price,
            is_active: targetService.isActive,
            recall_after_days: targetService.recallAfterDays,
            doctor_role_ids: targetService.doctorRoleIds,
          }),
        });
        Object.assign(targetService, window.mapApiService ? window.mapApiService(updated) : targetService);
        const serverIndex = window.data?.serverServices?.findIndex((service) => String(service.backendId) === String(targetService.backendId));
        if (serverIndex >= 0) window.data.serverServices[serverIndex] = targetService;
      } catch (error) {
        showToast(window.humanizeApiError ? window.humanizeApiError(error, "Не удалось сохранить услугу") : "Не удалось сохранить услугу");
        return;
      }
    } else if (!editingService) {
      structuredServices.push(targetService);
    }

    window.markServicesChanged?.();

    actionModal.classList.add("hidden");
    renderApp();
    showToast(editingService ? "Услуга обновлена" : "Услуга добавлена");
  });
}

window.renderServicesPage = renderServicesPage;
window.openServiceModal = openServiceModal;
