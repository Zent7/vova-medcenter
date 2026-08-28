from pydantic import BaseModel


class DocumentTemplateRead(BaseModel):
    id: int
    code: str
    name: str
    visit_type_id: int | None = None
    file_name: str
    file_path: str | None
    description: str | None
    template_type: str
    output_format: str
    requires_numbered_blank: bool
    blank_type: str | None
    is_active: bool
    supports_layout_editing: bool = False
    has_override: bool = False
    in_service_list: bool = True
    listed_on_templates_page: bool = True

    model_config = {"from_attributes": True}
