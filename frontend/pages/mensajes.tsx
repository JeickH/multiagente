import { useCallback, useEffect, useRef, useState } from 'react';
import GrabadorVoz from '../components/GrabadorVoz';
import Layout from '../components/Layout';
import SelectorEmoji from '../components/SelectorEmoji';
import Paginacion, {
  OPCIONES_POR_PAGINA,
  guardarPorPagina,
  leerPorPagina,
} from '../components/Paginacion';
import TutorialOverlay from '../components/TutorialOverlay';
import {
  ACCEPT_ADJUNTO,
  ClaseAdjunto,
  MAX_CAPTION,
  etiquetaDeClase,
  subirAdjunto,
  tamanoLegible,
  validarAdjunto,
} from '../lib/adjuntos';
import { horaCorta } from '../lib/fechas';
import { formatearWhatsapp } from '../lib/formatoWhatsapp';
import { getToken } from '../lib/session';

const MENSAJES_TUTORIAL = [
  {
    selector: '[data-tour="conv-list"]',
    title: 'Lista de conversaciones',
    body: 'Aquí ves todas las conversaciones de WhatsApp del equipo. Haz click en cualquiera para abrirla y leer su historial completo a la derecha.',
  },
  {
    selector: '[data-tour="conv-filters"]',
    title: 'Filtros por estado',
    body: 'Usa estos chips para ver sólo las charlas Abiertas, Pendientes o Cerradas. Es la forma rápida de revisar qué mensajes están asignados a tu equipo o esperan respuesta.',
  },
  {
    selector: '[data-tour="reply-composer"]',
    title: 'Responder manualmente',
    body: 'Cuando selecciones una conversación, escribe aquí tu respuesta y pulsa "Enviar" (o Enter). Con el clip 📎 adjuntas una foto, un video o un PDF, y con el micrófono 🎤 grabas una nota de voz. El mensaje sale por la cuenta de WhatsApp conectada en Mi Plan.',
  },
  {
    selector: '[data-tour="user-badge"]',
    title: 'Tu usuario conectado',
    body: 'Esta es la sesión activa. Cada mensaje saliente queda asociado a tu usuario; los otros miembros del equipo también pueden responder en paralelo desde sus propias sesiones.',
  },
];

type Conversation = {
  id: number;
  contact_wa_id: string;
  contact_name: string | null;
  status: string;
  assigned_to?: string;
  last_message_at: string;
  last_message_preview: string | null;
  /**
   * Etiqueta que el bot le pone a la conversación. Hoy la única es
   * "conversación abandonada" (la pone el seguimiento cuando la persona no
   * volvió a escribir). `null` = sin etiqueta, y entonces no se pinta nada.
   */
  etiqueta?: string | null;
};

type Message = {
  id: number;
  direction: 'inbound' | 'outbound';
  content: string;
  message_type: string;
  status: string;
  created_at: string;
};

type ConversationPage = {
  conversaciones: Conversation[];
  total: number;
  pagina: number;
  por_pagina: number;
};

type ConversationDetail = {
  id: number;
  contact_wa_id: string;
  contact_name: string | null;
  status: string;
  assigned_to?: string;
  last_message_at: string;
  etiqueta?: string | null;
  messages: Message[];
};

/** Un archivo elegido o grabado, todavía sin enviar. */
type AdjuntoLocal = {
  archivo: File;
  clase: ClaseAdjunto;
  /** `URL.createObjectURL` para la vista previa. Se revoca al soltarlo. */
  url: string;
  /** Lo que se muestra: el nombre del archivo, o "Nota de voz" si se grabó. */
  titulo: string;
};

type TeamMe = {
  team: { id: number; nombre: string; owner_user_id: number };
  member: {
    id: number;
    user_id: number;
    role: string;
    nombre: string | null;
    correo: string | null;
    permissions: Record<string, boolean>;
  };
};

const FILTERS = [
  { key: 'todas', label: 'Todas' },
  { key: 'open', label: 'Abierto' },
  { key: 'pending', label: 'Pendiente' },
  { key: 'closed', label: 'Cerrado' },
];

// Cada cuánto el navegador vuelve a preguntar. Son dos ritmos distintos porque
// responden a dos preguntas distintas:
//
//   LISTA (45 s) — "¿entró alguna conversación nueva?". Decisión del CEO el
//     20-ago-2026, bajando de 8 s: con la lista paginada cada pregunta cuesta 4
//     consultas en vez de 602, pero seguía preguntando 450 veces por hora y por
//     pestaña para oír "nada nuevo" casi siempre. A 45 s son 80.
//   DETALLE (5 s) — "¿contestó la persona con la que estoy hablando AHORA?".
//     Este no se toca: es el que hace que una conversación abierta se sienta
//     viva, y son los segundos que una asesora está esperando mirando la
//     pantalla.
//
// El costo de la lista más lenta: un chat nuevo puede tardar hasta 45 s en
// aparecer en la bandeja. Los mensajes de la conversación ya abierta NO se
// atrasan — esos los trae el poll del detalle.
//
// Lo que de verdad resuelve esto es que el servidor avise (SSE/websocket) en
// vez de que el navegador pregunte. Anotado en la BITÁCORA.
const POLL_LISTA_MS = 45000;
const POLL_DETALLE_MS = 5000;

function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Hora de Colombia. Ver `lib/fechas.ts`: el backend serializa UTC sin marcarlo. */
function formatTime(iso: string): string {
  return horaCorta(iso);
}

function initials(name: string | null, fallback: string): string {
  const src = (name || fallback || '?').trim();
  return src.slice(0, 2).toUpperCase();
}

/**
 * Lo que sale de la plataforma como imagen, audio, video o documento se guarda
 * en `content` con el formato `caption\nURL` (ver `bot_runner._send_media`, y
 * ahora también el endpoint `/adjunto` que usa el composer de abajo), así que
 * el archivo se puede mostrar acá sin columnas nuevas: la URL ya es pública, es
 * exactamente la misma que se le envió al cliente por WhatsApp.
 *
 * Lo que manda el *cliente* llega igual desde que el webhook lo baja del
 * proveedor y lo guarda como nuestro: el contenido queda `[imagen]\nURL`, con
 * el marcador delante porque es lo que lee el bot. Por eso el caption de un
 * entrante se descarta al pintarlo — decir "[imagen]" encima de la imagen
 * sobra.
 *
 * Si la descarga falló (o es un mensaje viejo, anterior a esto), no hay URL y
 * queda solo el marcador: ahí la burbuja lo dice con todas las letras en vez de
 * mostrar un "[imagen]" suelto que parece un error.
 */
const URL_EN_TEXTO = /https?:\/\/\S+/;
const TIPOS_VISIBLES = ['image', 'imagen', 'video', 'audio', 'document', 'documento'];

function Contenido({ mensaje }: { mensaje: Message }) {
  const tipo = (mensaje.message_type || '').toLowerCase();
  const encontrada = mensaje.content.match(URL_EN_TEXTO);
  const url = encontrada ? encontrada[0] : null;
  const caption = url ? mensaje.content.replace(url, '').trim() : mensaje.content;

  if (url && TIPOS_VISIBLES.includes(tipo)) {
    const esDocumento = tipo === 'document' || tipo === 'documento';
    const entrante = mensaje.direction === 'inbound';
    // En un entrante el "caption" es el marcador que lee el bot (`[imagen]`),
    // no algo que el cliente escribió: no se pinta.
    const pie = entrante ? '' : caption;
    return (
      <div className="space-y-1.5">
        {pie && (
          <div className="text-sm whitespace-pre-wrap break-words">{formatearWhatsapp(pie)}</div>
        )}
        {tipo === 'video' ? (
          <video src={url} controls className="rounded-lg max-h-72 w-full bg-black/10" />
        ) : tipo === 'audio' ? (
          // Una nota de voz se escucha, no se lee. El reproductor nativo trae
          // play, barra y volumen sin librerías; `preload="metadata"` baja solo
          // la cabecera para poder mostrar la duración sin descargar el audio
          // de cada burbuja del historial.
          <audio src={url} controls preload="metadata" className="w-60 max-w-full" />
        ) : esDocumento ? (
          <div className="flex items-center gap-2 rounded-lg bg-white/10 px-3 py-2">
            <span className="text-lg leading-none">📄</span>
            <span className="text-sm">
              {entrante ? 'Documento del cliente' : 'Documento enviado'}
            </span>
          </div>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={url}
            alt={entrante ? 'Imagen que envió el cliente' : caption || 'Imagen enviada al cliente'}
            loading="lazy"
            className="rounded-lg max-h-72 object-contain bg-white/10"
          />
        )}
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="block text-[10px] underline opacity-70 hover:opacity-100"
        >
          {esDocumento ? 'abrir documento' : 'abrir original'}
        </a>
      </div>
    );
  }

  // Adjunto del cliente: no lo tenemos guardado, solo sabemos que llegó.
  if (mensaje.direction === 'inbound' && !url && /^\[.+\]$/.test(mensaje.content.trim())) {
    const etiqueta = mensaje.content.trim().slice(1, -1);
    return (
      <div className="text-sm italic text-gray-500">
        📎 {etiqueta} — el archivo queda en WhatsApp, todavía no se ve aquí
      </div>
    );
  }

  // `formatearWhatsapp` pinta `*negrilla*`, `_cursiva_`, `~tachado~` y
  // `` `mono` `` como los ve el cliente en su celular — antes se veían los
  // asteriscos crudos. Devuelve nodos de React, nunca HTML: el texto lo escribe
  // un tercero (ver `lib/formatoWhatsapp.ts`). `whitespace-pre-wrap` se queda:
  // los saltos de línea siguen viviendo dentro del texto.
  return (
    <div className="text-sm whitespace-pre-wrap break-words">
      {formatearWhatsapp(mensaje.content)}
    </div>
  );
}

/**
 * Lo que está a punto de salir. Se ve ANTES de enviar y con el mismo control
 * con que se verá en la burbuja (imagen, `<video>`, `<audio>`): mandarle una
 * foto equivocada a un cliente no se puede deshacer, así que la pantalla
 * muestra el archivo, su peso y una equis para arrepentirse.
 */
function VistaPreviaAdjunto({
  adjunto,
  subiendo,
  onQuitar,
}: {
  adjunto: AdjuntoLocal;
  subiendo: boolean;
  onQuitar: () => void;
}) {
  return (
    <div className="mb-2 flex items-start gap-3 p-3 rounded-lg border border-gloma-rose-soft bg-gloma-rose-soft/40">
      <div className="flex-shrink-0">
        {adjunto.clase === 'image' ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={adjunto.url}
            alt={adjunto.titulo}
            className="h-20 w-20 object-cover rounded-lg bg-white"
          />
        ) : adjunto.clase === 'video' ? (
          <video src={adjunto.url} controls className="h-20 rounded-lg bg-black/10" />
        ) : adjunto.clase === 'audio' ? (
          <audio src={adjunto.url} controls className="w-64 max-w-full" />
        ) : (
          <div className="h-20 w-20 rounded-lg bg-white flex items-center justify-center text-3xl">
            📄
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-gray-800 truncate">{adjunto.titulo}</div>
        <div className="text-xs text-gray-500">
          {etiquetaDeClase(adjunto.clase)} · {tamanoLegible(adjunto.archivo.size)}
        </div>
        {adjunto.clase === 'audio' ? (
          <div className="text-xs text-gray-500 mt-1">
            Escúchala antes de enviarla. Las notas de voz salen sin texto.
          </div>
        ) : (
          <div className="text-xs text-gray-500 mt-1">
            Puedes escribir abajo un comentario para acompañarla (opcional).
          </div>
        )}
        {subiendo && (
          <div className="text-xs text-gloma-brown font-medium mt-1" aria-live="polite">
            Enviando…
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={onQuitar}
        disabled={subiendo}
        aria-label="Quitar el archivo adjunto"
        title="Quitar"
        className="text-gray-400 hover:text-gray-700 text-lg leading-none px-1 disabled:opacity-40"
      >
        ×
      </button>
    </div>
  );
}

export default function Mensajes() {
  const [me, setMe] = useState<TeamMe | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [filter, setFilter] = useState<string>('todas');
  const [search, setSearch] = useState('');
  // Lo que se escribió vs. lo que ya se le pidió al backend (ver el debounce).
  const [searchAplicado, setSearchAplicado] = useState('');
  const [pagina, setPagina] = useState(1);
  const [porPagina, setPorPagina] = useState(OPCIONES_POR_PAGINA[0]);
  const [total, setTotal] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [newPhone, setNewPhone] = useState('');
  const [newName, setNewName] = useState('');
  const [newTemplate, setNewTemplate] = useState('plantilla_prueba_1');
  const [newLang, setNewLang] = useState('es_CO');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [adjunto, setAdjunto] = useState<AdjuntoLocal | null>(null);
  const [grabando, setGrabando] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  // Espejo del adjunto para poder revocar su object URL sin meter un efecto
  // secundario dentro del updater de `setState` (React lo llama dos veces en
  // desarrollo).
  const adjuntoRef = useRef<AdjuntoLocal | null>(null);

  // El "por página" elegido se recuerda entre visitas. Se lee en un efecto y
  // no en el `useState` porque `localStorage` no existe en el render del
  // servidor y Next.js marcaría el HTML como distinto al del cliente.
  useEffect(() => {
    setPorPagina(leerPorPagina('mensajes.porPagina'));
  }, []);

  // Cargar /teams/me
  useEffect(() => {
    fetch('/api/teams/me', { headers: authHeaders() })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: TeamMe) => setMe(data))
      .catch((err) => setMeError(err.message || 'Error cargando equipo'));
  }, []);

  // La búsqueda no dispara una consulta por tecla: se espera a que la persona
  // deje de escribir. Sin esto, "marcela" son siete consultas y seis se tiran.
  useEffect(() => {
    const t = setTimeout(() => setSearchAplicado(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  // Cambiar de filtro, de búsqueda o de tamaño de página vuelve a la primera.
  // Si no, se queda uno en la página 7 de un resultado que tiene 2 y la
  // pantalla aparece vacía sin explicar por qué.
  useEffect(() => {
    setPagina(1);
  }, [filter, searchAplicado, porPagina]);

  // Cargar conversaciones (ver POLL_LISTA_MS).
  //
  // El filtro y la búsqueda viajan al backend en vez de aplicarse sobre lo que
  // ya se descargó: si se recortaran acá, "20 por página" filtraría dentro de
  // esas 20 y el usuario vería "no hay pendientes" teniendo pendientes tres
  // páginas más abajo.
  useEffect(() => {
    if (!me) return;
    let active = true;
    const params = new URLSearchParams({
      limite: String(porPagina),
      pagina: String(pagina),
    });
    if (filter !== 'todas') params.set('estado', filter);
    if (searchAplicado) params.set('busqueda', searchAplicado);

    const load = () =>
      fetch(`/api/mensajes/conversaciones?${params.toString()}`, { headers: authHeaders() })
        .then((res) => (res.ok ? res.json() : null))
        .then((data: ConversationPage | null) => {
          if (!active || !data) return;
          setConversations(data.conversaciones || []);
          setTotal(data.total || 0);
        })
        .catch(() => {});
    load();
    const t = setInterval(load, POLL_LISTA_MS);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, [me, filter, searchAplicado, pagina, porPagina]);

  // Cargar detalle al seleccionar (ver POLL_DETALLE_MS)
  useEffect(() => {
    if (selectedId == null) {
      setDetail(null);
      return;
    }
    let active = true;
    const load = () =>
      fetch(`/api/mensajes/conversaciones/${selectedId}`, { headers: authHeaders() })
        .then((res) => (res.ok ? res.json() : null))
        .then((data: ConversationDetail | null) => {
          if (active && data) setDetail(data);
        })
        .catch(() => {});
    load();
    const t = setInterval(load, POLL_DETALLE_MS);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, [selectedId]);

  // Auto-scroll al final cuando llegan mensajes
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [detail?.messages?.length]);

  const canReply = me?.member.permissions?.can_reply_messages === true;

  // Ya no se filtra acá: `conversations` es la página que devolvió el backend
  // con el filtro y la búsqueda ya aplicados.

  /**
   * Cambia el archivo pendiente y libera el anterior. Los object URL no los
   * recoge el recolector de basura solo: sin el `revoke`, una jornada eligiendo
   * fotos deja el blob de cada una en memoria hasta que se recargue la página.
   */
  const ponerAdjunto = useCallback((nuevo: AdjuntoLocal | null) => {
    const previo = adjuntoRef.current;
    if (previo && previo.url !== nuevo?.url) URL.revokeObjectURL(previo.url);
    adjuntoRef.current = nuevo;
    setAdjunto(nuevo);
  }, []);

  // Cambiar de chat suelta el archivo pendiente. Es a propósito: un adjunto que
  // sobrevive al cambio de conversación termina en el chat equivocado, y una
  // foto enviada a un cliente que no era no se puede devolver.
  useEffect(() => {
    ponerAdjunto(null);
    setErrorMsg(null);
  }, [selectedId, ponerAdjunto]);

  useEffect(() => {
    return () => {
      if (adjuntoRef.current) URL.revokeObjectURL(adjuntoRef.current.url);
    };
  }, []);

  /** Toma el archivo (del clip o del grabador), lo valida y lo deja listo. */
  const aceptarArchivo = useCallback(
    (archivo: File, titulo?: string) => {
      const revision = validarAdjunto(archivo);
      if (revision.estado !== 'ok') {
        setErrorMsg(revision.motivo);
        return;
      }
      setErrorMsg(null);
      ponerAdjunto({
        archivo,
        clase: revision.clase,
        url: URL.createObjectURL(archivo),
        titulo: titulo || archivo.name,
      });
    },
    [ponerAdjunto],
  );

  const alElegirArchivo = (e: React.ChangeEvent<HTMLInputElement>) => {
    const archivo = e.target.files?.[0];
    e.target.value = ''; // para poder volver a elegir el mismo archivo
    if (archivo) aceptarArchivo(archivo);
  };

  /**
   * Inserta el emoji donde está el cursor, no al final: si la asesora escribió
   * "Listo, te confirmo" y se devolvió a poner una carita después de "Listo",
   * pegarla al final sería ignorar lo que pidió.
   */
  const insertarEmoji = (emoji: string) => {
    const el = textareaRef.current;
    const inicio = el?.selectionStart ?? draft.length;
    const fin = el?.selectionEnd ?? draft.length;
    const nuevo = draft.slice(0, inicio) + emoji + draft.slice(fin);
    // Con un adjunto en curso el texto es el pie, y el pie tiene tope.
    if (adjunto && nuevo.length > MAX_CAPTION) return;
    setDraft(nuevo);
    // Después del re-render: si se mueve el cursor antes, React lo pisa al
    // repintar el textarea con el valor nuevo.
    requestAnimationFrame(() => {
      const destino = textareaRef.current;
      if (!destino) return;
      destino.focus();
      const pos = inicio + emoji.length;
      destino.setSelectionRange(pos, pos);
    });
  };

  /**
   * Lo que graba el micrófono llega sin nombre útil
   * (`nota-de-voz-1755812345.webm`), así que se muestra con un título humano.
   */
  const alGrabarNota = useCallback(
    (archivo: File) => {
      const esGrabacion = archivo.name.startsWith('nota-de-voz-');
      aceptarArchivo(archivo, esGrabacion ? 'Nota de voz' : archivo.name);
    },
    [aceptarArchivo],
  );

  const recargarDetalle = async (conversationId: number) => {
    const res = await fetch(`/api/mensajes/conversaciones/${conversationId}`, {
      headers: authHeaders(),
    });
    if (res.ok) setDetail(await res.json());
  };

  /**
   * Sube el archivo y lo manda por WhatsApp. El cómo vive en `subirAdjunto`
   * (`lib/adjuntos.ts`): en producción son tres viajes y el archivo va directo
   * a S3, esquivando los dos saltos que le ponían techo (~4,4 MB de Amplify y
   * 10 MB del API Gateway).
   *
   * `authHeaders()` solo agrega `Authorization`, que es justo lo que hace falta
   * (regla #7: el token sale de `lib/session.ts`, nunca de `localStorage`).
   */
  const enviarAdjunto = async () => {
    if (!detail || !adjunto || !canReply || sending) return;
    // El caption no aplica a las notas de voz (contrato de API): se manda solo
    // el audio y el texto se queda escrito para el mensaje siguiente.
    const caption = adjunto.clase === 'audio' ? '' : draft.trim().slice(0, MAX_CAPTION);
    setSending(true);
    setErrorMsg(null);
    try {
      await subirAdjunto(detail.id, adjunto.archivo, caption, authHeaders());
      ponerAdjunto(null);
      if (caption) setDraft('');
      await recargarDetalle(detail.id);
    } catch (e: any) {
      // El archivo NO se suelta cuando falla: casi siempre el reintento es el
      // mismo archivo, y volver a buscarlo en el disco es trabajo perdido.
      setErrorMsg(e?.message || 'Error temporal al enviar el archivo. Inténtalo de nuevo.');
    } finally {
      setSending(false);
    }
  };

  /** El botón "Enviar" es uno solo: manda el archivo si hay, si no el texto. */
  const enviar = () => {
    if (adjunto) {
      void enviarAdjunto();
    } else {
      void sendMessage();
    }
  };

  const sendMessage = async () => {
    if (!detail || !draft.trim() || !canReply) return;
    setSending(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`/api/mensajes/conversaciones/${detail.id}/enviar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ content: draft.trim() }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Error ${res.status}`);
      }
      setDraft('');
      await recargarDetalle(detail.id);
    } catch (e: any) {
      setErrorMsg(e.message || 'Error enviando mensaje');
    } finally {
      setSending(false);
    }
  };

  const startNewConversation = async () => {
    if (!newPhone || !newTemplate) return;
    setSending(true);
    setErrorMsg(null);
    try {
      const res = await fetch('/api/mensajes/conversaciones/nueva', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          contact_wa_id: newPhone.replace(/\D/g, ''),
          contact_name: newName || null,
          template_name: newTemplate,
          language_code: newLang,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Error ${res.status}`);
      }
      setShowNew(false);
      setNewPhone('');
      setNewName('');
      // La conversación recién creada es la más reciente, así que está en la
      // primera página. Se vuelve a ella y se limpian los filtros: si quedara
      // puesto "Cerrado", el chat que se acaba de abrir no aparecería y daría
      // la impresión de que no se creó.
      setFilter('todas');
      setSearch('');
      setPagina(1);
      const r2 = await fetch('/api/mensajes/conversaciones?limite=20&pagina=1', {
        headers: authHeaders(),
      });
      if (r2.ok) {
        const page: ConversationPage = await r2.json();
        const list = page.conversaciones || [];
        setConversations(list);
        setTotal(page.total || 0);
        const found = list.find((c) => c.contact_wa_id === newPhone.replace(/\D/g, ''));
        if (found) setSelectedId(found.id);
      }
    } catch (e: any) {
      setErrorMsg(e.message || 'Error iniciando conversación');
    } finally {
      setSending(false);
    }
  };

  return (
    <Layout variant="app">
      {/* Header del módulo */}
      <header className="bg-white border-b border-gloma-rose-soft px-8 py-4 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <span className="text-2xl">💬</span>
          <h1 className="text-xl font-semibold text-gray-800">Bandeja de entrada</h1>
        </div>
        <div data-tour="user-badge" className="flex items-center gap-4">
          {me && (
            <div className="text-right">
              <div className="text-xs text-gray-500">Conectado como</div>
              <div className="text-sm font-medium text-gloma-brown">{me.member.nombre || me.member.correo}</div>
            </div>
          )}
          <div className="w-10 h-10 rounded-full bg-gloma-brown text-white flex items-center justify-center font-semibold">
            {initials(me?.member.nombre || null, me?.member.correo || 'U')}
          </div>
        </div>
      </header>

      {/* Body: lista + panel */}
      <div className="flex-1 flex overflow-hidden">
        {/* Lista de conversaciones */}
        <aside data-tour="conv-list" className="w-96 bg-white border-r border-gloma-rose-soft flex flex-col">
          <div className="px-4 py-3 border-b border-gloma-rose-soft">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold text-gray-800">Chats activos</h2>
              <button
                onClick={() => setShowNew(true)}
                className="w-8 h-8 rounded-full bg-gloma-brown text-white flex items-center justify-center hover:bg-gloma-brown-dark transition-colors"
                title="Nueva conversación"
              >
                +
              </button>
            </div>
            <div className="text-xs text-gray-500 mb-2">
              {conversations.length} {conversations.length === 1 ? 'charla' : 'charlas'}
            </div>
            <input
              type="text"
              placeholder="Buscar..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-gloma-rose"
            />
            <div data-tour="conv-filters" className="flex gap-2 mt-3 flex-wrap">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                    filter === f.key
                      ? 'bg-gloma-brown text-white border-gloma-brown'
                      : 'text-gray-600 border-gray-200 hover:border-gloma-rose'
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {meError && (
              <div className="p-4 text-sm text-red-600">Error cargando equipo: {meError}</div>
            )}
            {conversations.length === 0 ? (
              <div className="p-8 text-center text-gray-400 text-sm">
                {/* Con el filtro puesto, "sin conversaciones todavía" sería
                    mentira: las hay, solo que no de este tipo. */}
                {filter !== 'todas' || searchAplicado
                  ? 'No hay resultados con el filtro actual.'
                  : 'Sin conversaciones todavía. Inicia una con el botón + arriba.'}
              </div>
            ) : (
              conversations.map((c) => {
                const selected = c.id === selectedId;
                return (
                  <button
                    key={c.id}
                    onClick={() => setSelectedId(c.id)}
                    className={`w-full text-left px-4 py-3 flex gap-3 border-b border-gray-50 transition-colors ${
                      selected ? 'bg-gloma-rose-soft/30' : 'hover:bg-gray-50'
                    }`}
                  >
                    <div className="w-10 h-10 rounded-full bg-gloma-rose-soft text-gloma-brown flex items-center justify-center font-semibold flex-shrink-0">
                      {initials(c.contact_name, c.contact_wa_id)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-sm text-gray-800 truncate">
                          {c.contact_name || `+${c.contact_wa_id}`}
                        </span>
                        <span className="text-xs text-gray-400 ml-2 flex-shrink-0">
                          {formatTime(c.last_message_at)}
                        </span>
                      </div>
                      {/* El número debajo del nombre: el asesor lo necesita para
                          buscar a la persona en su celular, y sin esto había que
                          abrir el chat para verlo. Si no sabemos el nombre, el
                          número ya está arriba y repetirlo sobra. */}
                      {c.contact_name && (
                        <div className="text-[11px] text-gray-400 truncate">
                          +{c.contact_wa_id}
                        </div>
                      )}
                      {/* El adelanto va con el mismo formato que la burbuja: si
                          el recorte parte una negrilla, el asterisco suelto se
                          queda escrito (igual que antes), no se come nada. */}
                      <div className="text-xs text-gray-500 truncate">
                        {c.last_message_preview
                          ? formatearWhatsapp(c.last_message_preview)
                          : '(sin mensajes)'}
                      </div>
                      <span
                        className={`inline-block mt-1 px-2 py-0.5 text-[10px] rounded-full ${
                          c.status === 'open'
                            ? 'bg-gloma-rose-soft text-gloma-brown'
                            : c.status === 'pending'
                            ? 'bg-yellow-100 text-yellow-700'
                            : 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        {c.status}
                      </span>
                      {c.assigned_to && c.assigned_to !== 'bot' ? (
                        <span className="inline-block mt-1 ml-1 px-2 py-0.5 text-[10px] rounded-full bg-emerald-50 text-emerald-700">
                          👤 {c.assigned_to}
                        </span>
                      ) : (
                        <span className="inline-block mt-1 ml-1 px-2 py-0.5 text-[10px] rounded-full bg-gray-100 text-gray-500">
                          🤖 bot
                        </span>
                      )}
                      {/* Etiqueta que puso el bot (hoy: "conversación
                          abandonada"). Sin valor no se pinta nada: una fila con
                          un chip vacío se lee como un dato que falta. Va en
                          ámbar, el mismo tono que la nota interna, porque las
                          dos dicen "esto lo escribió el sistema, míralo". */}
                      {c.etiqueta && (
                        <span
                          title={`Etiqueta: ${c.etiqueta}`}
                          className="inline-block mt-1 ml-1 px-2 py-0.5 text-[10px] rounded-full bg-amber-50 text-amber-700 border border-amber-200"
                        >
                          🏷️ {c.etiqueta}
                        </span>
                      )}
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {/* Paginación al pie de la lista: fuera del área que scrollea, para
              que no haya que bajar hasta el final para cambiar de página. */}
          <div className="px-4 border-t border-gloma-rose-soft">
            <Paginacion
              pagina={pagina}
              porPagina={porPagina}
              total={total}
              onPagina={setPagina}
              onPorPagina={(n) => {
                setPorPagina(n);
                guardarPorPagina('mensajes.porPagina', n);
              }}
              etiqueta="chats"
            />
          </div>
        </aside>

        {/* Panel de chat */}
        <section className="flex-1 flex flex-col bg-gloma-rose-soft/30">
          {detail ? (
            <>
              <div className="bg-white border-b border-gloma-rose-soft px-6 py-3 flex items-center gap-3 shadow-sm">
                <div className="w-10 h-10 rounded-full bg-gloma-rose-soft text-gloma-brown flex items-center justify-center font-semibold">
                  {initials(detail.contact_name, detail.contact_wa_id)}
                </div>
                <div>
                  <div className="font-semibold text-gray-800">
                    {detail.contact_name || `+${detail.contact_wa_id}`}
                  </div>
                  {/* Sin nombre, el número ya está arriba: mostrarlo dos veces
                      seguidas se veía como un error de la pantalla. */}
                  {detail.contact_name && (
                    <div className="text-xs text-gray-500">+{detail.contact_wa_id}</div>
                  )}
                </div>
                <div className="ml-auto text-xs">
                  {detail.assigned_to && detail.assigned_to !== 'bot' ? (
                    <span className="px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 font-medium">
                      Atiende: 👤 {detail.assigned_to}
                    </span>
                  ) : (
                    <span className="px-2.5 py-1 rounded-full bg-gray-100 text-gray-500 font-medium">
                      Atiende: 🤖 bot
                    </span>
                  )}
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-6 space-y-3">
                {detail.messages.length === 0 ? (
                  <div className="text-center text-gray-400 text-sm mt-12">
                    Sin mensajes en esta conversación.
                  </div>
                ) : (
                  detail.messages.map((m) =>
                    /* La nota interna la escribe el bot al pasar el chat a un
                       asesor. NO se le envió al cliente: se muestra centrada y
                       con aviso, para que nadie la confunda con un mensaje del
                       chat y le responda "como ya le dije...". */
                    m.message_type === 'nota_interna' ? (
                      <div key={m.id} className="flex justify-center">
                        <div className="max-w-lg w-full px-4 py-2.5 rounded-xl border border-amber-200 bg-amber-50">
                          <div className="text-sm whitespace-pre-wrap break-words text-amber-900">
                            {formatearWhatsapp(m.content)}
                          </div>
                          <div className="text-[10px] mt-1 text-amber-600">
                            {formatTime(m.created_at)} • solo visible para el equipo
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div
                        key={m.id}
                        className={`flex ${m.direction === 'outbound' ? 'justify-end' : 'justify-start'}`}
                      >
                        <div
                          className={`max-w-md px-4 py-2 rounded-2xl shadow-sm ${
                            m.direction === 'outbound'
                              ? 'bg-gloma-brown text-white rounded-br-sm'
                              : 'bg-white text-gray-800 rounded-bl-sm border border-gray-100'
                          }`}
                        >
                          <Contenido mensaje={m} />
                          <div
                            className={`text-[10px] mt-1 ${
                              m.direction === 'outbound' ? 'text-gloma-rose-soft' : 'text-gray-400'
                            }`}
                          >
                            {formatTime(m.created_at)}
                            {m.status === 'failed' && ' • falló'}
                          </div>
                        </div>
                      </div>
                    )
                  )
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Composer */}
              <div data-tour="reply-composer" className="bg-white border-t border-gloma-rose-soft p-4">
                {errorMsg && (
                  <div className="mb-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
                    {errorMsg}
                  </div>
                )}
                {canReply ? (
                  <>
                    {adjunto && (
                      <VistaPreviaAdjunto
                        adjunto={adjunto}
                        subiendo={sending}
                        onQuitar={() => ponerAdjunto(null)}
                      />
                    )}
                    <input
                      ref={fileRef}
                      type="file"
                      accept={ACCEPT_ADJUNTO}
                      onChange={alElegirArchivo}
                      className="hidden"
                    />
                    <div className="flex gap-2 items-end">
                      {/* Mientras se graba, la barra del grabador se queda con
                          toda la fila: no hay nada que escribir ni que enviar
                          hasta decidir si la nota sirve. */}
                      {!grabando && (
                        <button
                          type="button"
                          onClick={() => fileRef.current?.click()}
                          disabled={sending}
                          title="Adjuntar imagen, video o documento"
                          aria-label="Adjuntar imagen, video o documento"
                          className="w-10 h-10 flex-shrink-0 self-end rounded-lg border border-gray-200 text-lg leading-none flex items-center justify-center text-gloma-brown hover:bg-gloma-rose-soft hover:border-gloma-rose transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          📎
                        </button>
                      )}
                      <GrabadorVoz
                        deshabilitado={sending}
                        onGrabado={alGrabarNota}
                        onError={setErrorMsg}
                        onEstadoChange={setGrabando}
                      />
                      {!grabando && (
                        <>
                          {/* Con una nota de voz lista no hay texto que
                              acompañar, así que tampoco emoji que insertar. */}
                          <SelectorEmoji
                            onElegir={insertarEmoji}
                            deshabilitado={sending || adjunto?.clase === 'audio'}
                          />
                          <textarea
                            ref={textareaRef}
                            rows={2}
                            value={draft}
                            onChange={(e) => setDraft(e.target.value)}
                            disabled={adjunto?.clase === 'audio'}
                            maxLength={adjunto ? MAX_CAPTION : undefined}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                enviar();
                              }
                            }}
                            placeholder={
                              adjunto?.clase === 'audio'
                                ? 'La nota de voz se envía sola; tu texto queda aquí para después.'
                                : adjunto
                                ? 'Comentario para acompañar el archivo (opcional)...'
                                : 'Escribe un mensaje (Enter para enviar)...'
                            }
                            className="flex-1 px-3 py-2 border border-gray-200 rounded-lg resize-none focus:outline-none focus:border-gloma-rose text-sm disabled:bg-gray-50 disabled:text-gray-400"
                          />
                          <button
                            onClick={enviar}
                            disabled={sending || (!adjunto && !draft.trim())}
                            className="px-5 h-[42px] self-end bg-gloma-brown text-white font-medium rounded-lg hover:bg-gloma-brown-dark disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {sending ? (adjunto ? 'Enviando…' : '...') : 'Enviar'}
                          </button>
                        </>
                      )}
                    </div>
                    {/* El tope del caption es del backend (900). Se avisa cerca
                        del límite, no desde el primer carácter. */}
                    {adjunto && adjunto.clase !== 'audio' && draft.length > MAX_CAPTION - 100 && (
                      <div className="mt-1 text-right text-[11px] text-gray-500">
                        {draft.length}/{MAX_CAPTION} caracteres
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-center text-sm text-gray-500 py-3">
                    No tienes permiso para responder mensajes en este equipo.
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="text-6xl mb-4">💬</div>
                <div className="text-lg font-semibold text-gray-700">Ninguna conversación seleccionada</div>
                <div className="text-sm text-gray-500 mt-2">Selecciona un chat de la lista o inicia uno nuevo</div>
              </div>
            </div>
          )}
        </section>
      </div>

      {/* Modal nueva conversación */}
      {showNew && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-1">Nueva conversación</h3>
            <p className="text-xs text-gray-500 mb-4">
              Para iniciar conversación con un contacto nuevo, Meta exige enviar un template aprobado.
            </p>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-500">Número (con código país, sin +)</label>
                <input
                  type="text"
                  value={newPhone}
                  onChange={(e) => setNewPhone(e.target.value)}
                  placeholder="573150764000"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-gloma-rose"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500">Nombre (opcional)</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-gloma-rose"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500">Nombre del template</label>
                <input
                  type="text"
                  value={newTemplate}
                  onChange={(e) => setNewTemplate(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-gloma-rose"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500">Idioma</label>
                <input
                  type="text"
                  value={newLang}
                  onChange={(e) => setNewLang(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-gloma-rose"
                />
              </div>
            </div>
            {errorMsg && (
              <div className="mt-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
                {errorMsg}
              </div>
            )}
            <div className="flex gap-2 mt-5">
              <button
                onClick={() => {
                  setShowNew(false);
                  setErrorMsg(null);
                }}
                className="flex-1 px-4 py-2 border border-gray-200 rounded-lg text-gray-700 hover:bg-gray-50"
              >
                Cancelar
              </button>
              <button
                onClick={startNewConversation}
                disabled={sending || !newPhone || !newTemplate}
                className="flex-1 px-4 py-2 bg-gloma-brown text-white rounded-lg hover:bg-gloma-brown-dark disabled:opacity-50"
              >
                {sending ? 'Enviando...' : 'Enviar template'}
              </button>
            </div>
          </div>
        </div>
      )}

      {me && <TutorialOverlay moduleKey="mensajes" steps={MENSAJES_TUTORIAL} />}
    </Layout>
  );
}
