/**
 * Grabador de notas de voz del composer de la bandeja.
 *
 * Entrega un `File` y nada más: la vista previa, el caption y el envío los hace
 * el composer, que es el mismo camino de cualquier otro adjunto. Así hay una
 * sola pantalla de "esto es lo que estás por mandar" y un solo manejo de error.
 *
 * Degradación (es un requisito, no un extra): si el navegador no sabe grabar o
 * la persona niega el permiso del micrófono, el botón NO desaparece ni queda
 * muerto — se convierte en "adjuntar un archivo de audio" y abre el selector.
 * El caso real es el portátil compartido donde alguien le dio "Bloquear" al
 * permiso hace meses y nadie se acuerda.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { ACCEPT_AUDIO } from '../lib/adjuntos';

/**
 * Corte automático a los 5 minutos. Una nota de voz de 5 min en Opus pesa menos
 * de 1 MB, así que el tope no es el peso: es que un micrófono abierto y olvidado
 * termina grabando la oficina.
 */
const MAX_SEGUNDOS = 300;

/**
 * Formatos en orden de preferencia. Chrome y Firefox graban webm/opus; Safari
 * solo mp4. Los tres los acepta el backend (transcodifica a ogg/opus cuando hace
 * falta, porque WhatsApp no recibe webm).
 */
const CANDIDATOS = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/webm', 'audio/mp4'];

function formatoPreferido(): string {
  if (typeof MediaRecorder === 'undefined') return '';
  for (const mime of CANDIDATOS) {
    try {
      if (MediaRecorder.isTypeSupported(mime)) return mime;
    } catch {
      /* isTypeSupported no existe en navegadores viejos */
    }
  }
  return ''; // que el navegador elija su formato por defecto
}

function extensionDe(mime: string): string {
  if (mime.startsWith('audio/ogg')) return 'ogg';
  if (mime.startsWith('audio/mp4')) return 'm4a';
  if (mime.startsWith('audio/mpeg')) return 'mp3';
  return 'webm';
}

function mmss(segundos: number): string {
  const m = Math.floor(segundos / 60);
  const s = segundos % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

type Props = {
  deshabilitado?: boolean;
  /** La nota grabada (o el archivo elegido en el plan B). */
  onGrabado: (archivo: File) => void;
  /** Mensaje para la franja de error del composer. `null` la limpia. */
  onError: (mensaje: string | null) => void;
  /** El composer esconde el textarea mientras se graba. */
  onEstadoChange?: (grabando: boolean) => void;
};

export default function GrabadorVoz({
  deshabilitado = false,
  onGrabado,
  onError,
  onEstadoChange,
}: Props) {
  const [modo, setModo] = useState<'inactivo' | 'grabando' | 'sin-micro'>('inactivo');
  const [segundos, setSegundos] = useState(0);

  const recRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const trozosRef = useRef<Blob[]>([]);
  const descartarRef = useRef(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  /** Apagar el micrófono: sin esto el navegador deja el punto rojo encendido. */
  const soltarMicrofono = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const detener = useCallback(
    (conservar: boolean) => {
      descartarRef.current = !conservar;
      const rec = recRef.current;
      if (rec && rec.state !== 'inactive') {
        rec.stop(); // el resto ocurre en `onstop`
      } else {
        soltarMicrofono();
        setModo('inactivo');
        setSegundos(0);
      }
    },
    [soltarMicrofono],
  );

  const comenzar = useCallback(async () => {
    onError(null);
    const puede =
      typeof window !== 'undefined' &&
      typeof MediaRecorder !== 'undefined' &&
      !!navigator.mediaDevices?.getUserMedia;
    if (!puede) {
      setModo('sin-micro');
      onError(
        'Este navegador no permite grabar audio. Adjunta un archivo de audio con el mismo botón.',
      );
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const preferido = formatoPreferido();
      const rec = preferido
        ? new MediaRecorder(stream, { mimeType: preferido })
        : new MediaRecorder(stream);

      trozosRef.current = [];
      descartarRef.current = false;

      rec.ondataavailable = (e: BlobEvent) => {
        if (e.data && e.data.size > 0) trozosRef.current.push(e.data);
      };

      rec.onstop = () => {
        soltarMicrofono();
        const trozos = trozosRef.current;
        trozosRef.current = [];
        setModo('inactivo');
        setSegundos(0);
        if (descartarRef.current) return;

        // El tipo se manda sin parámetros (`audio/webm`, no
        // `audio/webm;codecs=opus`): es el mismo contenido, y la lista blanca
        // del backend compara contra el MIME base.
        const crudo = rec.mimeType || preferido || 'audio/webm';
        const tipo = crudo.split(';')[0].trim().toLowerCase();
        const blob = new Blob(trozos, { type: tipo });
        if (blob.size === 0) {
          onError('No se grabó nada. Revisa que el micrófono esté conectado y vuelve a intentar.');
          return;
        }
        const archivo = new File([blob], `nota-de-voz-${Date.now()}.${extensionDe(tipo)}`, {
          type: tipo,
        });
        onGrabado(archivo);
      };

      rec.start();
      recRef.current = rec;
      setSegundos(0);
      setModo('grabando');
    } catch (e: any) {
      soltarMicrofono();
      setModo('sin-micro');
      const negado = e?.name === 'NotAllowedError' || e?.name === 'SecurityError';
      const sinMicro = e?.name === 'NotFoundError' || e?.name === 'DevicesNotFoundError';
      onError(
        negado
          ? 'No hay permiso para usar el micrófono. Actívalo en el candado de la barra de direcciones, o adjunta un archivo de audio con este mismo botón.'
          : sinMicro
          ? 'No encontramos un micrófono conectado. Puedes adjuntar un archivo de audio con este mismo botón.'
          : 'No pudimos abrir el micrófono. Puedes adjuntar un archivo de audio con este mismo botón.',
      );
    }
  }, [onError, onGrabado, soltarMicrofono]);

  // Contador de duración.
  useEffect(() => {
    if (modo !== 'grabando') return;
    const t = setInterval(() => setSegundos((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [modo]);

  // Corte automático.
  useEffect(() => {
    if (modo === 'grabando' && segundos >= MAX_SEGUNDOS) detener(true);
  }, [modo, segundos, detener]);

  useEffect(() => {
    onEstadoChange?.(modo === 'grabando');
  }, [modo, onEstadoChange]);

  // Si la pantalla se desmonta grabando (cambio de ruta, logout), el micrófono
  // se apaga y lo grabado se descarta: nadie pidió mandarlo.
  useEffect(() => {
    return () => {
      descartarRef.current = true;
      const rec = recRef.current;
      if (rec && rec.state !== 'inactive') {
        try {
          rec.stop();
        } catch {
          /* no-op */
        }
      }
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const elegirArchivoAudio = () => inputRef.current?.click();

  const alElegirArchivo = (e: React.ChangeEvent<HTMLInputElement>) => {
    const archivo = e.target.files?.[0];
    e.target.value = ''; // permite volver a elegir el mismo archivo
    if (archivo) {
      onError(null);
      onGrabado(archivo);
    }
  };

  if (modo === 'grabando') {
    return (
      <div className="flex-1 flex items-center gap-3 px-3 py-2 rounded-lg border border-gloma-rose bg-gloma-rose-soft/50">
        <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse flex-shrink-0" />
        <span
          className="text-sm font-semibold text-gloma-brown tabular-nums"
          aria-live="polite"
          aria-label={`Grabando, ${mmss(segundos)}`}
        >
          {mmss(segundos)}
        </span>
        <span className="text-xs text-gray-500 hidden md:inline">
          Grabando nota de voz… (máx. {mmss(MAX_SEGUNDOS)})
        </span>
        <div className="ml-auto flex gap-2">
          <button
            type="button"
            onClick={() => detener(false)}
            className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => detener(true)}
            className="px-4 py-1.5 text-sm rounded-lg bg-gloma-brown text-white font-medium hover:bg-gloma-brown-dark"
          >
            Listo
          </button>
        </div>
      </div>
    );
  }

  const sinMicro = modo === 'sin-micro';
  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT_AUDIO}
        onChange={alElegirArchivo}
        className="hidden"
      />
      <button
        type="button"
        onClick={sinMicro ? elegirArchivoAudio : comenzar}
        disabled={deshabilitado}
        title={sinMicro ? 'Adjuntar un archivo de audio' : 'Grabar una nota de voz'}
        aria-label={sinMicro ? 'Adjuntar un archivo de audio' : 'Grabar una nota de voz'}
        className="w-10 h-10 flex-shrink-0 self-end rounded-lg border border-gray-200 text-lg leading-none flex items-center justify-center text-gloma-brown hover:bg-gloma-rose-soft hover:border-gloma-rose transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {sinMicro ? '🎵' : '🎤'}
      </button>
    </>
  );
}
