from fastapi import APIRouter

from app.api.v1.routes.audit_logs import router as audit_logs_router
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.blanks import router as blanks_router
from app.api.v1.routes.certificate_number_ranges import router as certificate_number_ranges_router
from app.api.v1.routes.centers import router as centers_router
from app.api.v1.routes.client_documents import router as client_documents_router
from app.api.v1.routes.clients import router as clients_router
from app.api.v1.routes.dashboard import router as dashboard_router
from app.api.v1.routes.documents import router as documents_router
from app.api.v1.routes.doctor_exams import router as doctor_exams_router
from app.api.v1.routes.doctor_roles import router as doctor_roles_router
from app.api.v1.routes.document_journals import router as document_journals_router
from app.api.v1.routes.encounters import router as encounters_router
from app.api.v1.routes.encounter_services import router as encounter_services_router
from app.api.v1.routes.generated_documents import router as generated_documents_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.imports import router as imports_router
from app.api.v1.routes.medical_records import router as medical_records_router
from app.api.v1.routes.patient_consents import router as patient_consents_router
from app.api.v1.routes.payments import router as payments_router
from app.api.v1.routes.recalls import router as recalls_router
from app.api.v1.routes.reports import router as reports_router
from app.api.v1.routes.services import router as services_router
from app.api.v1.routes.staff import router as staff_router
from app.api.v1.routes.service_categories import router as service_categories_router
from app.api.v1.routes.template_phrases import router as template_phrases_router
from app.api.v1.routes.visit_types import router as visit_types_router
from app.api.v1.routes.xml_exports import router as xml_exports_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(audit_logs_router, prefix="/audit-logs", tags=["audit-logs"])
api_router.include_router(staff_router, prefix="/staff", tags=["staff"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(health_router, tags=["health"])
api_router.include_router(imports_router, prefix="/imports", tags=["imports"])
api_router.include_router(clients_router, prefix="/clients", tags=["clients"])
api_router.include_router(centers_router, prefix="/centers", tags=["centers"])
api_router.include_router(client_documents_router, prefix="/client-documents", tags=["client-documents"])
api_router.include_router(encounters_router, prefix="/encounters", tags=["encounters"])
api_router.include_router(encounter_services_router, prefix="/encounter-services", tags=["encounter-services"])
api_router.include_router(visit_types_router, prefix="/visit-types", tags=["visit-types"])
api_router.include_router(payments_router, prefix="/payments", tags=["payments"])
api_router.include_router(reports_router, prefix="/reports", tags=["reports"])
api_router.include_router(service_categories_router, prefix="/service-categories", tags=["service-categories"])
api_router.include_router(services_router, prefix="/services", tags=["services"])
api_router.include_router(blanks_router, prefix="/blanks", tags=["blanks"])
api_router.include_router(doctor_roles_router, prefix="/doctor-roles", tags=["doctor-roles"])
api_router.include_router(documents_router, prefix="/documents", tags=["documents"])
api_router.include_router(generated_documents_router, prefix="/generated-documents", tags=["generated-documents"])
api_router.include_router(xml_exports_router, prefix="/xml-exports", tags=["xml-exports"])
api_router.include_router(document_journals_router, prefix="/document-journals", tags=["document-journals"])
api_router.include_router(medical_records_router, prefix="/medical-records", tags=["medical-records"])
api_router.include_router(patient_consents_router, prefix="/patient-consents", tags=["patient-consents"])
api_router.include_router(certificate_number_ranges_router, prefix="/certificate-number-ranges", tags=["certificate-number-ranges"])
api_router.include_router(template_phrases_router, prefix="/template-phrases", tags=["template-phrases"])
api_router.include_router(doctor_exams_router, prefix="/doctor-exams", tags=["doctor-exams"])
api_router.include_router(recalls_router, prefix="/recalls", tags=["recalls"])
