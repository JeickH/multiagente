/**
 * Adjuntos salientes de la bandeja: qué se puede mandar, y qué decir cuando no.
 *
 * La tabla de MIME y tamaños es la MISMA que valida
 * `POST /mensajes/conversaciones/{id}/adjunto`. Está repetida acá a propósito,
 * y el backend sigue mandando: él mira los magic bytes del archivo, el
 * navegador solo cree lo que dice el sistema operativo. Lo que gana esta copia
 * es tiempo de la asesora — rebotar un video de 40 MB antes de subirlo le
 * ahorra la barra de progreso completa para terminar en un 400. Si la lista del
 * backend cambia, esta se actualiza detrás.
 *
 * Los límites salen de lo que acepta WhatsApp (Meta): 5 MB imagen, 16 MB el
 * resto. El video va en 12 MB, que es lo que se le promete al asesor.
 *
 * Estos números son los únicos que quedan: el archivo ya no sube por nuestra
 * API sino directo a S3 (`subirAdjunto`), justamente porque el camino viejo
 * tenía dos techos invisibles que ningún número de acá podía levantar —el
 * compute de Amplify (~4,4 MB) y el API Gateway (10 MB duros de AWS)—.
 */

export type ClaseAdjunto = 'image' | 'audio' | 'video' | 'document';

/** Tope de caracteres del caption (mismo del contrato de API). */
export const MAX_CAPTION = 900;

const MB = 1024 * 1024;

type Regla = {
  clase: ClaseAdjunto;
  /** Cómo se llama en la interfaz, en singular y en español. */
  etiqueta: string;
  mimes: string[];
  /** Extensiones de respaldo: hay sistemas que entregan `file.type` vacío. */
  extensiones: string[];
  maxBytes: number;
};

const REGLAS: Regla[] = [
  {
    clase: 'image',
    etiqueta: 'Imagen',
    mimes: ['image/jpeg', 'image/png', 'image/webp'],
    extensiones: ['jpg', 'jpeg', 'png', 'webp'],
    maxBytes: 5 * MB,
  },
  {
    clase: 'audio',
    etiqueta: 'Audio',
    mimes: ['audio/ogg', 'audio/mpeg', 'audio/mp4', 'audio/aac', 'audio/amr', 'audio/webm'],
    extensiones: ['ogg', 'oga', 'opus', 'mp3', 'm4a', 'aac', 'amr', 'weba', 'webm'],
    maxBytes: 16 * MB,
  },
  {
    clase: 'video',
    etiqueta: 'Video',
    mimes: ['video/mp4', 'video/3gpp'],
    extensiones: ['mp4', '3gp', '3gpp'],
    maxBytes: 12 * MB,
  },
  {
    clase: 'document',
    etiqueta: 'Documento',
    mimes: [
      'application/pdf',
      'application/msword',
      'application/vnd.ms-excel',
      'application/vnd.ms-powerpoint',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      'text/plain',
      'text/csv',
    ],
    extensiones: ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv'],
    maxBytes: 16 * MB,
  },
];

/** Los MIME de documento, para no repetirlos en la lista del selector. */
const MIMES_DOCUMENTO = REGLAS.find((r) => r.clase === 'document')!.mimes;

/**
 * Lo que se le ofrece al selector de archivos. Van MIME y extensiones juntos:
 * macOS filtra bien por MIME, Windows a veces solo entiende la extensión.
 *
 * `.webm` NO está en la lista aunque el audio grabado sea webm: un `.webm` de
 * disco casi siempre es video (`video/webm`, que WhatsApp no acepta) y ofrecerlo
 * sería invitar a un rechazo. Las notas de voz que grabamos nosotros no pasan
 * por este selector.
 */
export const ACCEPT_ADJUNTO = [
  'image/jpeg',
  'image/png',
  'image/webp',
  'video/mp4',
  'video/3gpp',
  'audio/ogg',
  'audio/mpeg',
  'audio/mp4',
  'audio/aac',
  'audio/amr',
  ...MIMES_DOCUMENTO,
  '.jpg',
  '.jpeg',
  '.png',
  '.webp',
  '.mp4',
  '.3gp',
  '.ogg',
  '.oga',
  '.mp3',
  '.m4a',
  '.aac',
  '.amr',
  '.pdf',
  '.doc',
  '.docx',
  '.xls',
  '.xlsx',
  '.ppt',
  '.pptx',
  '.txt',
  '.csv',
].join(',');

/** Lo mismo, recortado a audio: es el plan B cuando no se puede grabar. */
export const ACCEPT_AUDIO = [
  'audio/ogg',
  'audio/mpeg',
  'audio/mp4',
  'audio/aac',
  'audio/amr',
  '.ogg',
  '.oga',
  '.mp3',
  '.m4a',
  '.aac',
  '.amr',
].join(',');

/**
 * Deja el MIME en su forma canónica: sin parámetros (`;codecs=opus`), en
 * minúscula, y con los alias que reportan algunos navegadores traducidos al
 * nombre oficial. Sin esto, un MP3 grabado en Windows (`audio/mp3`, que no
 * existe en el registro de IANA) se rechazaría sin razón.
 */
export function normalizarMime(tipo: string | null | undefined): string {
  const base = (tipo || '').split(';')[0].trim().toLowerCase();
  const alias: Record<string, string> = {
    'image/jpg': 'image/jpeg',
    'image/pjpeg': 'image/jpeg',
    'audio/mp3': 'audio/mpeg',
    'audio/mpeg3': 'audio/mpeg',
    'audio/x-mpeg': 'audio/mpeg',
    'audio/m4a': 'audio/mp4',
    'audio/x-m4a': 'audio/mp4',
    'audio/aacp': 'audio/aac',
    'audio/x-aac': 'audio/aac',
    'audio/opus': 'audio/ogg',
    'audio/3gpp': 'audio/amr',
    'video/3gp': 'video/3gpp',
  };
  return alias[base] || base;
}

function extensionDe(nombre: string): string {
  const punto = nombre.lastIndexOf('.');
  return punto === -1 ? '' : nombre.slice(punto + 1).toLowerCase();
}

/** La regla que le corresponde al archivo, o `null` si no es de los nuestros. */
function reglaDe(archivo: File): Regla | null {
  const mime = normalizarMime(archivo.type);
  if (mime) {
    const porMime = REGLAS.find((r) => r.mimes.includes(mime));
    if (porMime) return porMime;
  }
  // `file.type` vacío pasa con archivos venidos de un ZIP o de un disco de red.
  if (!mime) {
    const ext = extensionDe(archivo.name);
    const porExt = REGLAS.find((r) => r.extensiones.includes(ext));
    if (porExt) return porExt;
  }
  return null;
}

/** Qué clase de adjunto es, para decidir cómo se previsualiza. */
export function claseDeArchivo(archivo: File): ClaseAdjunto | null {
  return reglaDe(archivo)?.clase ?? null;
}

/** Nombre humano de la clase: "Imagen", "Audio", … */
export function etiquetaDeClase(clase: ClaseAdjunto): string {
  return REGLAS.find((r) => r.clase === clase)?.etiqueta ?? 'Archivo';
}

/** "4,2 MB", "812 KB". Con coma decimal, como se lee en Colombia. */
export function tamanoLegible(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < MB) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / MB).toLocaleString('es-CO', { maximumFractionDigits: 1 })} MB`;
}

/**
 * El resultado se distingue por un `estado` de texto y no por un `ok: boolean`:
 * este `tsconfig` corre con `strict: false`, y sin `strictNullChecks`
 * TypeScript no sabe estrechar una unión discriminada por `true`/`false` — el
 * `motivo` quedaba invisible en la rama del rechazo.
 */
export type Validacion =
  | { estado: 'ok'; clase: ClaseAdjunto; etiqueta: string }
  | { estado: 'rechazado'; motivo: string };

/**
 * Revisión previa a la subida. El motivo se escribe para que lo lea la asesora
 * y sepa qué hacer distinto, no para describir el error técnico.
 */
export function validarAdjunto(archivo: File): Validacion {
  if (!archivo || archivo.size === 0) {
    return { estado: 'rechazado', motivo: 'Ese archivo está vacío. Elige otro.' };
  }
  const regla = reglaDe(archivo);
  if (!regla) {
    return {
      estado: 'rechazado',
      motivo:
        'WhatsApp no acepta ese tipo de archivo. Puedes enviar imágenes (JPG, PNG, WEBP), ' +
        'audio (OGG, MP3, M4A, AAC), video MP4 o documentos (PDF, Word, Excel, ' +
        'PowerPoint, TXT o CSV).',
    };
  }
  if (archivo.size > regla.maxBytes) {
    return {
      estado: 'rechazado',
      motivo:
        `${regla.etiqueta} de ${tamanoLegible(archivo.size)}: el máximo que acepta WhatsApp ` +
        `son ${tamanoLegible(regla.maxBytes)}. Envía una versión más liviana.`,
    };
  }
  return { estado: 'ok', clase: regla.clase, etiqueta: regla.etiqueta };
}

/**
 * Sube el archivo y lo manda, por el camino que diga el backend.
 *
 * Son tres viajes en vez de uno, y vale la pena: el de en medio —el archivo—
 * va **directo a S3**, sin pasar por Amplify ni por el API Gateway, que es
 * justo donde se moría un video de 10 MB. Los otros dos son JSON de unos pocos
 * bytes.
 *
 *   1. `POST …/adjunto/preparar` → o un POST prefirmado, o "sube por la API"
 *      (desarrollo local, donde no hay bucket y tampoco hay saltos en medio).
 *   2. `POST` del archivo a S3. Los `campos` van **antes** que el archivo: en
 *      un POST de S3 el binario tiene que ser el último campo del formulario o
 *      S3 responde 400.
 *   3. `POST …/adjunto/confirmar` → el backend valida los bytes de verdad y
 *      recién ahí sale por WhatsApp.
 *
 * `autorizacion` se recibe en vez de leer el token acá: la sesión se toca solo
 * por `lib/session.ts` (regla de seguridad #7). Y ojo con no mandarla nunca al
 * POST de S3 — ahí no pinta nada, y un `Authorization` de más rompe la firma.
 */
export async function subirAdjunto(
  conversationId: number,
  archivo: File,
  caption: string,
  autorizacion: HeadersInit,
): Promise<void> {
  const jsonHeaders = { ...(autorizacion as Record<string, string>), 'Content-Type': 'application/json' };

  const preparar = await fetch(`/api/mensajes/conversaciones/${conversationId}/adjunto/preparar`, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({
      filename: archivo.name,
      content_type: normalizarMime(archivo.type),
      size: archivo.size,
    }),
  });
  if (!preparar.ok) {
    const cuerpo = await preparar.json().catch(() => null);
    throw new Error(mensajeDeErrorEnvio(preparar.status, cuerpo?.detail));
  }
  const plan = await preparar.json();

  // Sin bucket: el camino de siempre, un solo POST con el archivo adentro.
  if (plan?.modo !== 's3') {
    const form = new FormData();
    form.append('archivo', archivo);
    if (caption) form.append('caption', caption);
    const res = await fetch(`/api/mensajes/conversaciones/${conversationId}/adjunto`, {
      method: 'POST',
      headers: autorizacion,
      body: form,
    });
    if (!res.ok) {
      const cuerpo = await res.json().catch(() => null);
      throw new Error(mensajeDeErrorEnvio(res.status, cuerpo?.detail));
    }
    return;
  }

  const form = new FormData();
  Object.entries(plan.campos || {}).forEach(([k, v]) => form.append(k, String(v)));
  form.append('file', archivo);

  const subida = await fetch(plan.url, { method: 'POST', body: form });
  if (!subida.ok) {
    // S3 contesta XML; no hay nada ahí que mostrarle a la asesora. El caso
    // realista es que la firma expiró (tardó más de 10 min en darle enviar).
    throw new Error(
      'No pudimos subir el archivo. Revisa tu conexión e inténtalo de nuevo.',
    );
  }

  const confirmar = await fetch(`/api/mensajes/conversaciones/${conversationId}/adjunto/confirmar`, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({
      referencia: plan.referencia,
      filename: archivo.name,
      content_type: normalizarMime(archivo.type),
      caption: caption || null,
    }),
  });
  if (!confirmar.ok) {
    const cuerpo = await confirmar.json().catch(() => null);
    throw new Error(mensajeDeErrorEnvio(confirmar.status, cuerpo?.detail));
  }
}

/**
 * Traduce la respuesta del backend a algo que se pueda leer en la pantalla.
 *
 * Cuando el backend manda `detail` lo usamos tal cual: ya viene sanitizado
 * (regla de seguridad #6, el detalle del proveedor se queda en los logs del
 * servidor). El texto de respaldo es para cuando la respuesta no trae nada
 * legible — un 502 del gateway, por ejemplo, que ni siquiera es JSON.
 */
export function mensajeDeErrorEnvio(status: number, detalle?: unknown): string {
  if (typeof detalle === 'string' && detalle.trim()) return detalle.trim();

  switch (status) {
    case 400:
      return 'El archivo no se pudo enviar: revisa que sea una imagen, un audio, un video MP4 o un documento (PDF, Word, Excel).';
    case 401:
      return 'Tu sesión venció. Vuelve a entrar para seguir respondiendo.';
    case 403:
      return 'No tienes permiso para responder mensajes en este equipo.';
    case 404:
      return 'Esa conversación ya no está disponible. Recarga la bandeja.';
    case 409:
      return 'La cuenta de WhatsApp no está activa. Revísala en Mi Plan.';
    case 413:
      return 'El archivo pesa demasiado para enviarlo por WhatsApp.';
    case 502:
      return 'WhatsApp no aceptó el archivo. Inténtalo de nuevo en un momento.';
    default:
      return 'Error temporal al enviar el archivo. Inténtalo de nuevo.';
  }
}
