from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.certificate_number_range import CertificateNumberRange
from app.models.center import Center
from app.models.client import Client
from app.models.client_document import ClientDocument
from app.models.document_journal import DocumentJournalEntry
from app.models.document_template import DocumentTemplate
from app.models.encounter import Encounter
from app.models.encounter_service import EncounterService
from app.models.medical_record import MedicalRecord
from app.models.payment import Payment
from app.models.recall import Recall
from app.models.service import DoctorRole, Service, ServiceCategory, ServiceDoctorRole
from app.models.template_phrase import TemplatePhrase
from app.models.user import Role, User
from app.models.visit_type import VisitType, VisitTypeService
from app.services.template_catalog import sync_document_template_catalog, template_visit_type_code


SERVICE_GROUPS = [
    ("legacy-group-1", "Анализы", 10),
    ("legacy-group-2", "ВУ", 20),
    ("legacy-group-3", "ГИМС", 30),
    ("legacy-group-4", "ЛМК", 40),
    ("legacy-group-5", "Приём врачей", 50),
    ("legacy-group-6", "Профосмотры", 60),
    ("legacy-group-7", "Справки", 70),
    ("legacy-group-8", "УЗИ", 80),
    ("legacy-group-9", "ЭКГ", 90),
]

SERVICE_CATALOG = [
    (22, 1, "Анализы", "1000.00"),
    (8, 2, "Водительская справка", "4000.00"),
    (29, 2, "Водительская справка", "3500.00"),
    (7, 2, "071У", "4000.00"),
    (37, 3, "ГИМС", "3500.00"),
    (18, 4, "ЛМК", "4000.00"),
    (33, 4, "Направление на Флюорографию", "1000.00"),
    (19, 4, "Продление ЛМК", "3500.00"),
    (23, 4, "ФОТО для ЛМК", "200.00"),
    (35, 5, "Повторный приём врача НЕВРОЛОГА", "1800.00"),
    (36, 5, "Повторный приём врача НЕВРОЛОГА", "1800.00"),
    (34, 5, "Приём врача НЕВРОЛОГА", "2200.00"),
    (28, 5, "Приём врача ТЕРАПЕВТА", "2200.00"),
    (16, 6, "Первичный профосмотр 29Н", "3500.00"),
    (24, 7, "Санаторно-курортная карта 072У", "2500.00"),
    (2, 7, "Справка формы 001 ГСУ", "1800.00"),
    (9, 7, "Справка 002 ЧОД (для охраны)", "3500.00"),
    (3, 7, "Справка в бассейн", "1000.00"),
    (10, 7, "Справка выезжающих за границу 082у", "2000.00"),
    (11, 7, "Справка для работы с гостайной формы 989Н", "1800.00"),
    (4, 7, "Справка ГТО 1144", "1500.00"),
    (12, 7, "Справка формы 086у", "2200.00"),
    (30, 7, "095", "1800.00"),
    (5, 7, "спорт", "1200.00"),
    (13, 8, "УЗИ брюшной полости", "2000.00"),
    (14, 8, "УЗИ молочных желез", "1500.00"),
    (15, 8, "УЗИ предстательной железы", "1500.00"),
    (20, 9, "ЭКГ без расшифровки", "700.00"),
    (21, 9, "ЭКГ при нагрузке с расшифровкой", "1700.00"),
    (6, 9, "ЭКГ с расшифровкой", "1200.00"),
]

DOCTOR_ROLES = [
    (1, "therapist", "Терапевт", 10),
    (2, "psychiatrist", "Психиатр", 20),
    (3, "psychiatrist-narcologist", "Психиатр-Нарколог", 30),
    (4, "neurologist", "Невролог", 40),
    (5, "otolaryngologist", "Отоларинголог", 50),
    (6, "gynecologist", "Гинеколог", 60),
    (7, "ophthalmologist", "Офтальмолог", 70),
    (8, "dermatologist", "Дерматовенеролог", 80),
    (9, "dentist", "Стоматолог", 90),
    (10, "surgeon", "Хирург", 100),
    (11, "phthisiatrist", "Фтизиатр", 110),
    (12, "uzist", "Узист", 120),
    (13, "chairman", "Председатель", 130),
]

SERVICE_DOCTOR_ROLE_IDS = {
    35: [4],
    36: [4],
    34: [4],
    28: [1],
    16: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
}

SERVICE_RECALL_AFTER_DAYS = {
    8: 365,
    29: 365,
    7: 365,
    37: 365,
    18: 365,
    19: 365,
    33: 365,
    3: 180,
    4: 365,
    5: 365,
    6: 365,
    9: 365,
    10: 365,
    11: 365,
    12: 365,
    16: 365,
    20: 365,
    21: 365,
    24: 365,
    30: 365,
}

# The current working catalog mirrors the customer Excel file "для программы":
# order, prices, doctor appointments, and certificate validity.
SERVICE_GROUPS = [
    ("legacy-group-1", "Анализы", 10),
    ("legacy-group-2", "ВУ", 20),
    ("legacy-group-3", "ГИМС", 30),
    ("legacy-group-4", "ЛМК", 40),
    ("legacy-group-5", "Приём врачей", 50),
    ("legacy-group-6", "Профосмотры", 60),
    ("legacy-group-7", "Справки", 70),
    ("legacy-group-8", "УЗИ", 80),
    ("legacy-group-9", "ЭКГ", 90),
]

SERVICE_CATALOG = [
    (22, 1, "Анализы", "1000.00"),
    (8, 2, "Медицинская комиссия", "4000.00"),
    (29, 2, "Медицинская комиссия", "3500.00"),
    (18, 4, "ЛМК", "4000.00"),
    (19, 4, "Продление ЛМК", "3500.00"),
    (7, 2, "071У", "4000.00"),
    (37, 3, "Медкомиссия для управления маломерными судами", "3500.00"),
    (33, 4, "Направление на флюорографию", "1000.00"),
    (23, 4, "Фото для ЛМК", "200.00"),
    (28, 5, "Приём врача терапевта", "2200.00"),
    (34, 5, "Приём врача невролога", "2200.00"),
    (35, 5, "Повторный приём врача невролога", "1800.00"),
    (36, 5, "Повторный приём врача невролога дубль", "1800.00"),
    (16, 6, "Профосмотр", "3500.00"),
    (12, 7, "Справка формы 086у", "2200.00"),
    (2, 7, "Справка формы 001 ГСУ", "1800.00"),
    (11, 7, "Справка для работы с гостайной формы 989Н", "1800.00"),
    (4, 7, "Справка ГТО 1144", "1500.00"),
    (3, 7, "Справка для посещения бассейна", "1000.00"),
    (5, 7, "спорт", "1200.00"),
    (27, 9, "ЭКГ", "1200.00"),
    (30, 7, "095", "1800.00"),
    (24, 7, "Санаторно-курортная карта 072У", "2500.00"),
    (31, 7, "Справка для получения путевки 070У", "2000.00"),
    (10, 7, "Справка для выезжающих за границу 082у", "2000.00"),
    (32, 7, "капельница", "1500.00"),
    (38, 7, "Морская медицинская комиссия", "6000.00"),
    (39, 7, "DRUG/ALCOHOL TEST \u2116 96", "2500.00"),
    (40, 7, "Справка 342н (псих. освид.)", "1800.00"),
    (41, 7, "Выписка из амб. карты (профа)", "0.00"),
    (13, 8, "УЗИ брюшной полости", "2000.00"),
    (14, 8, "УЗИ молочных желез", "1500.00"),
    (15, 8, "УЗИ предстательной железы", "1500.00"),
    (20, 9, "ЭКГ без расшифровки", "700.00"),
    (21, 9, "ЭКГ при нагрузке с расшифровкой", "1700.00"),
    (6, 9, "ЭКГ с расшифровкой", "1200.00"),
]

DOCTOR_ROLES = [
    (1, "therapist", "Терапевт", 10),
    (2, "psychiatrist", "Психиатр", 20),
    (3, "psychiatrist-narcologist", "Психиатр-нарколог", 30),
    (4, "neurologist", "Невролог", 40),
    (5, "otolaryngologist", "Оториноларинголог", 50),
    (6, "gynecologist", "Гинеколог", 60),
    (7, "ophthalmologist", "Офтальмолог", 70),
    (8, "dermatologist", "Дерматовенеролог", 80),
    (9, "dentist", "Стоматолог", 90),
    (10, "surgeon", "Хирург", 100),
    (11, "phthisiatrist", "Фтизиатр", 110),
    (12, "uzist", "Узист", 120),
    (13, "chairman", "Председатель", 130),
]

SERVICE_DOCTOR_ROLE_IDS = {
    8: [1, 4, 5, 7],
    29: [1, 7],
    7: [1, 4, 5, 7],
    37: [1, 13],
    18: [1, 2, 3, 4, 5, 6, 7, 8, 9, 13],
    19: [1, 2, 3, 4, 5, 6, 7, 8, 9, 13],
    38: [1, 4, 5, 7],
    16: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 13],
    28: [1],
    34: [4],
    35: [4],
    36: [4],
    2: [4, 2, 1, 13],
    3: [1, 6, 8],
    4: [1],
    5: [1, 10],
    10: [1],
    11: [4, 2, 1, 13],
    12: [6, 1, 10, 4, 7, 5, 13],
    24: [1, 13],
    27: [1],
    30: [1],
    31: [13],
    39: [1, 13],
    40: [2, 13],
    41: [1, 13],
}

SERVICE_RECALL_AFTER_DAYS = {
    8: 3650,
    29: 3650,
    7: 365,
    37: 365,
    18: 365,
    19: 365,
    3: 180,
    4: 365,
    5: 365,
    6: 365,
    10: 365,
    11: 365,
    12: 365,
    16: 365,
    20: 365,
    21: 365,
    24: 365,
    27: 365,
    30: 365,
    40: 365,
    41: 365,
}

SERVICE_CATALOG = [item for item in SERVICE_CATALOG if item[0] != 36]
SERVICE_DOCTOR_ROLE_IDS = {service_id: role_ids for service_id, role_ids in SERVICE_DOCTOR_ROLE_IDS.items() if service_id != 36}
CERTIFICATE_SERVICE_LEGACY_IDS = {legacy_id for legacy_id, group_id, _, _ in SERVICE_CATALOG if group_id == 7}

SERVICE_GROUP_SORT_OVERRIDES = {
    "legacy-group-2": 10,  # ВУ
    "legacy-group-4": 20,  # ЛМК
    "legacy-group-3": 30,  # ГИМС
    "legacy-group-7": 40,  # Справки
    "legacy-group-9": 50,  # ЭКГ
    "legacy-group-6": 60,  # Профосмотры
    "legacy-group-1": 70,  # Анализы
    "legacy-group-8": 80,  # УЗИ
    "legacy-group-5": 90,  # Приём врачей
}

VISIT_TYPES = [
    ("driver", "Медицинская комиссия", "Водительская медицинская комиссия"),
    ("lmk_new", "ЛМК", "Оформление новой ЛМК"),
    ("lmk_extend", "Продление ЛМК", "Продление ЛМК"),
    ("tractor", "Справка 071У", "Справка для управления самоходными машинами"),
    ("gims", "ГИМС", "Медкомиссия для управления маломерными судами"),
    ("086", "Справка 086у", "Справка для поступления и обучения"),
    ("prof", "Профосмотр", "Профилактический медицинский осмотр"),
    ("sport", "Спорт", "Справки для спорта и соревнований"),
    ("guard", "Охрана", "Справки для охраны и допуска"),
    ("other", "Прочие справки", "Остальные справки и обследования"),
]

VISIT_TYPE_SERVICE_LEGACY_IDS = {
    "driver": [8, 29],
    "lmk_new": [18, 33, 23],
    "lmk_extend": [19, 33],
    "tractor": [7],
    "gims": [37],
    "086": [12],
    "prof": [16],
    "sport": [4, 5],
    "guard": [9, 11],
    "other": [2, 3, 10, 24, 27, 30, 31, 32, 38, 39, 40, 41],
}

TEMPLATE_PHRASES = [
    ("therapist", "normal", "Норма", "Противопоказаний не выявлено."),
    ("ophthalmologist", "normal", "Норма", "Патологии органа зрения не выявлено."),
    ("neurologist", "normal", "Норма", "Очаговой неврологической симптоматики не выявлено."),
    ("psychiatrist", "normal", "Норма", "Психиатрических противопоказаний не выявлено."),
    ("psychiatrist-narcologist", "normal", "Норма", "Признаков наркологического заболевания не выявлено."),
    ("otolaryngologist", "normal", "Норма", "Патологии ЛОР-органов не выявлено."),
    ("chairman", "allowed", "Допущен", "По результатам медицинского осмотра противопоказаний не выявлено."),
]


STAFF_ROLES = [
    ("chairman", "Председатель", "Управляет доступом и создает учетные записи сотрудников"),
    ("doctor", "Врач", "Работает с медицинской частью и заключениями"),
    ("admin", "Админ", "Управляет системой и настройками"),
    ("operator", "Оператор", "Работает с регистрацией и потоком пациентов"),
]


def _template_visit_type_id(template_name: str, visit_type_by_code: dict[str, VisitType]) -> int | None:
    visit_type_code = template_visit_type_code(template_name)
    visit_type = visit_type_by_code.get(visit_type_code or "")
    return visit_type.id if visit_type is not None else None


def _sync_document_templates(db: Session, visit_type_by_code: dict[str, VisitType]) -> None:
    sync_document_template_catalog(db)


def _ensure_user_roles_and_staff(db: Session, default_center_id: int | None = None) -> dict[str, Role]:
    role_by_code = {role.code: role for role in db.execute(select(Role)).scalars().all()}
    registrar_role = role_by_code.get("registrar")
    operator_role = role_by_code.get("operator")
    if registrar_role is not None and operator_role is None:
        registrar_role.code = "operator"
        registrar_role.name = "Оператор"
        registrar_role.description = "Работает с регистрацией и потоком пациентов"
        role_by_code.pop("registrar", None)
        role_by_code["operator"] = registrar_role

    for code, name, description in STAFF_ROLES:
        role = role_by_code.get(code)
        if role is None:
            role = Role(code=code, name=name, description=description)
            db.add(role)
            db.flush()
        else:
            role.name = name
            role.description = description
        role_by_code[code] = role

    chairman = db.execute(select(User).where(User.login == "chairman")).scalar_one_or_none()
    if chairman is None:
        db.add(
            User(
                center_id=default_center_id,
                role_id=role_by_code["chairman"].id,
                login="chairman",
                password_hash=hash_password("chairman123"),
                full_name="Председатель комиссии",
                email="chairman@example.com",
                is_active=True,
            )
        )
    else:
        chairman.role_id = role_by_code["chairman"].id
        chairman.center_id = chairman.center_id or default_center_id
        chairman.is_active = True

    admin = db.execute(select(User).where(User.login == "admin")).scalar_one_or_none()
    if admin is None:
        db.add(
            User(
                center_id=default_center_id,
                role_id=role_by_code["admin"].id,
                login="admin",
                password_hash=hash_password("admin123"),
                full_name="Администратор системы",
                email="admin@example.com",
                is_active=True,
            )
        )
    else:
        admin.role_id = role_by_code["admin"].id
        admin.center_id = admin.center_id or default_center_id
        admin.is_active = True

    db.commit()
    return role_by_code


def seed_reference_data(db: Session) -> None:
    center_exists = db.execute(select(Center.id).limit(1)).scalar_one_or_none()
    if center_exists is not None:
        _ensure_user_roles_and_staff(db)
        _ensure_center_details(db)
        _ensure_service_catalog(db)
        _ensure_foundation_catalog(db)
        has_large_import = db.execute(select(Client.id).offset(2000).limit(1)).scalar_one_or_none() is not None
        if not has_large_import:
            _backfill_related_records(db)
        return

    centers = [
        Center(code="center-a", name="Медцентр 1"),
        Center(code="center-b", name="Медцентр 2"),
    ]
    db.add_all(centers)

    roles = [
        Role(code="admin", name="Администратор", description="Полный доступ"),
        Role(code="registrar", name="Регистратор", description="Работа с клиентами и обращениями"),
    ]
    db.add_all(roles)
    db.flush()

    admin = User(
        center_id=centers[0].id,
        role_id=roles[0].id,
        login="admin",
        password_hash=hash_password("admin123"),
        full_name="Администратор системы",
        email="admin@example.com",
        is_active=True,
    )
    db.add(admin)
    _ensure_user_roles_and_staff(db, default_center_id=centers[0].id)

    category = ServiceCategory(code="base", name="Базовые услуги", sort_order=10)
    db.add(category)
    db.flush()

    services = [
        Service(code="spravka-driver", name="Справка водителя", price=Decimal("1500.00"), category_id=category.id),
        Service(code="spravka-pool", name="Справка в бассейн", price=Decimal("900.00"), category_id=category.id),
        Service(
            code="med-inspection",
            name="Медосмотр",
            price=Decimal("3500.00"),
            category_id=category.id,
            requires_sequence=True,
            recall_after_days=365,
        ),
    ]
    db.add_all(services)
    _ensure_service_catalog(db)
    _ensure_center_details(db)
    _ensure_foundation_catalog(db)

    clients = [
        Client(
            patient_number=1,
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            birth_date=date(1990, 5, 20),
            sex="M",
            phone="+79990000001",
            snils="111-111-111 11",
            created_by_user_id=admin.id,
        ),
        Client(
            patient_number=2,
            last_name="Петрова",
            first_name="Анна",
            middle_name="Сергеевна",
            birth_date=date(1988, 2, 14),
            sex="F",
            phone="+79990000002",
            created_by_user_id=admin.id,
        ),
    ]
    db.add_all(clients)
    db.flush()

    encounter = Encounter(
        center_id=centers[0].id,
        client_id=clients[0].id,
        created_by_user_id=admin.id,
        encounter_date=date.today(),
        payment_type="cash",
        total_amount=Decimal("1500.00"),
        comment="Первичный прием",
        status="completed",
    )
    db.add(encounter)
    db.flush()

    recall = Recall(
        client_id=clients[0].id,
        encounter_id=encounter.id,
        service_id=services[2].id,
        planned_date=date.today() + timedelta(days=30),
        status="planned",
        comment="Контрольный повтор",
    )
    db.add(recall)

    db.commit()
    _backfill_related_records(db)


def _ensure_center_details(db: Session) -> None:
    centers = db.execute(select(Center).order_by(Center.id.asc())).scalars().all()
    for index, center in enumerate(centers, start=1):
        center.legal_name = center.legal_name or f"ООО Медцентр {index}"
        center.address = center.address or "Адрес медцентра уточняется"
        center.phone = center.phone or "+7 000 000-00-00"
        center.email = center.email or "info@example.com"
        center.inn = center.inn or "0000000000"
        center.ogrn = center.ogrn or "0000000000000"
        center.license_number = center.license_number or "ЛО-00-00-000000"
        center.license_date = center.license_date or "01.01.2026"
    db.commit()


def _ensure_foundation_catalog(db: Session) -> None:
    visit_type_by_code: dict[str, VisitType] = {}
    for code, name, description in VISIT_TYPES:
        visit_type = db.execute(select(VisitType).where(VisitType.code == code)).scalar_one_or_none()
        if visit_type is None:
            visit_type = VisitType(code=code, name=name, description=description, is_active=True)
            db.add(visit_type)
            db.flush()
        else:
            visit_type.name = name
            visit_type.description = description
            visit_type.is_active = True
        visit_type_by_code[code] = visit_type

    service_by_legacy_id = {
        service.legacy_source_id: service
        for service in db.execute(select(Service).where(Service.legacy_source_id.is_not(None))).scalars().all()
    }
    db.execute(VisitTypeService.__table__.delete())
    for visit_type_code, legacy_ids in VISIT_TYPE_SERVICE_LEGACY_IDS.items():
        visit_type = visit_type_by_code.get(visit_type_code)
        if visit_type is None:
            continue
        for sort_order, legacy_id in enumerate(legacy_ids, start=10):
            service = service_by_legacy_id.get(legacy_id)
            if service is None:
                continue
            db.add(
                VisitTypeService(
                    visit_type_id=visit_type.id,
                    service_id=service.id,
                    sort_order=sort_order,
                    is_required=True,
                )
            )

    role_by_code = {
        role.code: role
        for role in db.execute(select(DoctorRole).where(DoctorRole.is_active.is_(True))).scalars().all()
    }
    for role_code, phrase_code, name, text_value in TEMPLATE_PHRASES:
        role = role_by_code.get(role_code)
        if role is None:
            continue
        phrase = db.execute(
            select(TemplatePhrase).where(
                TemplatePhrase.doctor_role_id == role.id,
                TemplatePhrase.code == phrase_code,
            )
        ).scalar_one_or_none()
        if phrase is None:
            phrase = TemplatePhrase(
                doctor_role_id=role.id,
                code=phrase_code,
                name=name,
                text=text_value,
                is_default=True,
                is_active=True,
            )
            db.add(phrase)
        else:
            phrase.name = name
            phrase.text = text_value
            phrase.is_default = True
            phrase.is_active = True

    _sync_document_templates(db, visit_type_by_code)

    driver_visit_type = visit_type_by_code.get("driver")
    driver_service = service_by_legacy_id.get(8)
    if driver_visit_type is not None and driver_service is not None:
        existing_range = db.execute(
            select(CertificateNumberRange).where(
                CertificateNumberRange.visit_type_id == driver_visit_type.id,
                CertificateNumberRange.series == "demo",
            )
        ).scalar_one_or_none()
        if existing_range is None:
            db.add(
                CertificateNumberRange(
                    visit_type_id=driver_visit_type.id,
                    service_id=driver_service.id,
                    series="demo",
                    number_from=1,
                    number_to=999999,
                    current_number=1,
                    is_active=True,
                )
            )

    for template in db.execute(select(DocumentTemplate)).scalars().all():
        template.output_format = template.output_format or template.template_type
        if template.visit_type_id is None:
            template_name = f"{template.name} {template.file_name}".lower()
            if "вод" in template_name or "driver" in template_name:
                template.visit_type_id = visit_type_by_code.get("driver").id if visit_type_by_code.get("driver") else None
            elif "лмк" in template_name:
                template.visit_type_id = visit_type_by_code.get("lmk_new").id if visit_type_by_code.get("lmk_new") else None
            elif any(keyword in template_name for keyword in ("070", "072", "санатор", "морск", "marine", "seafar", "драг", "drug", "alcohol")):
                template.visit_type_id = visit_type_by_code.get("other").id if visit_type_by_code.get("other") else None

    db.commit()


def _ensure_service_catalog(db: Session) -> None:
    role_by_legacy_id: dict[int, int] = {}
    for legacy_id, code, name, sort_order in DOCTOR_ROLES:
        role = db.execute(select(DoctorRole).where(DoctorRole.code == code)).scalar_one_or_none()
        if role is None:
            role = DoctorRole(id=legacy_id, code=code, name=name, sort_order=sort_order, is_active=True)
            db.add(role)
            db.flush()
        else:
            role.name = name
            role.sort_order = sort_order
            role.is_active = True
        role_by_legacy_id[legacy_id] = role.id

    category_by_group_id: dict[int, int] = {}
    for group_id, (code, name, sort_order) in enumerate(SERVICE_GROUPS, start=1):
        sort_order = SERVICE_GROUP_SORT_OVERRIDES.get(code, sort_order)
        category = db.execute(select(ServiceCategory).where(ServiceCategory.code == code)).scalar_one_or_none()
        if category is None:
            category = ServiceCategory(code=code, name=name, sort_order=sort_order)
            db.add(category)
            db.flush()
        else:
            category.name = name
            category.sort_order = sort_order
        category_by_group_id[group_id] = category.id

    for legacy_id, group_id, name, price in SERVICE_CATALOG:
        code = f"legacy-service-{legacy_id}"
        service = db.execute(select(Service).where(Service.code == code)).scalar_one_or_none()
        if service is None:
            service = db.execute(select(Service).where(Service.legacy_source_id == legacy_id)).scalar_one_or_none()

        if service is None:
            service = Service(code=code)
            db.add(service)

        service.legacy_source_id = legacy_id
        service.category_id = category_by_group_id[group_id]
        service.name = name
        service.price = Decimal(price)
        service.recall_after_days = SERVICE_RECALL_AFTER_DAYS.get(legacy_id)
        service.is_active = True
        db.flush()

        db.execute(
            ServiceDoctorRole.__table__.delete().where(ServiceDoctorRole.service_id == service.id)
        )
        for role_legacy_id in SERVICE_DOCTOR_ROLE_IDS.get(legacy_id, []):
            doctor_role_id = role_by_legacy_id.get(role_legacy_id)
            if doctor_role_id is not None:
                db.add(ServiceDoctorRole(service_id=service.id, doctor_role_id=doctor_role_id))

    for old_code in ("spravka-driver", "spravka-pool", "med-inspection"):
        old_service = db.execute(select(Service).where(Service.code == old_code)).scalar_one_or_none()
        if old_service is not None:
            old_service.is_active = False

    db.commit()


def _backfill_related_records(db: Session) -> None:
    encounters = db.execute(select(Encounter)).scalars().all()
    services = db.execute(select(Service)).scalars().all()
    clients = db.execute(select(Client)).scalars().all()

    if encounters and services:
        for encounter in encounters:
            has_service = db.execute(
                select(EncounterService.id).where(EncounterService.encounter_id == encounter.id).limit(1)
            ).scalar_one_or_none()
            if has_service is None:
                primary_service = services[0]
                amount = encounter.total_amount or primary_service.price
                db.add(
                    EncounterService(
                        encounter_id=encounter.id,
                        service_id=primary_service.id,
                        quantity=1,
                        unit_price=amount,
                        line_total=amount,
                        sequence_number=f"{encounter.id:06d}",
                        notes="Автозаполнение стартовых данных",
                    )
                )

            has_payment = db.execute(
                select(Payment.id).where(Payment.encounter_id == encounter.id).limit(1)
            ).scalar_one_or_none()
            if has_payment is None:
                db.add(
                    Payment(
                        encounter_id=encounter.id,
                        payment_date=encounter.encounter_date,
                        payment_type=encounter.payment_type,
                        amount=encounter.total_amount,
                        status="paid",
                        comment="Первичный платеж",
                        created_by_user_id=encounter.created_by_user_id,
                    )
                )

    for client in clients:
        has_record = db.execute(
            select(MedicalRecord.id).where(MedicalRecord.client_id == client.id).limit(1)
        ).scalar_one_or_none()
        if has_record is None:
            db.add(
                MedicalRecord(
                    client_id=client.id,
                    card_number=client.card_number or str(client.patient_number or client.id),
                    opened_at=client.birth_date,
                    oms_policy=client.oms_policy,
                    work_place=client.organization,
                    diagnosis=client.indications,
                    mkb10=client.mkb10,
                    notes=client.notes,
                )
            )

        has_document = db.execute(
            select(ClientDocument.id).where(ClientDocument.client_id == client.id).limit(1)
        ).scalar_one_or_none()
        if has_document is None:
            db.add(
                ClientDocument(
                    client_id=client.id,
                    document_type="Паспорт РФ",
                    series="4000",
                    number=f"{client.id:06d}",
                    issued_by="ГУ МВД",
                    issued_at=client.birth_date,
                    notes="Автозаполненный документ клиента",
                )
            )

    first_client = clients[0] if clients else None
    if first_client is not None:
        has_journal = db.execute(
            select(DocumentJournalEntry.id).where(DocumentJournalEntry.journal_code == "journal_344").limit(1)
        ).scalar_one_or_none()
        if has_journal is None:
            db.add(
                DocumentJournalEntry(
                    journal_code="journal_344",
                    journal_name="Журнал 344 водительских заключений",
                    client_id=first_client.id,
                    issued_at=date.today(),
                    series="demo",
                    number=first_client.reference_number or str(first_client.patient_number or first_client.id),
                    result_text="Противопоказаний не выявлено",
                    notes="Демо-запись журнала для проверки структуры",
                    created_by_user_id=first_client.created_by_user_id,
                )
            )

    db.commit()
