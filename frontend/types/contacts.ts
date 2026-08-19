/**
 * Tipos compartidos para Contactos y Grupos (Sprint 13 — tarea #168).
 *
 * Reflejan los `response_model` declarados en
 * `backend/app/routers/contacts.py` y los schemas Pydantic en
 * `backend/app/schemas.py` (`ContactOut`, `ContactGroupOut`,
 * `ContactGroupDetailOut`, `ContactBulkImportResult`).
 *
 * SEGURIDAD: estos tipos NO contienen `team_id`, `hashed_password` ni
 * cualquier otro secreto — el backend ya los excluye (regla 2). El
 * `phone_e164` se renderiza siempre vía `maskPhone()` (regla 1).
 */

/** Refleja `schemas.ContactOut`. */
export interface Contact {
  id: number;
  phone_e164: string;
  name: string | null;
  email: string | null;
  attributes: Record<string, unknown>;
  opt_in: boolean;
  opt_in_source: string | null;
  created_at: string;
  updated_at: string;
}

/** Refleja `schemas.ContactGroupOut`. */
export interface ContactGroup {
  id: number;
  name: string;
  description: string | null;
  member_count: number;
  created_at: string;
}

/** Refleja `schemas.ContactGroupDetailOut`. */
export interface ContactGroupDetail extends ContactGroup {
  members: Contact[];
}

/** Refleja `schemas.ContactBulkImportResult`. Los `errors` ya vienen
 *  sanitizados del backend (regla 1 / S13-009) — NO deben contener PII
 *  cruda. Si alguna entrada la contiene, es bug del backend a reportar.
 */
export interface ContactImportResult {
  total: number;
  created: number;
  updated: number;
  skipped: number;
  errors: string[];
}

/** Una fila que el importador de Excel rechazó. Refleja
 *  `schemas.ContactExcelRowError`. `reason` es un motivo en español, sin PII
 *  (regla 1): dice qué está mal, nunca repite el teléfono ni el correo.
 */
export interface ContactExcelRowError {
  row: number;
  reason: string;
}

/** Refleja `schemas.ContactExcelImportResult` (POST /contacts/import-excel). */
export interface ContactExcelImportResult {
  total: number;
  created: number;
  updated: number;
  rejected: number;
  errors: ContactExcelRowError[];
  /** Encabezados extra que se guardaron como atributos del contacto. */
  detected_attributes: string[];
  /** Mensaje que aplica a todo el archivo, no a una fila. */
  notice: string | null;
}

/** Un campo del contacto usable para personalizar un mensaje.
 *  Refleja `schemas.ContactFieldOut` (GET /contacts/campos). Es el CATÁLOGO:
 *  no trae valores, así que no hay PII en esta respuesta (regla 2).
 */
export interface ContactField {
  key: string;
  label: string;
  /** Token que se guarda en `template_variables_json`. */
  token: string;
  source: 'base' | 'attribute' | string;
  contacts: number;
}

/** Refleja `schemas.ContactFieldsOut`. */
export interface ContactFieldsResponse {
  fields: ContactField[];
  scanned_contacts: number;
}

/** Body para `POST /contacts` (refleja `schemas.ContactCreate`). */
export interface ContactCreatePayload {
  phone_e164: string;
  name?: string | null;
  email?: string | null;
  attributes?: Record<string, unknown> | null;
  opt_in?: boolean;
  opt_in_source?: string | null;
}

/** Body para `PATCH /contacts/{id}` (refleja `schemas.ContactUpdate`). */
export interface ContactUpdatePayload {
  name?: string | null;
  email?: string | null;
  attributes?: Record<string, unknown> | null;
  opt_in?: boolean;
  opt_in_source?: string | null;
}

/** Body para `POST /contact-groups` (refleja `schemas.ContactGroupCreate`). */
export interface ContactGroupCreatePayload {
  name: string;
  description?: string | null;
}

/** Body para `PATCH /contact-groups/{id}` (refleja `ContactGroupUpdate`). */
export interface ContactGroupUpdatePayload {
  name?: string | null;
  description?: string | null;
}
