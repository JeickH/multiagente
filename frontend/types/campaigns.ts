/**
 * Tipos compartidos para el módulo Campañas (Sprint 13).
 *
 * Reflejan los `response_model` declarados en
 * `backend/app/routers/campaigns.py` (`schemas.CampaignOut`,
 * `schemas.CampaignsGlobalKPIs`, etc.). Mantener en sincronía con
 * `backend/app/schemas.py`.
 */

export type CampaignStatus =
  | 'draft'
  | 'scheduled'
  | 'running'
  | 'completed'
  | 'cancelled'
  | 'failed';

export interface CampaignSummary {
  id: number;
  name: string;
  status: CampaignStatus | string;
  meta_account_id: number;
  template_id: number;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  total_recipients: number;
  sent: number;
  delivered: number;
  read: number;
  failed: number;
  pending: number;
  skipped: number;
}

export interface GlobalKPIs {
  total_campaigns: number;
  total_recipients: number;
  sent_count: number;
  delivered_count: number;
  read_count: number;
  failed_count: number;
  queued_count: number;
  skipped_count: number;
  delivery_rate_pct: number | null;
  read_rate_pct: number | null;
}

/**
 * Estado de MetaAccount del usuario actual (subset relevante para el
 * wizard de campañas — solo necesitamos saber si está registrada y su id).
 * El backend devuelve más campos (display_phone, status…) que ignoramos aquí.
 * Reflejado por `schemas.MetaAccountStatusOut`.
 */
export interface MetaAccountStatus {
  registered: boolean;
  display_phone?: string | null;
  verified_name?: string | null;
  status?: string | null;
  is_active?: boolean | null;
  can_manage_meta_account: boolean;
}

/**
 * Plantilla WhatsApp tal como la expone `GET /templates`.
 * Refleja `schemas.WhatsappTemplateOut`.
 */
export interface TemplatePreview {
  id: number;
  meta_account_id: number;
  meta_template_id: string | null;
  name: string;
  category: string | null;
  language: string;
  status: string;
  components_json: {
    header?: { type?: string; format?: string; text?: string };
    body?: { text?: string };
    footer?: { text?: string };
    buttons?: unknown;
    [k: string]: unknown;
  };
  rejection_reason: string | null;
  last_synced_at: string | null;
  created_at: string;
}

/**
 * Contacto en su forma "lite" para selección en el wizard. Refleja
 * `schemas.ContactOut`. NO incluye PII innecesaria para el wizard.
 */
export interface ContactLite {
  id: number;
  phone_e164: string;
  name: string | null;
  email: string | null;
  opt_in: boolean;
  opt_in_source: string | null;
  attributes: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

/**
 * Grupo de contactos. Refleja `schemas.ContactGroupOut`.
 */
export interface GroupLite {
  id: number;
  name: string;
  description: string | null;
  member_count: number;
  created_at: string;
}

/**
 * Payload de creación de campaña. Refleja `schemas.CampaignCreate`.
 * Backend valida `meta_account_id`/`template_id` contra el team y
 * que la plantilla esté APPROVED (S13-001) antes de aceptar.
 */
export interface CampaignCreatePayload {
  name: string;
  template_id: number;
  meta_account_id: number;
  template_variables_json?: Record<string, string> | null;
  scheduled_at?: string | null;
  recipients:
    | { mode: 'individual'; contact_ids: number[] }
    | { mode: 'group'; contact_group_id: number };
}

/**
 * Respuesta de `POST /campaigns` — backend devuelve `CampaignDetailOut`.
 * Aquí solo tipamos lo que el wizard usa para redirigir.
 */
export interface CampaignCreateResponse {
  id: number;
  status: string;
  total_recipients: number;
  pending: number;
  skipped: number;
}

/**
 * Estado individual de un destinatario (`CampaignRecipient`).
 * Reflejo de `schemas.CampaignRecipientOut`. SEGURIDAD: `phone_e164` se
 * enmascara en UI con `maskPhone()` antes de mostrarse.
 */
export type RecipientStatus =
  | 'queued'
  | 'sending'
  | 'sent'
  | 'delivered'
  | 'read'
  | 'failed'
  | 'skipped';

export interface CampaignRecipient {
  id: number;
  contact_id: number;
  phone_e164: string;
  status: RecipientStatus | string;
  error_code: string | null;
  sent_at: string | null;
  delivered_at: string | null;
  read_at: string | null;
  failed_at: string | null;
}

/**
 * Página de destinatarios devuelta por
 * `GET /campaigns/{id}/recipients?limit=&offset=&status=`.
 * Reflejo de `schemas.CampaignRecipientsPage`.
 */
export interface CampaignRecipientsPage {
  items: CampaignRecipient[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * Detalle completo de una campaña — reflejo de
 * `schemas.CampaignDetailOut` (extiende `CampaignSummary`).
 */
export interface CampaignDetail extends CampaignSummary {
  template_name: string | null;
  template_language: string | null;
  template_variables_json: Record<string, unknown>;
  recipients_preview: CampaignRecipient[];
  kpis_by_event_type: Record<string, number>;
}
