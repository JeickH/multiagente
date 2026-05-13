/**
 * Editor de plantilla WhatsApp (Sprint 13 — tarea #167B).
 *
 * Contrato visual: `identidad_gloma/diseno_campanas.html` pantalla 5
 * (sección `#p5` "Editor de Plantilla") — dos columnas, form a la izquierda,
 * preview tipo WhatsApp en vivo a la derecha (sticky en desktop).
 *
 * Endpoint consumido:
 *   - POST /templates (status 201 → CampaignTemplateOut). Tras éxito,
 *     redirige a /campanas/plantillas para que la nueva plantilla
 *     aparezca con estado PENDING.
 *
 * Validaciones (mirror del backend `WhatsappTemplateCreatePayload`):
 *   - name regex `^[a-z][a-z0-9_]{0,511}$` (Meta-style snake_case).
 *   - body requerido, max 1024 chars.
 *   - footer max 60.
 *   - botón URL: URL válida (http/https). Botón teléfono: E.164.
 *
 * Reglas de Seguridad aplicadas (frontend):
 *   - regla 6: errores backend ya sanitizados; se muestran tal cual.
 *   - no se loggea ningún payload desde cliente.
 */
import Link from 'next/link';
import { useRouter } from 'next/router';
import type { ReactElement } from 'react';
import { useMemo, useState } from 'react';

import Layout from '../../../components/Layout';
import { ApiError, authedFetch } from '../../../lib/api';
import type { TemplatePreview } from '../../../types/campaigns';

// ─── Constantes ────────────────────────────────────────────────────────────

const NAME_REGEX = /^[a-z][a-z0-9_]{0,511}$/;
const E164_REGEX = /^\+?[1-9]\d{6,18}$/;

const LANGUAGES: Array<{ code: string; label: string }> = [
  { code: 'es_MX', label: 'es_MX (Español México)' },
  { code: 'es', label: 'es (Español)' },
  { code: 'en_US', label: 'en_US (English US)' },
  { code: 'pt_BR', label: 'pt_BR (Português BR)' },
];

const CATEGORIES: Array<{ value: 'MARKETING' | 'UTILITY' | 'AUTHENTICATION'; label: string }> = [
  { value: 'MARKETING', label: 'MARKETING' },
  { value: 'UTILITY', label: 'UTILITY' },
  { value: 'AUTHENTICATION', label: 'AUTHENTICATION' },
];

const TYPE_TABS = [
  { id: 'standard', label: 'Estándar', enabled: true },
  { id: 'catalog', label: 'Catalogar', enabled: false },
  { id: 'carousel', label: 'Carrusel', enabled: false },
  { id: 'limited_time', label: 'Ofertas tiempo limitado', enabled: false },
] as const;

type HeaderKind = 'NONE' | 'TEXT' | 'IMAGE' | 'VIDEO' | 'DOCUMENT';
type ButtonKind = 'URL' | 'PHONE_NUMBER';

interface ButtonDraft {
  kind: ButtonKind;
  text: string;
  value: string; // URL o número
}

// ─── Helpers ───────────────────────────────────────────────────────────────

function nextVariableNumber(body: string): number {
  // Encuentra el siguiente {{N}} disponible.
  const used = new Set<number>();
  const re = /\{\{(\d+)\}\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(body))) {
    const n = parseInt(m[1], 10);
    if (!Number.isNaN(n)) used.add(n);
  }
  let i = 1;
  while (used.has(i)) i += 1;
  return i;
}

function isValidUrl(s: string): boolean {
  if (!s) return false;
  try {
    const u = new URL(s);
    return u.protocol === 'http:' || u.protocol === 'https:';
  } catch {
    return false;
  }
}

function renderBodyWithVars(body: string): ReactElement {
  // Render con {{1}} resaltado en color. Soporta *negritas* WhatsApp.
  const parts: Array<{ kind: 'text' | 'var' | 'b'; value: string }> = [];
  // Primero parseamos por placeholders y por *...*. Implementación simple:
  // tokenize en pases.
  let remaining = body;
  // Token regex: combina {{n}} y *texto*.
  const re = /(\{\{\d+\}\})|\*([^*\n]+)\*/g;
  let lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(remaining))) {
    if (m.index > lastIndex) {
      parts.push({ kind: 'text', value: remaining.slice(lastIndex, m.index) });
    }
    if (m[1]) {
      parts.push({ kind: 'var', value: m[1] });
    } else if (m[2] !== undefined) {
      parts.push({ kind: 'b', value: m[2] });
    }
    lastIndex = m.index + m[0].length;
  }
  if (lastIndex < remaining.length) {
    parts.push({ kind: 'text', value: remaining.slice(lastIndex) });
  }
  return (
    <>
      {parts.map((p, i) => {
        if (p.kind === 'var')
          return (
            <span
              key={i}
              className="px-1 rounded bg-gloma-rose-soft text-gloma-brown-dark font-mono text-[10px]"
            >
              {p.value}
            </span>
          );
        if (p.kind === 'b')
          return (
            <strong key={i} className="font-semibold">
              {p.value}
            </strong>
          );
        return <span key={i}>{p.value}</span>;
      })}
    </>
  );
}

// ─── Componente ───────────────────────────────────────────────────────────

export default function EditorPlantillaPage() {
  const router = useRouter();

  // Sección 1
  const [name, setName] = useState('');
  const [category, setCategory] = useState<'MARKETING' | 'UTILITY' | 'AUTHENTICATION'>(
    'MARKETING',
  );
  const [language, setLanguage] = useState<string>('es_MX');

  // Sección 2: tipo de plantilla (solo "standard" funcional)
  const [typeTab, setTypeTab] = useState<typeof TYPE_TABS[number]['id']>(
    'standard',
  );

  // Sección 3: Header
  const [headerKind, setHeaderKind] = useState<HeaderKind>('NONE');
  const [headerText, setHeaderText] = useState('');

  // Sección 4: Body
  const [body, setBody] = useState('');

  // Sección 5: Footer
  const [footer, setFooter] = useState('');

  // Sección 6: Botones
  const [buttons, setButtons] = useState<ButtonDraft[]>([]);

  // Submit state
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);

  // Validaciones derivadas
  const errors = useMemo(() => {
    const errs: Record<string, string> = {};
    if (!name) {
      errs.name = 'Requerido.';
    } else if (!NAME_REGEX.test(name)) {
      errs.name =
        'Solo minúsculas, números y guion bajo. Debe iniciar con letra.';
    }
    if (!body) {
      errs.body = 'Requerido.';
    } else if (body.length > 1024) {
      errs.body = `Máximo 1024 caracteres (actual: ${body.length}).`;
    }
    if (headerKind === 'TEXT' && headerText.length > 60) {
      errs.header = `Máximo 60 caracteres (actual: ${headerText.length}).`;
    }
    if (footer.length > 60) {
      errs.footer = `Máximo 60 caracteres (actual: ${footer.length}).`;
    }
    buttons.forEach((b, i) => {
      if (!b.text.trim()) {
        errs[`btn_text_${i}`] = 'Texto requerido.';
      } else if (b.text.length > 25) {
        errs[`btn_text_${i}`] = 'Máximo 25 caracteres.';
      }
      if (b.kind === 'URL' && !isValidUrl(b.value)) {
        errs[`btn_val_${i}`] = 'URL inválida (debe iniciar con http/https).';
      }
      if (b.kind === 'PHONE_NUMBER' && !E164_REGEX.test(b.value)) {
        errs[`btn_val_${i}`] = 'Teléfono inválido (formato E.164, ej. +521234567890).';
      }
    });
    return errs;
  }, [name, body, headerKind, headerText, footer, buttons]);

  const isValid = Object.keys(errors).length === 0;

  const addVariable = () => {
    const n = nextVariableNumber(body);
    setBody((prev) => `${prev}{{${n}}}`);
  };

  const addButton = () => {
    if (buttons.length >= 3) return;
    setButtons((prev) => [
      ...prev,
      { kind: 'URL', text: '', value: '' },
    ]);
  };

  const updateButton = (i: number, patch: Partial<ButtonDraft>) => {
    setButtons((prev) =>
      prev.map((b, idx) => (idx === i ? { ...b, ...patch } : b)),
    );
  };

  const removeButton = (i: number) => {
    setButtons((prev) => prev.filter((_, idx) => idx !== i));
  };

  const buildComponents = (): Array<Record<string, unknown>> => {
    const components: Array<Record<string, unknown>> = [];
    if (headerKind === 'TEXT' && headerText.trim()) {
      components.push({
        type: 'HEADER',
        format: 'TEXT',
        text: headerText.trim(),
      });
    } else if (headerKind !== 'NONE' && headerKind !== 'TEXT') {
      // Media headers: el backend valida la estructura mínima. Por ahora
      // solo declaramos el format — la asset URL queda como follow-up.
      components.push({
        type: 'HEADER',
        format: headerKind,
      });
    }
    components.push({ type: 'BODY', text: body });
    if (footer.trim()) {
      components.push({ type: 'FOOTER', text: footer.trim() });
    }
    if (buttons.length > 0) {
      components.push({
        type: 'BUTTONS',
        buttons: buttons.map((b) =>
          b.kind === 'URL'
            ? { type: 'URL', text: b.text.trim(), url: b.value.trim() }
            : {
                type: 'PHONE_NUMBER',
                text: b.text.trim(),
                phone_number: b.value.trim(),
              },
        ),
      });
    }
    return components;
  };

  const handleSubmit = async () => {
    if (!isValid || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);
    const payload = {
      name,
      category,
      language,
      components: buildComponents(),
    };
    try {
      await authedFetch<TemplatePreview>('/templates', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setSubmitSuccess(
        'Plantilla enviada. Estado: Pendiente de aprobación de WhatsApp.',
      );
      setTimeout(() => {
        router.push('/campanas/plantillas');
      }, 2000);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : 'No se pudo enviar la plantilla.';
      setSubmitError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  // ─── Preview helpers ──────────────────────────────────────────────────
  const previewHeader =
    headerKind === 'TEXT' && headerText.trim() ? headerText.trim() : null;
  const previewBody = body || 'Tu mensaje aparecerá aquí…';
  const previewFooter = footer.trim();

  return (
    <Layout variant="fullscreen">
      <div className="p-6 md:p-8 w-full bg-gloma-cream min-h-screen font-body">
        {/* Header + breadcrumb */}
        <div className="mb-6">
          <p className="text-[11px] text-gloma-brown-light mb-1">
            <Link href="/campanas" legacyBehavior>
              <a className="hover:text-gloma-brown hover:underline">
                Transmisiones masivas
              </a>
            </Link>
            <span className="mx-1">/</span>
            <Link href="/campanas/plantillas" legacyBehavior>
              <a className="hover:text-gloma-brown hover:underline">
                Plantillas
              </a>
            </Link>
            <span className="mx-1">/</span>
            <span>Nueva</span>
          </p>
          <h1 className="font-heading text-2xl md:text-3xl font-extrabold text-gloma-brown-dark">
            Editor de Plantilla
          </h1>
          <p className="text-sm text-gloma-brown-light mt-1 max-w-2xl">
            Formulario a la izquierda + preview WhatsApp en vivo a la derecha.
          </p>
        </div>

        {/* Banner aprobación */}
        <div className="bg-gloma-rose-soft border border-gloma-rose rounded-lg px-4 py-3 mb-5 flex items-start gap-2 text-sm text-gloma-brown-darker">
          <span aria-hidden className="text-lg">
            ℹ️
          </span>
          <p>
            <strong>
              Esta plantilla se enviará a WhatsApp para aprobación.
            </strong>{' '}
            Puede tardar hasta 24 horas en aprobarse. El estado inicial será{' '}
            <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-semibold text-[10px]">
              PENDING
            </span>
            .
          </p>
        </div>

        {/* Mensajes de submit */}
        {submitError && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">
            {submitError}
          </div>
        )}
        {submitSuccess && (
          <div className="bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-lg mb-4 text-sm">
            {submitSuccess}
          </div>
        )}

        {/* Grid 2 columnas */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* ─── FORM (izquierda) ──────────────────────────────────────── */}
          <div className="bg-white border border-gloma-brown-light/20 rounded-2xl p-5 md:p-6 shadow-sm space-y-6">
            {/* Sección 1: identidad */}
            <section>
              <h2 className="font-heading text-sm uppercase tracking-widest text-gloma-brown-light mb-3">
                1 · Identidad
              </h2>
              <div className="grid grid-cols-1 gap-3">
                <div>
                  <label className="block text-xs font-semibold mb-1 text-gloma-brown-dark">
                    Nombre de la plantilla *
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) =>
                      setName(e.target.value.toLowerCase().replace(/\s+/g, '_'))
                    }
                    placeholder="promo_dia_madres_v3"
                    className={`w-full px-3 py-2 rounded-lg border bg-white text-sm font-mono focus:outline-none ${
                      errors.name
                        ? 'border-red-300 focus:border-red-500'
                        : 'border-gloma-brown-light/30 focus:border-gloma-brown'
                    }`}
                  />
                  <p className="text-[10px] text-gloma-brown-light mt-1">
                    snake_case · solo a-z, 0-9, _
                  </p>
                  {errors.name && (
                    <p className="text-[11px] text-red-600 mt-1">
                      {errors.name}
                    </p>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold mb-1 text-gloma-brown-dark">
                      Categoría *
                    </label>
                    <select
                      value={category}
                      onChange={(e) =>
                        setCategory(
                          e.target.value as
                            | 'MARKETING'
                            | 'UTILITY'
                            | 'AUTHENTICATION',
                        )
                      }
                      className="w-full px-3 py-2 rounded-lg border border-gloma-brown-light/30 bg-white text-sm focus:outline-none focus:border-gloma-brown"
                    >
                      {CATEGORIES.map((c) => (
                        <option key={c.value} value={c.value}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold mb-1 text-gloma-brown-dark">
                      Lenguaje *
                    </label>
                    <select
                      value={language}
                      onChange={(e) => setLanguage(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg border border-gloma-brown-light/30 bg-white text-sm focus:outline-none focus:border-gloma-brown"
                    >
                      {LANGUAGES.map((l) => (
                        <option key={l.code} value={l.code}>
                          {l.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
            </section>

            {/* Sección 2: tipo */}
            <section>
              <h2 className="font-heading text-sm uppercase tracking-widest text-gloma-brown-light mb-3">
                2 · Tipo de plantilla
              </h2>
              <div className="flex flex-wrap gap-2">
                {TYPE_TABS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    disabled={!t.enabled}
                    onClick={() => t.enabled && setTypeTab(t.id)}
                    className={`relative px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                      typeTab === t.id && t.enabled
                        ? 'border-gloma-brown bg-gloma-brown text-gloma-cream font-semibold'
                        : t.enabled
                          ? 'border-gloma-brown-light/30 bg-white text-gloma-brown-dark hover:bg-gloma-rose-soft'
                          : 'border-gloma-brown-light/20 bg-gloma-cream text-gloma-brown-light cursor-not-allowed'
                    }`}
                  >
                    {t.label}
                    {!t.enabled && (
                      <span className="ml-1 inline-block px-1 py-px text-[9px] rounded bg-gloma-rose text-gloma-brown-darker font-bold">
                        PRO
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </section>

            {/* Sección 3: Header */}
            <section>
              <h2 className="font-heading text-sm uppercase tracking-widest text-gloma-brown-light mb-3">
                3 · Título (opcional)
              </h2>
              <div className="flex flex-wrap gap-2 mb-2 text-xs">
                {(['NONE', 'TEXT', 'IMAGE', 'VIDEO', 'DOCUMENT'] as HeaderKind[]).map(
                  (k) => (
                    <label
                      key={k}
                      className={`px-2.5 py-1 rounded border cursor-pointer transition-colors ${
                        headerKind === k
                          ? 'border-gloma-brown bg-gloma-brown text-gloma-cream font-semibold'
                          : 'border-gloma-brown-light/30 bg-white text-gloma-brown-dark hover:bg-gloma-rose-soft'
                      }`}
                    >
                      <input
                        type="radio"
                        name="headerKind"
                        className="sr-only"
                        checked={headerKind === k}
                        onChange={() => setHeaderKind(k)}
                      />
                      {k === 'NONE'
                        ? 'Ninguno'
                        : k.charAt(0) + k.slice(1).toLowerCase()}
                    </label>
                  ),
                )}
              </div>
              {headerKind === 'TEXT' && (
                <div>
                  <input
                    type="text"
                    value={headerText}
                    onChange={(e) => setHeaderText(e.target.value)}
                    placeholder="🌷 ¡Feliz Día de las Madres!"
                    maxLength={60}
                    className={`w-full px-3 py-2 rounded-lg border bg-white text-sm focus:outline-none ${
                      errors.header
                        ? 'border-red-300 focus:border-red-500'
                        : 'border-gloma-brown-light/30 focus:border-gloma-brown'
                    }`}
                  />
                  <p className="text-[10px] text-gloma-brown-light mt-1">
                    {headerText.length}/60
                  </p>
                </div>
              )}
              {headerKind !== 'NONE' && headerKind !== 'TEXT' && (
                <p className="text-[11px] text-gloma-brown-light italic">
                  Tipo {headerKind} declarado. La carga del archivo se hará en
                  una versión próxima (la plantilla se enviará sin asset).
                </p>
              )}
            </section>

            {/* Sección 4: Body */}
            <section>
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-heading text-sm uppercase tracking-widest text-gloma-brown-light">
                  4 · Cuerpo *
                </h2>
                <button
                  type="button"
                  onClick={addVariable}
                  className="text-[11px] px-2 py-1 rounded border border-gloma-brown-light/30 bg-white hover:bg-gloma-rose-soft text-gloma-brown-dark font-semibold"
                >
                  + Agregar variable
                </button>
              </div>
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={6}
                maxLength={1024}
                placeholder="Hola {{1}}, tenemos una sorpresa para ti…"
                className={`w-full px-3 py-2 rounded-lg border bg-white text-sm font-mono focus:outline-none ${
                  errors.body
                    ? 'border-red-300 focus:border-red-500'
                    : 'border-gloma-brown-light/30 focus:border-gloma-brown'
                }`}
              />
              <div className="flex justify-between text-[10px] text-gloma-brown-light mt-1">
                <span>
                  Usa <code className="bg-gloma-cream px-1 rounded">{`{{1}}`}</code>,{' '}
                  <code className="bg-gloma-cream px-1 rounded">{`{{2}}`}</code>… para
                  variables. Negritas con *texto*.
                </span>
                <span>{body.length}/1024</span>
              </div>
              {errors.body && (
                <p className="text-[11px] text-red-600 mt-1">{errors.body}</p>
              )}
            </section>

            {/* Sección 5: Footer */}
            <section>
              <h2 className="font-heading text-sm uppercase tracking-widest text-gloma-brown-light mb-3">
                5 · Pie de página (opcional)
              </h2>
              <input
                type="text"
                value={footer}
                onChange={(e) => setFooter(e.target.value)}
                maxLength={60}
                placeholder="Responde STOP para dejar de recibir promociones."
                className={`w-full px-3 py-2 rounded-lg border bg-white text-sm focus:outline-none ${
                  errors.footer
                    ? 'border-red-300 focus:border-red-500'
                    : 'border-gloma-brown-light/30 focus:border-gloma-brown'
                }`}
              />
              <p className="text-[10px] text-gloma-brown-light mt-1">
                {footer.length}/60
              </p>
              {errors.footer && (
                <p className="text-[11px] text-red-600 mt-1">{errors.footer}</p>
              )}
            </section>

            {/* Sección 6: Botones */}
            <section>
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-heading text-sm uppercase tracking-widest text-gloma-brown-light">
                  6 · Botones (opcional, máx 3)
                </h2>
                <button
                  type="button"
                  onClick={addButton}
                  disabled={buttons.length >= 3}
                  className="text-[11px] px-2 py-1 rounded border border-gloma-brown-light/30 bg-white hover:bg-gloma-rose-soft text-gloma-brown-dark font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  + Agregar botón
                </button>
              </div>
              <div className="space-y-2">
                {buttons.length === 0 && (
                  <p className="text-[11px] text-gloma-brown-light italic">
                    Sin botones. Agrega hasta 3 (URL o teléfono).
                  </p>
                )}
                {buttons.map((b, i) => (
                  <div
                    key={i}
                    className="flex flex-col gap-2 p-3 rounded-lg bg-gloma-cream border border-gloma-brown-light/20"
                  >
                    <div className="flex gap-2 items-center">
                      <select
                        value={b.kind}
                        onChange={(e) =>
                          updateButton(i, {
                            kind: e.target.value as ButtonKind,
                            value: '',
                          })
                        }
                        className="text-xs px-2 py-1.5 rounded border border-gloma-brown-light/30 bg-white"
                      >
                        <option value="URL">Visitar sitio web (URL)</option>
                        <option value="PHONE_NUMBER">
                          Llamar a un número
                        </option>
                      </select>
                      <input
                        type="text"
                        value={b.text}
                        onChange={(e) =>
                          updateButton(i, { text: e.target.value })
                        }
                        placeholder="Texto del botón"
                        maxLength={25}
                        className={`flex-1 text-xs px-2 py-1.5 rounded border bg-white ${
                          errors[`btn_text_${i}`]
                            ? 'border-red-300'
                            : 'border-gloma-brown-light/30'
                        }`}
                      />
                      <button
                        type="button"
                        onClick={() => removeButton(i)}
                        className="text-red-600 hover:text-red-700 text-xs font-bold"
                        aria-label="Eliminar botón"
                      >
                        ✕
                      </button>
                    </div>
                    <input
                      type="text"
                      value={b.value}
                      onChange={(e) =>
                        updateButton(i, { value: e.target.value })
                      }
                      placeholder={
                        b.kind === 'URL' ? 'https://…' : '+5215512345678'
                      }
                      className={`text-xs px-2 py-1.5 rounded border bg-white ${
                        errors[`btn_val_${i}`]
                          ? 'border-red-300'
                          : 'border-gloma-brown-light/30'
                      }`}
                    />
                    {(errors[`btn_text_${i}`] || errors[`btn_val_${i}`]) && (
                      <p className="text-[11px] text-red-600">
                        {errors[`btn_text_${i}`] || errors[`btn_val_${i}`]}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </section>

            {/* Acciones inferiores */}
            <div className="flex flex-col sm:flex-row justify-between gap-2 pt-4 border-t border-gloma-brown-light/15">
              <button
                type="button"
                disabled
                title="Próximamente"
                className="px-4 py-2 text-sm rounded-lg border border-gloma-brown-light/30 bg-white text-gloma-brown-light cursor-not-allowed"
              >
                Guardar como borrador
              </button>
              <div className="flex gap-2">
                <Link href="/campanas/plantillas" legacyBehavior>
                  <a className="px-4 py-2 text-sm rounded-lg border border-gloma-brown-light/30 bg-white text-gloma-brown-dark hover:bg-gloma-rose-soft inline-flex items-center">
                    Cancelar
                  </a>
                </Link>
                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={!isValid || submitting || !!submitSuccess}
                  className="px-5 py-2 text-sm rounded-lg bg-gloma-brown text-gloma-cream font-semibold hover:bg-gloma-brown-dark disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {submitting
                    ? 'Enviando…'
                    : submitSuccess
                      ? 'Enviada ✓'
                      : 'Guardar y enviar a aprobación'}
                </button>
              </div>
            </div>
          </div>

          {/* ─── PREVIEW (derecha) ─────────────────────────────────────── */}
          <div className="md:sticky md:top-6 self-start">
            <div className="bg-gloma-brown-darker rounded-2xl p-5 md:p-6 shadow-sm">
              <p className="text-center text-[10px] uppercase tracking-widest text-gloma-rose mb-3">
                Vista previa
              </p>
              <div className="w-full max-w-xs mx-auto">
                <div className="rounded-[2rem] border-[6px] border-gloma-brown-dark overflow-hidden shadow-xl bg-white">
                  {/* Header WhatsApp */}
                  <div className="bg-[#075E54] text-white px-3 py-2 flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full bg-gloma-rose flex items-center justify-center text-[10px] font-bold text-gloma-brown-darker">
                      G
                    </div>
                    <div className="text-xs">
                      <p className="font-semibold leading-tight">
                        Gloma Beauty
                      </p>
                      <p className="text-[9px] opacity-75">en línea</p>
                    </div>
                  </div>
                  {/* Body conversación */}
                  <div
                    className="p-3 min-h-[320px]"
                    style={{
                      backgroundColor: '#ECE5DD',
                      backgroundImage:
                        'radial-gradient(rgba(0,0,0,0.04) 1px, transparent 1px)',
                      backgroundSize: '14px 14px',
                    }}
                  >
                    <div className="bg-white rounded-lg rounded-tl-none px-3 py-2 shadow-sm max-w-[92%]">
                      {/* Header del mensaje */}
                      {previewHeader && (
                        <p className="text-xs font-semibold text-gloma-brown-darker mb-1">
                          {previewHeader}
                        </p>
                      )}
                      {headerKind === 'IMAGE' && (
                        <div className="mb-2 h-20 rounded bg-gloma-rose-soft flex items-center justify-center text-xs text-gloma-brown-light">
                          🖼️ Imagen
                        </div>
                      )}
                      {headerKind === 'VIDEO' && (
                        <div className="mb-2 h-20 rounded bg-gloma-rose-soft flex items-center justify-center text-xs text-gloma-brown-light">
                          🎞️ Video
                        </div>
                      )}
                      {headerKind === 'DOCUMENT' && (
                        <div className="mb-2 h-12 rounded bg-gloma-rose-soft flex items-center justify-center text-xs text-gloma-brown-light">
                          📄 Documento
                        </div>
                      )}
                      {/* Body */}
                      <p className="text-xs text-gray-800 leading-snug whitespace-pre-wrap">
                        {renderBodyWithVars(previewBody)}
                      </p>
                      {/* Footer */}
                      {previewFooter && (
                        <p className="text-[10px] text-gray-500 mt-2 italic">
                          {previewFooter}
                        </p>
                      )}
                      {/* Botones */}
                      {buttons.length > 0 && (
                        <div className="mt-2 border-t border-gray-200 pt-1.5 space-y-1">
                          {buttons.map((b, i) => (
                            <button
                              key={i}
                              type="button"
                              className="block w-full text-[11px] text-[#00a884] py-1 border-t border-gray-100 first:border-t-0"
                            >
                              {b.kind === 'URL' ? '🔗' : '📞'}{' '}
                              {b.text || (b.kind === 'URL' ? 'Visitar' : 'Llamar')}
                            </button>
                          ))}
                        </div>
                      )}
                      <p className="text-[9px] text-right text-gray-400 mt-1">
                        ahora ✓✓
                      </p>
                    </div>
                  </div>
                </div>
                <p className="text-center text-[10px] text-gloma-rose-soft mt-3">
                  Esto verá tu cliente en WhatsApp
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
}
