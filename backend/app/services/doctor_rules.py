GYNECOLOGIST_ROLE_CODE = "gynecologist"


def is_male_sex(value: object) -> bool:
    text = str(value or "").strip().lower()
    return text in {"m", "male", "man", "м", "муж", "мужской"} or "муж" in text


def should_include_doctor_role_for_client_sex(role_code: object, sex: object) -> bool:
    if str(role_code or "").strip().lower() != GYNECOLOGIST_ROLE_CODE:
        return True
    return not is_male_sex(sex)
