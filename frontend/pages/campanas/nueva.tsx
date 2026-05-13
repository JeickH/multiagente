/**
 * Wizard de creación de campaña (Sprint 13 — tarea #165).
 *
 * Contrato visual: `identidad_gloma/diseno_campanas.html` pantalla 2
 * (sección `#p2` "Wizard Nueva Campaña" — 4 pasos lineales).
 *
 * Endpoints consumidos:
 *   - GET  /usuario/me/meta-account     → resolver meta_account_id del team
 *   - GET  /templates?status=APPROVED   → lista plantillas para paso 2
 *   - GET  /contacts?limit=500          → contactos para modo individual
 *   - GET  /contact-groups              → grupos para modo group
 *   - POST /campaigns                   → crear campaña (S13-001/002/003)
 *
 * Reglas de Seguridad aplicadas (frontend):
 *   - regla 6: errores del backend se muestran tal cual los manda él
 *     (`detail` ya está sanitizado server-side); jamás se loggean.
 *   - S13-003 (transparencia opt-in): se muestra aviso al usuario en paso 3
 *     indicándole que los contactos sin opt-in serán omitidos por el sender.
 */
import { useRouter } from 'next/router';
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import Layout from '../../components/Layout';
import { ApiError, authedFetch } from '../../lib/api';
import type {
  CampaignCreatePayload,
  CampaignCreateResponse,
  ContactLite,
  GroupLite,
  MetaAccountStatus,
  TemplatePreview,
} from '../../types/campaigns';

// ─── Constantes ────────────────────────────────────────────────────────────

const STEP_LABELS = ['Datos', 'Plantilla', 'Destinatarios', 'Programación'];
const CONTACTS_PAGE_SIZE = 50;
// Coincide con backend `schemas.MAX_RECIPIENTS_PER_CAMPAIGN`.
const MAX_RECIPIENTS = 10000;
// Estimación grosera de rate de envío (10 msg/s, ver `META_RATE_LIMIT_RPS`
// en `services/campaign_sender.py`). Se usa solo para el resumen.
const SEND_RATE_PER_SEC = 10;

type Mode = 'individual' | 'group';
type Schedule = 'now' | 'scheduled';

interface WizardDraft {
  name: string;
  description: string; // solo UX, no se envía (no hay campo backend)
  templateId: number | null;
  templateVariables: Record<string, string>;
  mode: Mode;
  selectedContactIds: Set<number>;
  selectedGroupId: number | null;
  schedule: Schedule;
  scheduledAtLocal: string; // datetime-local string
}

// ─── Helpers ───────────────────────────────────────────────────────────────

function extractTemplateBody(t: TemplatePreview | null): string {
  if (!t) return '';
  const body = t.components_json?.body;
  if (body && typeof body === 'object' && typeof body.text === 'string') {
    return body.text;
  }
  // Algunas plantillas vienen como array `components: [{type:'BODY', text}, ...]`
  // dentro de `components_json` cuando el backend la persiste 1:1 de Meta.
  const arr = (t.components_json as unknown as { components?: Array<{ type?: string; text?: string }> })
    ?.components;
  if (Array.isArray(arr)) {
    const b = arr.find((c) => (c?.type || '').toUpperCase() === 'BODY');
    if (b && typeof b.text === 'string') return b.text;
  }
  return '';
}

function extractVariableKeys(t: TemplatePreview | null): string[] {
  const body = extractTemplateBody(t);
  if (!body) return [];
  const matches = body.match(/\{\{\s*(\d+)\s*\}\}/g) || [];
  const keys = new Set<string>();
  for (const m of matches) {
    const n = m.replace(/[^0-9]/g, '');
    if (n) keys.add(n);
  }
  return Array.from(keys).sort((a, b) => Number(a) - Number(b));
}

function fmtNumber(n: number): string {
  return new Intl.NumberFormat('es-MX').format(n);
}

function fmtDuration(seconds: number): string {
  if (seconds <= 60) return `~${Math.max(1, seconds)} s`;
  const m = Math.ceil(seconds / 60);
  if (m < 60) return `~${m} min`;
  const h = Math.floor(m / 60);
  const r = m % 60;
  return r === 0 ? `~${h} h` : `~${h} h ${r} min`;
}

function localToUtcIso(local: string): string | null {
  // input type="datetime-local" devuelve "YYYY-MM-DDTHH:MM"
  if (!local) return null;
  const d = new Date(local);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

// ─── Subcomponentes ────────────────────────────────────────────────────────

function Stepper({ step }: { step: number }) {
  return (
    <div className="bg-gloma-brown text-gloma-cream px-5 py-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-gloma-rose">
            Nueva campaña
          </p>
          <h3 className="font-heading text-lg font-bold">
            Asistente paso a paso
          </h3>
        </div>
        {/* Desktop horizontal stepper */}
        <ol className="hidden md:flex items-center gap-2 text-xs">
          {STEP_LABELS.map((label, i) => {
            const idx = i + 1;
            const done = idx < step;
            const active = idx === step;
            return (
              <li key={label} className="flex items-center gap-2">
                <span
                  className={`w-7 h-7 rounded-full flex items-center justify-center font-bold text-xs transition-colors ${
                    done
                      ? 'bg-emerald-500 text-white'
                      : active
                        ? 'bg-white text-gloma-brown ring-2 ring-gloma-rose'
                        : 'bg-gloma-brown-darker text-gloma-cream/70 border border-gloma-rose-soft/30'
                  }`}
                  aria-current={active ? 'step' : undefined}
                >
                  {done ? '✓' : idx}
                </span>
                <span
                  className={
                    active
                      ? 'font-semibold'
                      : done
                        ? 'opacity-90'
                        : 'opacity-60'
                  }
                >
                  {label}
                </span>
                {idx < STEP_LABELS.length && (
                  <span className="text-gloma-rose mx-1">—</span>
                )}
              </li>
            );
          })}
        </ol>
      </div>
      {/* Mobile vertical stepper */}
      <ol className="mt-3 flex md:hidden flex-col gap-1.5 text-xs">
        {STEP_LABELS.map((label, i) => {
          const idx = i + 1;
          const done = idx < step;
          const active = idx === step;
          return (
            <li key={label} className="flex items-center gap-2">
              <span
                className={`w-5 h-5 rounded-full flex items-center justify-center font-bold text-[10px] ${
                  done
                    ? 'bg-emerald-500 text-white'
                    : active
                      ? 'bg-white text-gloma-brown ring-2 ring-gloma-rose'
                      : 'bg-gloma-brown-darker text-gloma-cream/70'
                }`}
              >
                {done ? '✓' : idx}
              </span>
              <span className={active ? 'font-semibold' : 'opacity-70'}>
                Paso {idx} · {label}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function StepHeader({
  step,
  title,
  subtitle,
}: {
  step: number;
  title: string;
  subtitle: string;
}) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-widest text-gloma-brown-light mb-1">
        Paso {step} de 4
      </p>
      <h4 className="font-heading text-xl font-bold mb-1 text-gloma-brown-dark">
        {title}
      </h4>
      <p className="text-sm text-gloma-brown-light mb-5">{subtitle}</p>
    </div>
  );
}

// ─── Página ────────────────────────────────────────────────────────────────

export default function NuevaCampanaWizard() {
  const router = useRouter();

  // Loading + datos remotos
  const [metaAccount, setMetaAccount] = useState<MetaAccountStatus | null>(
    null,
  );
  const [metaAccountId, setMetaAccountId] = useState<number | null>(null);
  const [templates, setTemplates] = useState<TemplatePreview[] | null>(null);
  const [contacts, setContacts] = useState<ContactLite[] | null>(null);
  const [groups, setGroups] = useState<GroupLite[] | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);

  // Wizard state
  const [step, setStep] = useState<number>(1);
  const [draft, setDraft] = useState<WizardDraft>({
    name: '',
    description: '',
    templateId: null,
    templateVariables: {},
    mode: 'group',
    selectedContactIds: new Set<number>(),
    selectedGroupId: null,
    schedule: 'now',
    scheduledAtLocal: '',
  });

  // Estado búsqueda contactos (paso 3 / modo individual)
  const [contactSearch, setContactSearch] = useState('');
  const [contactsPage, setContactsPage] = useState(1);

  // Estado submit
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitErrorStatus, setSubmitErrorStatus] = useState<number | null>(
    null,
  );

  // ─── Boot: meta-account (paso 1 bloqueante) ─────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setBooting(true);
    setBootError(null);
    authedFetch<MetaAccountStatus & { phone_number_id?: string; waba_id?: string }>(
      '/usuario/me/meta-account',
    )
      .then(async (acc) => {
        if (cancelled) return;
        setMetaAccount(acc);
        if (!acc.registered) {
          setBooting(false);
          return;
        }
        // El endpoint no expone `id` directamente, pero `GET /contact-groups`
        // / `/templates` ya filtran por team. El backend acepta cualquier
        // `meta_account_id` válido del team; resolverlo aquí requiere otra
        // call. Truco: el primer template del team trae `meta_account_id`
        // y todos los del team son del mismo. Si no hay plantillas todavía
        // (team recién conectado), usamos `/templates` igual: viene `[]` y
        // el wizard bloqueará el paso 2.
        try {
          const [tpls, ctcs, grps] = await Promise.all([
            authedFetch<TemplatePreview[]>(
              '/templates?status=APPROVED',
            ),
            authedFetch<ContactLite[]>(
              '/contacts?limit=500&opt_in_only=false',
            ),
            authedFetch<GroupLite[]>('/contact-groups'),
          ]);
          if (cancelled) return;
          setTemplates(tpls);
          setContacts(ctcs);
          setGroups(grps);
          // Resolver meta_account_id: del primer template, si hay; si no,
          // se queda en null y el paso 2 mostrará empty state. El POST
          // /campaigns en ese caso no puede dispararse (botón deshabilitado).
          if (tpls.length > 0) {
            setMetaAccountId(tpls[0].meta_account_id);
          }
        } catch (err) {
          if (cancelled) return;
          const msg =
            err instanceof ApiError
              ? err.message
              : 'No se pudieron cargar las plantillas, contactos o grupos.';
          setBootError(msg);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        const msg =
          err instanceof ApiError
            ? err.message
            : 'No se pudo verificar tu cuenta de WhatsApp.';
        setBootError(msg);
      })
      .finally(() => {
        if (!cancelled) setBooting(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Plantilla seleccionada (derivada)
  const selectedTemplate = useMemo<TemplatePreview | null>(() => {
    if (!templates || draft.templateId === null) return null;
    return templates.find((t) => t.id === draft.templateId) ?? null;
  }, [templates, draft.templateId]);

  const variableKeys = useMemo(
    () => extractVariableKeys(selectedTemplate),
    [selectedTemplate],
  );

  // Cuando cambia la plantilla, inicializa los valores de variables
  useEffect(() => {
    if (!selectedTemplate) return;
    setDraft((d) => {
      const next: Record<string, string> = {};
      for (const k of variableKeys) {
        // Pre-relleno: la primera variable suele ser el nombre del contacto.
        if (k === '1' && !d.templateVariables[k]) {
          next[k] = '{{contact.name}}';
        } else {
          next[k] = d.templateVariables[k] ?? '';
        }
      }
      return { ...d, templateVariables: next };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTemplate?.id]);

  // ─── Contactos: filtrado + paginación cliente ───────────────────────────
  const filteredContacts = useMemo<ContactLite[]>(() => {
    if (!contacts) return [];
    const q = contactSearch.trim().toLowerCase();
    if (!q) return contacts;
    return contacts.filter((c) => {
      return (
        (c.name || '').toLowerCase().includes(q) ||
        (c.phone_e164 || '').toLowerCase().includes(q)
      );
    });
  }, [contacts, contactSearch]);

  const totalContactPages = Math.max(
    1,
    Math.ceil(filteredContacts.length / CONTACTS_PAGE_SIZE),
  );
  const contactsPageSafe = Math.min(contactsPage, totalContactPages);
  const pagedContacts = filteredContacts.slice(
    (contactsPageSafe - 1) * CONTACTS_PAGE_SIZE,
    contactsPageSafe * CONTACTS_PAGE_SIZE,
  );

  // Reset página cuando cambia búsqueda
  useEffect(() => {
    setContactsPage(1);
  }, [contactSearch]);

  // ─── Validaciones por paso ──────────────────────────────────────────────
  const canAdvance: boolean = (() => {
    if (step === 1) {
      const trimmed = draft.name.trim();
      return trimmed.length >= 1 && trimmed.length <= 120 && metaAccount?.registered === true;
    }
    if (step === 2) {
      if (!selectedTemplate) return false;
      // Todas las variables deben tener valor (no vacío)
      for (const k of variableKeys) {
        if (!draft.templateVariables[k] || !draft.templateVariables[k].trim()) {
          return false;
        }
      }
      return true;
    }
    if (step === 3) {
      if (draft.mode === 'individual') {
        const n = draft.selectedContactIds.size;
        return n >= 1 && n <= MAX_RECIPIENTS;
      }
      return draft.selectedGroupId !== null;
    }
    if (step === 4) {
      if (draft.schedule === 'now') return true;
      const iso = localToUtcIso(draft.scheduledAtLocal);
      if (!iso) return false;
      return new Date(iso).getTime() > Date.now();
    }
    return false;
  })();

  // ─── Resumen ────────────────────────────────────────────────────────────
  const totalRecipients = useMemo<number>(() => {
    if (draft.mode === 'individual') return draft.selectedContactIds.size;
    if (draft.selectedGroupId !== null && groups) {
      const g = groups.find((x) => x.id === draft.selectedGroupId);
      return g?.member_count ?? 0;
    }
    return 0;
  }, [draft.mode, draft.selectedContactIds, draft.selectedGroupId, groups]);

  const estSeconds = Math.ceil(Math.max(1, totalRecipients) / SEND_RATE_PER_SEC);

  // ─── Submit ─────────────────────────────────────────────────────────────
  const handleSubmit = async () => {
    if (!metaAccountId || !selectedTemplate) return;
    setSubmitting(true);
    setSubmitError(null);
    setSubmitErrorStatus(null);

    const payload: CampaignCreatePayload = {
      name: draft.name.trim(),
      template_id: selectedTemplate.id,
      meta_account_id: metaAccountId,
      template_variables_json:
        variableKeys.length > 0 ? { ...draft.templateVariables } : null,
      scheduled_at:
        draft.schedule === 'scheduled'
          ? localToUtcIso(draft.scheduledAtLocal)
          : null,
      recipients:
        draft.mode === 'individual'
          ? {
              mode: 'individual',
              contact_ids: Array.from(draft.selectedContactIds),
            }
          : {
              mode: 'group',
              // canAdvance ya garantizó que es number en step 3.
              contact_group_id: draft.selectedGroupId as number,
            },
    };

    try {
      const created = await authedFetch<CampaignCreateResponse>('/campaigns', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      router.push(`/campanas/${created.id}`);
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      const msg =
        err instanceof ApiError
          ? err.message
          : 'No fue posible crear la campaña. Intenta de nuevo.';
      setSubmitError(msg);
      setSubmitErrorStatus(status);
      // Si fue 400 (plantilla no APPROVED) o 404 (plantilla cross-team),
      // regresar al paso 2 para que el usuario reelija.
      if (status === 400 || status === 404) {
        setStep(2);
      }
    } finally {
      setSubmitting(false);
    }
  };

  // ─── Helpers de selección de contactos ──────────────────────────────────
  const toggleContact = (id: number) => {
    setDraft((d) => {
      const next = new Set(d.selectedContactIds);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { ...d, selectedContactIds: next };
    });
  };
  const selectAllOnPage = () => {
    setDraft((d) => {
      const next = new Set(d.selectedContactIds);
      for (const c of pagedContacts) next.add(c.id);
      return { ...d, selectedContactIds: next };
    });
  };
  const clearSelection = () => {
    setDraft((d) => ({ ...d, selectedContactIds: new Set<number>() }));
  };

  // ─── Render: bloqueos previos ───────────────────────────────────────────
  if (booting) {
    return (
      <Layout variant="fullscreen">
        <div className="p-6 md:p-8 w-full bg-gloma-cream min-h-screen font-body">
          <div className="max-w-4xl mx-auto">
            <div className="h-8 w-64 bg-gloma-brown-light/15 rounded animate-pulse mb-3" />
            <div className="h-4 w-96 bg-gloma-brown-light/10 rounded animate-pulse mb-6" />
            <div className="bg-white rounded-2xl border border-gloma-brown-light/20 shadow-sm">
              <div className="h-20 bg-gloma-brown-light/20 animate-pulse rounded-t-2xl" />
              <div className="p-8 space-y-3">
                <div className="h-5 w-40 bg-gloma-brown-light/15 rounded animate-pulse" />
                <div className="h-10 w-full bg-gloma-brown-light/10 rounded animate-pulse" />
                <div className="h-10 w-2/3 bg-gloma-brown-light/10 rounded animate-pulse" />
              </div>
            </div>
          </div>
        </div>
      </Layout>
    );
  }

  if (bootError) {
    return (
      <Layout variant="fullscreen">
        <div className="p-6 md:p-8 w-full bg-gloma-cream min-h-screen font-body">
          <div className="max-w-3xl mx-auto bg-white rounded-2xl border border-red-200 p-6">
            <h1 className="font-heading text-xl font-bold text-red-700 mb-2">
              No se pudo cargar el asistente
            </h1>
            <p className="text-sm text-gloma-brown-light mb-4">{bootError}</p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="px-4 py-2 rounded-lg bg-gloma-brown text-gloma-cream text-sm font-semibold hover:bg-gloma-brown-dark"
            >
              Reintentar
            </button>
          </div>
        </div>
      </Layout>
    );
  }

  if (!metaAccount?.registered) {
    return (
      <Layout variant="fullscreen">
        <div className="p-6 md:p-8 w-full bg-gloma-cream min-h-screen font-body">
          <div className="max-w-3xl mx-auto bg-white rounded-2xl border border-amber-200 p-8 text-center">
            <div className="w-16 h-16 mx-auto rounded-full bg-amber-100 flex items-center justify-center text-3xl mb-4">
              !
            </div>
            <h1 className="font-heading text-2xl font-bold text-gloma-brown-dark mb-2">
              Conecta primero tu cuenta de WhatsApp Business
            </h1>
            <p className="text-sm text-gloma-brown-light max-w-md mx-auto mb-6">
              Para crear campañas necesitas vincular una cuenta de WhatsApp
              Business desde la sección Mi Plan. Una vez conectada, podrás
              regresar a este asistente.
            </p>
            <Link href="/usuario" legacyBehavior>
              <a className="inline-flex items-center justify-center px-5 py-2.5 rounded-lg bg-gloma-brown text-gloma-cream font-semibold text-sm hover:bg-gloma-brown-dark">
                Ir a Mi Plan
              </a>
            </Link>
            <div className="mt-4">
              <Link href="/campanas" legacyBehavior>
                <a className="text-xs text-gloma-brown-light hover:text-gloma-brown underline">
                  Volver al panel de campañas
                </a>
              </Link>
            </div>
          </div>
        </div>
      </Layout>
    );
  }

  // ─── Render principal ───────────────────────────────────────────────────
  return (
    <Layout variant="fullscreen">
      <div className="p-6 md:p-8 w-full bg-gloma-cream min-h-screen font-body">
        <div className="max-w-5xl mx-auto">
          {/* Header */}
          <div className="mb-6">
            <Link href="/campanas" legacyBehavior>
              <a className="text-xs text-gloma-brown-light hover:text-gloma-brown underline">
                ← Volver al panel
              </a>
            </Link>
            <h1 className="font-heading text-2xl md:text-3xl font-extrabold text-gloma-brown-dark mt-1">
              Nueva campaña
            </h1>
            <p className="text-sm text-gloma-brown-light">
              Configura un envío masivo en cuatro pasos. Cada paso valida antes
              de habilitar el botón Continuar.
            </p>
          </div>

          {/* Banner de error de submit (visible en todos los pasos) */}
          {submitError && (
            <div
              className={`mb-4 px-4 py-3 rounded-lg text-sm flex items-start justify-between gap-3 ${
                submitErrorStatus === 422
                  ? 'bg-red-50 border border-red-200 text-red-700'
                  : 'bg-amber-50 border border-amber-200 text-amber-800'
              }`}
            >
              <div>
                <p className="font-semibold">
                  {submitErrorStatus === 422
                    ? 'Límite excedido'
                    : 'No fue posible crear la campaña'}
                </p>
                <p className="text-xs mt-0.5">
                  {submitError}
                  {submitErrorStatus
                    ? ` (código ${submitErrorStatus})`
                    : ''}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSubmitError(null)}
                className="text-xs underline"
              >
                Cerrar
              </button>
            </div>
          )}

          <div className="bg-white rounded-2xl border border-gloma-brown-light/20 shadow-sm overflow-hidden">
            <Stepper step={step} />

            {/* ───── Paso 1 ───── */}
            {step === 1 && (
              <div className="p-5 md:p-8 bg-gloma-cream">
                <StepHeader
                  step={1}
                  title="Datos de la campaña"
                  subtitle="Sólo tú y tu equipo verán este nombre. No se muestra al destinatario."
                />
                <div className="grid md:grid-cols-2 gap-5 max-w-3xl">
                  <div>
                    <label className="block text-xs font-semibold mb-1 text-gloma-brown-dark">
                      Nombre de la campaña *
                    </label>
                    <input
                      type="text"
                      maxLength={120}
                      value={draft.name}
                      onChange={(e) =>
                        setDraft((d) => ({ ...d, name: e.target.value }))
                      }
                      placeholder="Ej. Promo Día de la Madre 2026"
                      className="w-full px-3 py-2 rounded-lg border border-gloma-brown-light/30 bg-white focus:outline-none focus:border-gloma-brown text-sm"
                    />
                    <p className="text-[11px] text-gloma-brown-light mt-1">
                      {draft.name.length}/120
                    </p>
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-xs font-semibold mb-1 text-gloma-brown-dark">
                      Descripción interna (opcional)
                    </label>
                    <textarea
                      rows={3}
                      maxLength={500}
                      value={draft.description}
                      onChange={(e) =>
                        setDraft((d) => ({
                          ...d,
                          description: e.target.value,
                        }))
                      }
                      placeholder="Objetivo, audiencia, notas para tu equipo…"
                      className="w-full px-3 py-2 rounded-lg border border-gloma-brown-light/30 bg-white focus:outline-none focus:border-gloma-brown text-sm"
                    />
                    <p className="text-[11px] text-gloma-brown-light mt-1">
                      {draft.description.length}/500 — no se envía al
                      destinatario, sólo es referencia interna.
                    </p>
                  </div>
                </div>

                {/* Info meta-account */}
                {metaAccount?.display_phone && (
                  <div className="mt-6 max-w-3xl bg-white border border-gloma-brown-light/20 rounded-xl p-4 text-xs text-gloma-brown-dark">
                    <p className="font-semibold mb-0.5">
                      Cuenta de WhatsApp conectada
                    </p>
                    <p className="text-gloma-brown-light">
                      {metaAccount.verified_name || 'Cuenta sin nombre'} —{' '}
                      <span className="font-mono">
                        {metaAccount.display_phone}
                      </span>
                    </p>
                  </div>
                )}

                <NavBar
                  step={step}
                  canAdvance={canAdvance}
                  onBack={() => router.push('/campanas')}
                  onNext={() => setStep(2)}
                  backLabel="Cancelar"
                />
              </div>
            )}

            {/* ───── Paso 2 ───── */}
            {step === 2 && (
              <div className="p-5 md:p-8 bg-white">
                <StepHeader
                  step={2}
                  title="Elige la plantilla aprobada"
                  subtitle="Sólo aparecen plantillas con estado APPROVED en Meta."
                />

                {!templates || templates.length === 0 ? (
                  <div className="border border-dashed border-gloma-brown-light/30 rounded-xl p-8 text-center max-w-2xl">
                    <div className="w-12 h-12 mx-auto rounded-full bg-gloma-rose-soft flex items-center justify-center text-xl mb-3">
                      📄
                    </div>
                    <h5 className="font-heading text-lg font-bold text-gloma-brown-dark mb-1">
                      No tienes plantillas aprobadas
                    </h5>
                    <p className="text-sm text-gloma-brown-light mb-4">
                      Para enviar campañas necesitas al menos una plantilla
                      aprobada por Meta.
                    </p>
                    <Link href="/campanas/plantillas/nueva" legacyBehavior>
                      <a className="inline-flex items-center justify-center px-4 py-2 rounded-lg bg-gloma-brown text-gloma-cream font-semibold text-sm hover:bg-gloma-brown-dark">
                        Crear plantilla nueva
                      </a>
                    </Link>
                  </div>
                ) : (
                  <>
                    <div className="grid md:grid-cols-3 gap-3 max-w-5xl">
                      {templates.map((t) => {
                        const active = draft.templateId === t.id;
                        return (
                          <label
                            key={t.id}
                            className={`rounded-xl p-4 cursor-pointer transition-colors block ${
                              active
                                ? 'border-2 border-gloma-brown bg-gloma-rose-soft'
                                : 'border border-gloma-brown-light/20 bg-white hover:border-gloma-brown-light/50'
                            }`}
                          >
                            <input
                              type="radio"
                              name="template"
                              className="sr-only"
                              checked={active}
                              onChange={() =>
                                setDraft((d) => ({
                                  ...d,
                                  templateId: t.id,
                                  templateVariables: {},
                                }))
                              }
                            />
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-xs font-semibold text-gloma-brown-dark truncate">
                                {t.name}
                              </span>
                              <span className="text-[10px] px-2 py-0.5 rounded-full bg-green-100 text-green-800 font-semibold">
                                {t.status}
                              </span>
                            </div>
                            <p className="text-[11px] text-gloma-brown-light mb-2">
                              {t.category || '—'} · {t.language}
                            </p>
                            <p className="text-xs text-gloma-brown-dark line-clamp-3">
                              {extractTemplateBody(t) || (
                                <span className="italic text-gloma-brown-light">
                                  (sin cuerpo de texto)
                                </span>
                              )}
                            </p>
                          </label>
                        );
                      })}
                    </div>

                    {/* Vista previa + variables */}
                    {selectedTemplate && (
                      <div className="mt-6 grid md:grid-cols-2 gap-4 max-w-5xl">
                        <div className="bg-gloma-cream border border-gloma-brown-light/20 rounded-xl p-4">
                          <p className="text-xs font-semibold mb-2 text-gloma-brown-dark">
                            Vista previa del cuerpo
                          </p>
                          <pre className="text-xs whitespace-pre-wrap text-gloma-brown-dark font-body bg-white border border-gloma-brown-light/15 rounded p-3">
                            {extractTemplateBody(selectedTemplate) ||
                              '(sin cuerpo)'}
                          </pre>
                        </div>
                        <div className="bg-gloma-cream border border-gloma-brown-light/20 rounded-xl p-4">
                          <p className="text-xs font-semibold mb-2 text-gloma-brown-dark">
                            Variables a interpolar
                          </p>
                          {variableKeys.length === 0 ? (
                            <p className="text-xs text-gloma-brown-light">
                              Esta plantilla no tiene variables. Listo para
                              enviar tal cual.
                            </p>
                          ) : (
                            <div className="space-y-3">
                              {variableKeys.map((k) => (
                                <div key={k}>
                                  <label className="block text-[11px] text-gloma-brown-light mb-1">
                                    {`{{${k}}}`} → valor
                                  </label>
                                  <input
                                    type="text"
                                    value={draft.templateVariables[k] ?? ''}
                                    onChange={(e) =>
                                      setDraft((d) => ({
                                        ...d,
                                        templateVariables: {
                                          ...d.templateVariables,
                                          [k]: e.target.value,
                                        },
                                      }))
                                    }
                                    placeholder={
                                      k === '1' ? '{{contact.name}}' : 'Valor…'
                                    }
                                    className="w-full px-2 py-1.5 text-sm rounded-md border border-gloma-brown-light/30 bg-white focus:outline-none focus:border-gloma-brown"
                                  />
                                </div>
                              ))}
                              <p className="text-[11px] text-gloma-brown-light">
                                Usa <code>{`{{contact.name}}`}</code> para
                                personalizar con el nombre del contacto.
                              </p>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </>
                )}

                <NavBar
                  step={step}
                  canAdvance={canAdvance}
                  onBack={() => setStep(1)}
                  onNext={() => setStep(3)}
                />
              </div>
            )}

            {/* ───── Paso 3 ───── */}
            {step === 3 && (
              <div className="p-5 md:p-8 bg-gloma-cream">
                <StepHeader
                  step={3}
                  title="¿A quién le enviamos?"
                  subtitle="Selecciona un grupo predefinido o elige contactos uno por uno."
                />

                {/* Toggle modo */}
                <div className="inline-flex bg-white border border-gloma-brown-light/20 rounded-full p-1 mb-5 text-xs">
                  <button
                    type="button"
                    onClick={() =>
                      setDraft((d) => ({ ...d, mode: 'group' }))
                    }
                    className={`px-4 py-1.5 rounded-full transition-colors ${
                      draft.mode === 'group'
                        ? 'bg-gloma-brown text-gloma-cream font-semibold'
                        : 'text-gloma-brown-light'
                    }`}
                  >
                    Por grupo
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setDraft((d) => ({ ...d, mode: 'individual' }))
                    }
                    className={`px-4 py-1.5 rounded-full transition-colors ${
                      draft.mode === 'individual'
                        ? 'bg-gloma-brown text-gloma-cream font-semibold'
                        : 'text-gloma-brown-light'
                    }`}
                  >
                    Uno por uno
                  </button>
                </div>

                {/* Aviso S13-003 (transparencia opt-in) */}
                <div className="mb-5 max-w-3xl bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-900">
                  <strong>Nota:</strong> los contactos sin opt-in válido se
                  marcarán automáticamente como omitidos al momento del
                  envío. No se contarán contra tu tarifa.
                </div>

                {draft.mode === 'group' ? (
                  <div className="max-w-3xl">
                    {!groups || groups.length === 0 ? (
                      <div className="border border-dashed border-gloma-brown-light/30 rounded-xl p-6 text-center bg-white">
                        <p className="text-sm text-gloma-brown-light mb-3">
                          Aún no tienes grupos de contactos.
                        </p>
                        <Link href="/campanas/contactos" legacyBehavior>
                          <a className="text-xs underline text-gloma-brown">
                            Crear un grupo
                          </a>
                        </Link>
                      </div>
                    ) : (
                      <div className="bg-white border border-gloma-brown-light/20 rounded-xl p-4">
                        <label className="block text-xs font-semibold mb-2 text-gloma-brown-dark">
                          Grupo de contactos
                        </label>
                        <select
                          value={draft.selectedGroupId ?? ''}
                          onChange={(e) =>
                            setDraft((d) => ({
                              ...d,
                              selectedGroupId: e.target.value
                                ? Number(e.target.value)
                                : null,
                            }))
                          }
                          className="w-full px-3 py-2 rounded-lg border border-gloma-brown-light/30 bg-white text-sm focus:outline-none focus:border-gloma-brown"
                        >
                          <option value="">— Selecciona un grupo —</option>
                          {groups.map((g) => (
                            <option key={g.id} value={g.id}>
                              {g.name} ({g.member_count})
                            </option>
                          ))}
                        </select>
                        {draft.selectedGroupId !== null && (
                          <p className="mt-3 text-xs text-gloma-brown-light">
                            <span className="font-semibold text-gloma-brown-dark">
                              {fmtNumber(totalRecipients)}
                            </span>{' '}
                            destinatarios estimados.
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="max-w-4xl">
                    <div className="bg-white border border-gloma-brown-light/20 rounded-xl p-4">
                      <div className="flex flex-col sm:flex-row gap-2 items-start sm:items-center justify-between mb-3">
                        <input
                          type="text"
                          value={contactSearch}
                          onChange={(e) => setContactSearch(e.target.value)}
                          placeholder="Buscar por nombre o teléfono…"
                          className="flex-1 px-3 py-1.5 rounded-lg border border-gloma-brown-light/30 bg-white text-sm focus:outline-none focus:border-gloma-brown"
                        />
                        <div className="flex gap-2 text-xs">
                          <button
                            type="button"
                            onClick={selectAllOnPage}
                            className="px-3 py-1.5 rounded-md border border-gloma-brown text-gloma-brown hover:bg-gloma-rose-soft/50"
                          >
                            Seleccionar página
                          </button>
                          <button
                            type="button"
                            onClick={clearSelection}
                            className="px-3 py-1.5 rounded-md border border-gloma-brown-light/30 text-gloma-brown-light hover:text-gloma-brown"
                          >
                            Limpiar
                          </button>
                        </div>
                      </div>

                      {!contacts || contacts.length === 0 ? (
                        <p className="text-sm text-gloma-brown-light text-center py-6">
                          No tienes contactos todavía.{' '}
                          <Link
                            href="/campanas/contactos"
                            legacyBehavior
                          >
                            <a className="text-gloma-brown underline">
                              Agregar contactos
                            </a>
                          </Link>
                        </p>
                      ) : pagedContacts.length === 0 ? (
                        <p className="text-sm text-gloma-brown-light text-center py-6">
                          Ningún contacto coincide con tu búsqueda.
                        </p>
                      ) : (
                        <>
                          <div className="overflow-x-auto rounded-lg border border-gloma-brown-light/15">
                            <table className="min-w-full text-sm">
                              <thead className="bg-gloma-cream text-gloma-brown-light">
                                <tr>
                                  <th className="px-3 py-2 w-8 text-left" />
                                  <th className="px-3 py-2 text-left font-medium">
                                    Nombre
                                  </th>
                                  <th className="px-3 py-2 text-left font-medium">
                                    Teléfono
                                  </th>
                                  <th className="px-3 py-2 text-left font-medium">
                                    Opt-in
                                  </th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-gloma-brown-light/10">
                                {pagedContacts.map((c) => {
                                  const checked =
                                    draft.selectedContactIds.has(c.id);
                                  return (
                                    <tr
                                      key={c.id}
                                      className="hover:bg-gloma-rose-soft/30 cursor-pointer"
                                      onClick={() => toggleContact(c.id)}
                                    >
                                      <td className="px-3 py-2">
                                        <input
                                          type="checkbox"
                                          checked={checked}
                                          onChange={() => toggleContact(c.id)}
                                          onClick={(e) => e.stopPropagation()}
                                          className="accent-gloma-brown"
                                        />
                                      </td>
                                      <td className="px-3 py-2 text-gloma-brown-dark">
                                        {c.name || (
                                          <span className="italic text-gloma-brown-light">
                                            (sin nombre)
                                          </span>
                                        )}
                                      </td>
                                      <td className="px-3 py-2 font-mono text-gloma-brown-dark">
                                        {c.phone_e164}
                                      </td>
                                      <td className="px-3 py-2">
                                        {c.opt_in ? (
                                          <span className="text-[11px] px-2 py-0.5 rounded-full bg-green-100 text-green-800">
                                            Sí
                                          </span>
                                        ) : (
                                          <span className="text-[11px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                                            No
                                          </span>
                                        )}
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 mt-3 text-xs text-gloma-brown-light">
                            <span>
                              <strong className="text-gloma-brown-dark">
                                {fmtNumber(draft.selectedContactIds.size)}
                              </strong>{' '}
                              destinatarios seleccionados
                              {draft.selectedContactIds.size > MAX_RECIPIENTS && (
                                <span className="ml-2 text-red-600 font-semibold">
                                  (excede el máximo de{' '}
                                  {fmtNumber(MAX_RECIPIENTS)})
                                </span>
                              )}
                            </span>
                            <div className="flex gap-1">
                              <button
                                type="button"
                                onClick={() =>
                                  setContactsPage((p) => Math.max(1, p - 1))
                                }
                                disabled={contactsPageSafe <= 1}
                                className="px-3 py-1 rounded-md border border-gloma-brown-light/30 bg-white disabled:opacity-40"
                              >
                                ← Anterior
                              </button>
                              <span className="px-3 py-1 rounded-md bg-gloma-brown text-gloma-cream font-semibold">
                                {contactsPageSafe} / {totalContactPages}
                              </span>
                              <button
                                type="button"
                                onClick={() =>
                                  setContactsPage((p) =>
                                    Math.min(totalContactPages, p + 1),
                                  )
                                }
                                disabled={
                                  contactsPageSafe >= totalContactPages
                                }
                                className="px-3 py-1 rounded-md border border-gloma-brown-light/30 bg-white disabled:opacity-40"
                              >
                                Siguiente →
                              </button>
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                )}

                <NavBar
                  step={step}
                  canAdvance={canAdvance}
                  onBack={() => setStep(2)}
                  onNext={() => setStep(4)}
                />
              </div>
            )}

            {/* ───── Paso 4 ───── */}
            {step === 4 && (
              <div className="p-5 md:p-8 bg-white">
                <StepHeader
                  step={4}
                  title="Programación y resumen"
                  subtitle="Revisa todo antes de confirmar. Una vez creada, no se podrán agregar destinatarios."
                />

                <div className="grid md:grid-cols-2 gap-5 max-w-5xl">
                  {/* Cuando enviar */}
                  <div className="bg-gloma-cream border border-gloma-brown-light/20 rounded-xl p-4">
                    <p className="text-xs font-semibold mb-3 text-gloma-brown-dark">
                      ¿Cuándo enviar?
                    </p>
                    <div className="space-y-2 text-sm">
                      <label
                        className={`flex items-start gap-2 p-3 rounded-lg cursor-pointer ${
                          draft.schedule === 'now'
                            ? 'border-2 border-gloma-brown bg-white'
                            : 'border border-gloma-brown-light/20 bg-white'
                        }`}
                      >
                        <input
                          type="radio"
                          name="schedule"
                          checked={draft.schedule === 'now'}
                          onChange={() =>
                            setDraft((d) => ({ ...d, schedule: 'now' }))
                          }
                          className="mt-1 accent-gloma-brown"
                        />
                        <div>
                          <p className="font-semibold text-gloma-brown-dark">
                            Enviar ahora
                          </p>
                          <p className="text-xs text-gloma-brown-light">
                            La campaña se encola inmediatamente.
                          </p>
                        </div>
                      </label>
                      <label
                        className={`flex items-start gap-2 p-3 rounded-lg cursor-pointer ${
                          draft.schedule === 'scheduled'
                            ? 'border-2 border-gloma-brown bg-white'
                            : 'border border-gloma-brown-light/20 bg-white'
                        }`}
                      >
                        <input
                          type="radio"
                          name="schedule"
                          checked={draft.schedule === 'scheduled'}
                          onChange={() =>
                            setDraft((d) => ({
                              ...d,
                              schedule: 'scheduled',
                            }))
                          }
                          className="mt-1 accent-gloma-brown"
                        />
                        <div className="flex-1">
                          <p className="font-semibold text-gloma-brown-dark">
                            Programar para…
                          </p>
                          <input
                            type="datetime-local"
                            value={draft.scheduledAtLocal}
                            onChange={(e) =>
                              setDraft((d) => ({
                                ...d,
                                scheduledAtLocal: e.target.value,
                                schedule: 'scheduled',
                              }))
                            }
                            className="mt-2 w-full px-2 py-1 text-xs rounded border border-gloma-brown-light/30 bg-white"
                          />
                          <p className="text-[11px] text-gloma-brown-light mt-1">
                            Hora local — se enviará como UTC al backend.
                          </p>
                          {draft.schedule === 'scheduled' &&
                            draft.scheduledAtLocal &&
                            !canAdvance && (
                              <p className="text-[11px] text-red-600 mt-1">
                                La fecha debe ser futura.
                              </p>
                            )}
                        </div>
                      </label>
                    </div>
                  </div>

                  {/* Resumen */}
                  <div className="bg-gloma-rose-soft border border-gloma-rose rounded-xl p-4">
                    <p className="text-xs font-semibold mb-3 text-gloma-brown-dark">
                      Resumen
                    </p>
                    <dl className="text-sm space-y-2">
                      <div className="flex justify-between gap-3">
                        <dt className="text-gloma-brown-light">Nombre</dt>
                        <dd className="font-semibold text-gloma-brown-dark text-right truncate">
                          {draft.name || '—'}
                        </dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt className="text-gloma-brown-light">Plantilla</dt>
                        <dd className="font-semibold text-gloma-brown-dark text-right truncate">
                          {selectedTemplate?.name || '—'}
                        </dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt className="text-gloma-brown-light">
                          Destinatarios
                        </dt>
                        <dd className="font-semibold text-gloma-brown-dark">
                          {fmtNumber(totalRecipients)}
                        </dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt className="text-gloma-brown-light">
                          Tiempo estimado
                        </dt>
                        <dd className="font-semibold text-gloma-brown-dark">
                          {fmtDuration(estSeconds)}
                        </dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt className="text-gloma-brown-light">Envío</dt>
                        <dd className="font-semibold text-gloma-brown-dark text-right">
                          {draft.schedule === 'now'
                            ? 'Inmediato'
                            : draft.scheduledAtLocal
                              ? new Date(
                                  draft.scheduledAtLocal,
                                ).toLocaleString('es-MX')
                              : '—'}
                        </dd>
                      </div>
                    </dl>
                    <p className="text-[11px] text-gloma-brown-light mt-3">
                      Al confirmar, los mensajes se envían vía WhatsApp Business
                      API. Sólo destinatarios con opt-in válido recibirán el
                      mensaje (rate: {SEND_RATE_PER_SEC} msg/s).
                    </p>
                  </div>
                </div>

                <NavBar
                  step={step}
                  canAdvance={canAdvance && !submitting}
                  onBack={() => setStep(3)}
                  onNext={handleSubmit}
                  nextLabel={
                    submitting
                      ? 'Creando…'
                      : 'Confirmar y crear campaña'
                  }
                  primaryNext
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </Layout>
  );
}

// ─── Barra de navegación entre pasos ───────────────────────────────────────

function NavBar({
  step,
  canAdvance,
  onBack,
  onNext,
  backLabel,
  nextLabel,
  primaryNext = false,
}: {
  step: number;
  canAdvance: boolean;
  onBack: () => void;
  onNext: () => void;
  backLabel?: string;
  nextLabel?: string;
  primaryNext?: boolean;
}) {
  const defaultBack = step === 1 ? 'Cancelar' : '← Atrás';
  const defaultNext = step === 4 ? 'Confirmar' : 'Continuar →';
  return (
    <div className="flex justify-between mt-6 gap-2">
      <button
        type="button"
        onClick={onBack}
        className="px-4 py-2 text-sm rounded-lg border border-gloma-brown text-gloma-brown bg-white hover:bg-gloma-rose-soft/50"
      >
        {backLabel || defaultBack}
      </button>
      <button
        type="button"
        onClick={onNext}
        disabled={!canAdvance}
        className={`px-5 py-2 text-sm rounded-lg font-semibold disabled:opacity-40 disabled:cursor-not-allowed ${
          primaryNext
            ? 'bg-gloma-brown text-gloma-cream hover:bg-gloma-brown-dark px-6 py-2.5 font-bold'
            : 'bg-gloma-brown text-gloma-cream hover:bg-gloma-brown-dark'
        }`}
      >
        {nextLabel || defaultNext}
      </button>
    </div>
  );
}
