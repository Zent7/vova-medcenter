from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any

from app.models.client import Client
from app.models.encounter import Encounter


MONTH_NAMES = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}

MONTH_NAMES_EN = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _date(value: date | None) -> str:
    return value.strftime("%d.%m.%y") if value else ""


def _date_parts(value: date | None) -> tuple[str, str, str, str]:
    if value is None:
        return "", "", "", ""
    return value.strftime("%d"), value.strftime("%m"), str(value.year), MONTH_NAMES.get(value.month, "")


def _date_english(value: date | None) -> str:
    if value is None:
        return ""
    return f"{value.year}, {MONTH_NAMES_EN.get(value.month, '')}, {value.day:02d}"


def _age_on_date(birth_date: date | None, reference_date: date | None) -> str:
    if birth_date is None or reference_date is None:
        return ""
    age = reference_date.year - birth_date.year
    if (reference_date.month, reference_date.day) < (birth_date.month, birth_date.day):
        age -= 1
    return str(max(age, 0))


def _first_legacy_value(client: Client, *keys: str) -> str:
    payload = client.legacy_payload_json or {}
    lowered = {str(key).lower(): value for key, value in payload.items()}
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            value = lowered.get(key.lower())
        if value not in (None, ""):
            return _text(value)
    return ""


def _split_address(address: str) -> dict[str, str]:
    parts = [part.strip() for part in re.split(r",|\n", address or "") if part.strip()]
    result = {
        "subject": "",
        "district": "",
        "city": "",
        "street": "",
        "house": "",
        "body": "",
        "apartment": "",
    }

    def is_country(part: str) -> bool:
        return part.lower().replace(".", "").strip() in {"россия", "рф", "российская федерация"}

    marker_patterns = {
        "subject": re.compile(
            r"обл\.?|область|край|респ\.?|республика|автоном|ао\b|округ|санкт-петербург|спб|москва|севастополь",
            re.IGNORECASE,
        ),
        "district": re.compile(r"район|р-н", re.IGNORECASE),
        "city": re.compile(r"(^|\s)(г\.|гор\.|город)\s*|санкт-петербург|спб|москва|севастополь", re.IGNORECASE),
        "street": re.compile(
            r"(^|\s)(ул\.|улица|пр-?кт|просп\.?|проспект|пер\.|переулок|наб\.|шоссе|б-р|бул\.?|бульвар)\s*",
            re.IGNORECASE,
        ),
        "house": re.compile(r"(^|\s)(д\.|дом)\s*", re.IGNORECASE),
        "body": re.compile(r"(^|\s)(корпус|корп\.?|к\.)\s*", re.IGNORECASE),
        "apartment": re.compile(r"(^|\s)(кв\.|квартира)\s*", re.IGNORECASE),
    }

    if parts and is_country(parts[0]):
        result.update(
            {
                "subject": parts[1] if len(parts) > 1 else "",
                "district": parts[2] if len(parts) > 2 else "",
                "city": parts[3] if len(parts) > 3 else "",
                "street": parts[4] if len(parts) > 4 else "",
                "house": marker_patterns["house"].sub("", parts[5]).strip() if len(parts) > 5 else "",
                "body": marker_patterns["body"].sub("", parts[6]).strip() if len(parts) > 6 else "",
                "apartment": marker_patterns["apartment"].sub("", parts[7]).strip() if len(parts) > 7 else "",
            }
        )
        return result

    for part in parts:
        if not result["subject"] and marker_patterns["subject"].search(part):
            result["subject"] = part
        elif not result["district"] and marker_patterns["district"].search(part):
            result["district"] = part
        elif not result["city"] and marker_patterns["city"].search(part):
            result["city"] = part
        elif not result["street"] and marker_patterns["street"].search(part):
            result["street"] = part
        elif not result["house"] and marker_patterns["house"].search(part):
            result["house"] = marker_patterns["house"].sub("", part).strip()
        elif not result["body"] and marker_patterns["body"].search(part):
            result["body"] = marker_patterns["body"].sub("", part).strip()
        elif not result["apartment"] and marker_patterns["apartment"].search(part):
            result["apartment"] = marker_patterns["apartment"].sub("", part).strip()

    if not result["subject"] and parts:
        result["subject"] = next(
            (
                part
                for part in parts
                if not any(marker_patterns[key].search(part) for key in ("city", "street", "house", "body", "apartment"))
            ),
            "",
        )
    if not result["city"]:
        result["city"] = next(
            (
                part
                for part in parts
                if part
                and part != result["subject"]
                and part != result["district"]
                and not any(marker_patterns[key].search(part) for key in ("street", "house", "body", "apartment"))
            ),
            "",
        )
    return result


def _status(value: str | None) -> str:
    return {
        "draft": "Черновик",
        "completed": "Оформлено",
        "closed": "Закрыто",
    }.get(_text(value), "Создано")


def _payment_type(value: str | None) -> str:
    return {
        "cash": "наличные",
        "card": "карта",
        "invoice": "безналичный расчет",
    }.get(_text(value), _text(value))


def _category_context(category_text: str) -> dict[str, str]:
    categories = {
        "A": "",
        "B": "",
        "C": "",
        "D": "",
        "BE": "",
        "CE": "",
        "DE": "",
        "Tm": "",
        "Tb": "",
        "M": "",
        "A1": "",
        "B1": "",
        "C1": "",
        "D1": "",
        "C1E": "",
        "D1E": "",
    }
    aliases = {
        "A1": ("1A",),
        "B1": ("1B",),
        "C1": ("1C",),
        "D1": ("1D",),
        "C1E": ("1CE",),
        "D1E": ("1DE",),
    }
    source = category_text.upper()
    for key in categories:
        keys = (key, *aliases.get(key, ()))
        if any(re.search(rf"(^|[^A-Z0-9]){re.escape(item.upper())}([^A-Z0-9]|$)", source) for item in keys):
            categories[key] = "X"

    context: dict[str, str] = {}
    legacy_aliases = {
        "A1": "1A",
        "B1": "1B",
        "C1": "1C",
        "D1": "1D",
        "C1E": "1CE",
        "D1E": "1DE",
    }
    for key, value in categories.items():
        context[f"Category{key}"] = value
        context[f"Category{key}1"] = value
        context[f"{key}Calc"] = value
        context[f"Category{key}Calc"] = value
        legacy_key = legacy_aliases.get(key)
        if legacy_key:
            context[f"Category{legacy_key}"] = value
            context[f"Category{legacy_key}1"] = value
            context[f"{legacy_key}Calc"] = value
            context[f"Category{legacy_key}Calc"] = value
    return context


def build_document_context(
    client: Client,
    encounter: Encounter | None = None,
    *,
    service_names: list[str] | None = None,
    doctor_name: str | None = None,
    diagnosis: str | None = None,
    mkb10: str | None = None,
) -> dict[str, str]:
    birth_day, birth_month, birth_year, birth_month_name = _date_parts(client.birth_date)
    visit_day, visit_month, visit_year, visit_month_name = _date_parts(encounter.encounter_date if encounter else None)
    doc_day, doc_month, doc_year, doc_month_name = _date_parts(client.document_issued_date)

    full_name = " ".join(part for part in [client.last_name, client.first_name, client.middle_name] if part).strip()
    first_middle = " ".join(part for part in [client.first_name, client.middle_name] if part).strip()
    address = client.registration_text or client.address_text or ""
    address_parts = _split_address(address)
    services = ", ".join(name for name in (service_names or []) if name) or "Базовая услуга"
    visit_date = _date(encounter.encounter_date) if encounter else ""
    visit_date_en = _date_english(encounter.encounter_date if encounter else None)
    contract_date = visit_date or _date(date.today())
    total_amount = _text(encounter.total_amount) if encounter else ""
    notes = _text(encounter.comment) if encounter else _text(client.notes)
    sex = _text(client.sex).strip().upper()
    sex_label = {
        "M": "муж",
        "MALE": "муж",
        "М": "муж",
        "МУЖ": "муж",
        "МУЖСКОЙ": "муж",
        "F": "жен",
        "FEMALE": "жен",
        "Ж": "жен",
        "ЖЕН": "жен",
        "ЖЕНСКИЙ": "жен",
    }.get(sex, _text(client.sex))
    sex_full_label = {"муж": "мужской", "жен": "женский"}.get(sex_label.lower(), sex_label)
    organization = _text(client.organization) or _first_legacy_value(client, "Организация", "organization", "CompanyName")
    work_place = _text(client.work_place) or organization or _first_legacy_value(client, "Место работы", "WorkPlace", "qdfMain.WorkPlace")
    post = _text(client.profession) or _first_legacy_value(client, "Должность", "Post", "qdfMain.Post") or "не указано"
    document_series = _text(client.document_series) or _first_legacy_value(client, "DocumentSeries", "qdfMain.DocumentSeries")
    document_number = _text(client.document_number) or _first_legacy_value(client, "DocumentNumber", "qdfMain.DocumentNumber")
    document_issued_by = _text(client.document_issued_by) or _first_legacy_value(client, "WhoGive", "qdfMain.WhoGive")
    document_issued_date = _date(client.document_issued_date) or _first_legacy_value(client, "DocumentDate", "qdfMain.DocumentDate")
    resolved_mkb10 = _text(mkb10) or _text(client.mkb10)
    resolved_diagnosis = _text(diagnosis) or "Здоров"
    resolved_doctor = _text(doctor_name) or "Врач"
    reference_number = _text(client.reference_number) or str(encounter.id if encounter else client.patient_number or client.id)
    category_values = _category_context(_text(client.admission_category))
    age = _age_on_date(client.birth_date, encounter.encounter_date if encounter else date.today())
    marine_address_line = address
    marine_region = address_parts["subject"]
    position_applied = _text(client.profession) or post

    context = {
        "ID": str(encounter.id if encounter else client.id),
        "ClientID": str(client.id),
        "PatientNumber": _text(client.patient_number),
        "CardNumber": _text(client.card_number),
        "Client": full_name,
        "FullName": full_name,
        "FIO": full_name,
        "ClientCalc": full_name,
        "ClientCalcUpper": full_name.upper(),
        "FullNameUpper": full_name.upper(),
        "LastName": _text(client.last_name),
        "LastNameCalc": _text(client.last_name),
        "FirstName": _text(client.first_name),
        "FirstNameCalc": _text(client.first_name),
        "MiddleName": _text(client.middle_name),
        "PatronymicCalc": _text(client.middle_name),
        "FirstMiddleCalc": first_middle,
        "ReferenceNumber": reference_number,
        "SeriesNumberCalc": reference_number,
        "BirthDate": _date(client.birth_date),
        "BirthDateCalc": _date(client.birth_date),
        "BirthCalc": _date(client.birth_date),
        "BirthDateCalc_DAY": birth_day,
        "MonthBirthDateCalc": birth_month,
        "BirthDateCalc_MONTH": birth_month,
        "BirthDateCalc_DATEMONTH": birth_month_name,
        "BirthDateCalc_YEAR": birth_year,
        "BirthDateCalc_DAY1": birth_day,
        "MonthBirthDateCalc1": birth_month,
        "BirthDateCalc_MONTH1": birth_month,
        "BirthDateCalc_DATEMONTH1": birth_month_name,
        "BirthDateCalc_YEAR1": birth_year,
        "BirthDateCalc_DIGIT1": birth_day[:1],
        "BirthDateCalc_DIGIT2": birth_day[1:2],
        "BirthDateCalc_DIGIT3": birth_month[:1],
        "BirthDateCalc_DIGIT4": birth_month[1:2],
        "BirthDateCalc_DIGIT5": birth_year[:1],
        "BirthDateCalc_DIGIT6": birth_year[1:2],
        "BirthDateCalc_DIGIT7": birth_year[2:3],
        "BirthDateCalc_DIGIT8": birth_year[3:4],
        "VisitDate": visit_date,
        "PrintDateTime": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "VisitDate_EN": visit_date_en,
        "VisitDateMarine": visit_date_en,
        "ContractDate": contract_date,
        "VisitDate_DATEFULL": visit_date,
        "DateCalc": visit_date,
        "ServiceDateCalc": visit_date,
        "ServiceDateCalc1": visit_date,
        "VisitDate_DAY": visit_day,
        "MonthCalc": visit_month,
        "VisitDate_MONTH": visit_month,
        "VisitDate_DATEMONTH": visit_month_name,
        "VisitDate_YEAR": visit_year,
        "VisitDate_DAY1": visit_day,
        "MonthCalc1": visit_month,
        "VisitDate_MONTH1": visit_month,
        "VisitDate_DATEMONTH1": visit_month_name,
        "VisitDate_YEAR1": visit_year,
        "SubjectCalc": address_parts["subject"] or address,
        "SubjectCalc1": address_parts["subject"] or address,
        "SubDistrCalc": address_parts["district"],
        "AddressEndCalc": address,
        "AddressCalc": address,
        "MarineAddressLine": marine_address_line,
        "MarineRegion": marine_region,
        "CountryEN": "Russia",
        "DistrictCalc": address_parts["district"],
        "DistrictCalc1": address_parts["district"],
        "CityCalc": address_parts["city"],
        "CityCalc1": address_parts["city"],
        "StreetCalc": address_parts["street"],
        "StreetCalc1": address_parts["street"],
        "HouseNumberCalc": address_parts["house"],
        "HouseNumberCalc1": address_parts["house"],
        "HouseBodyCalc": address_parts["body"],
        "HouseBodyCalc1": address_parts["body"],
        "ApartmentNumberCalc": address_parts["apartment"],
        "ApartmentNumberCalc1": address_parts["apartment"],
        "Sex": sex_label,
        "SexCalc": sex_label,
        "SexFull": sex_full_label,
        "Gender": sex_label,
        "GenderCalc": sex_label,
        "GenderFull": sex_full_label,
        "Пол": sex_label,
        "ПолCalc": sex_label,
        "ПолПолный": sex_full_label,
        "qdfMain.Sex": sex_label,
        "Age": age,
        "AgeCalc": age,
        "RegistrType": "постоянная",
        "UserName": "Администратор системы",
        "StatusCalc": _status(encounter.status if encounter else None),
        "VisitAmount": total_amount,
        "AllPayment": total_amount,
        "PaymentType": _payment_type(encounter.payment_type if encounter else None),
        "Notes": notes,
        "Comment": notes,
        "OrderService": services,
        "qdfOrderServices": services,
        "Services": services,
        "ServiceName": services,
        "Post": post,
        "PositionApplied": position_applied,
        "CompanyName": work_place or "не указано",
        "Organization": organization,
        "WorkPlace": work_place,
        "Phone": _text(client.phone),
        "Email": _text(client.email),
        "SNILS": _text(client.snils),
        "PolisOMS": _text(client.oms_policy),
        "DocumentSeries": document_series,
        "DocumentNumber": document_number,
        "DocumentDate": document_issued_date,
        "DocumentDate_DAY": doc_day,
        "DocumentDate_MONTH": doc_month,
        "DocumentDate_DATEMONTH": doc_month_name,
        "DocumentDate_YEAR": doc_year,
        "WhoGive": document_issued_by,
        "MKB10": resolved_mkb10,
        "Mkb10": resolved_mkb10,
        "Diagnosis": resolved_diagnosis,
        "Diagnoz": resolved_diagnosis,
        "Doctor": resolved_doctor,
        "DoctorName": resolved_doctor,
        "qdfMain.AddressCalc": address,
        "qdfMain.Subject": address_parts["subject"] or address,
        "qdfMain.District": address_parts["district"],
        "qdfMain.City": address_parts["city"],
        "qdfMain.Street": address_parts["street"],
        "qdfMain.HouseNumber": address_parts["house"],
        "qdfMain.HouseBody": address_parts["body"],
        "qdfMain.ApartmentNumber": address_parts["apartment"],
        "qdfMain.BirthDate": _date(client.birth_date),
        "qdfMain.PolisOMS": _text(client.oms_policy),
        "qdfMain.SNILS": _text(client.snils),
        "qdfMain.Phone": _text(client.phone),
        "qdfMain.DocumentDate": document_issued_date,
        "qdfMain.DocumentNumber": document_number,
        "qdfMain.DocumentSeries": document_series,
        "qdfMain.Post": post,
        "qdfMain.WhoGive": document_issued_by,
        "qdfMain.WorkPlace": work_place,
        "qdfMain_Subject": address_parts["subject"] or address,
        "qdfMain_District": address_parts["district"],
        "qdfMain_City": address_parts["city"],
        "qdfMain_Street": address_parts["street"],
        "qdfMain_ApartmentNumber": address_parts["apartment"],
        "qdfMain_HouseBody": address_parts["body"],
        "qdfMain_HouseNumber": address_parts["house"],
        "ContractNumber": f"Д-{encounter.id if encounter else client.id}",
        "MainDoctorCalc": "Главный врач",
        "Harmfulness": _text(client.indications) or "не указано",
        "Therapist": "Терапевт",
        "TherapistCalc": "Терапевт",
        "Ophthalmolog": "Офтальмолог",
        "OphthalmologCalc": "Офтальмолог",
        "Neurolog": "Невролог",
        "NeurologCalc": "Невролог",
        "Otolaryngolog": "Отоларинголог",
        "OtolaryngologCalc": "Отоларинголог",
        "InstrumentalExamination": "Без отклонений",
        "InstrumentalExaminationCalc": "Без отклонений",
        "LaboratoryStudy": "Без отклонений",
        "LaboratoryStudyCalc": "Без отклонений",
        "Conclusion": "Годен",
        "SportDiagnosis": "",
        "SportMedicalRequirements": "",
        "SportContraindications": "",
        "SportEkg": "",
        "SportEkgConclusion": "",
        "SportFluorography": "",
        "SportConclusionText": "",
        "SportConclusion": "",
        "ChairmanDoctor": "",
        "SportDoctor": "",
        "MaritalStatus": "",
        "Weight": "",
        "Height": "",
        "HairColor": "",
        "EyeColor": "",
        "DistinguishingMark": "",
        "DriveShipCalc": "",
        "ManualControlCalc": "",
        "AutomaticTransmissionCalc": "",
        "ParkingSystemCalc": "",
        "VisionTCCalc": "",
        "HearingTCCalc": "",
        "3040": "",
        "3201": "",
        "DrSh": "",
        "DrSh1": "",
        "TCA": "",
        "TCB": "",
        "TCC": "",
        "A1Calc": category_values.get("Category1A", ""),
        "B1Calc": category_values.get("Category1B", ""),
        "C1Calc": category_values.get("Category1C", ""),
        "D1Calc": category_values.get("Category1D", ""),
        "C1ECalc": category_values.get("Category1CE", ""),
        "D1ECalc": category_values.get("Category1DE", ""),
        "RANGE!C2": "",
        "RANGE!C5": "",
        "RANGE!K14": "",
        "RANGE!X14": "",
    }
    context.update(category_values)
    return {key: _text(value) for key, value in context.items()}
