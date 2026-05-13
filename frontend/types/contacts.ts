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
