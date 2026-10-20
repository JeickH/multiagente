import { TIPOS_EMPRESA } from './demo_copy';
import {
  DemoApiError,
  almacen,
  type ChatOut,
  type DatosIniciar,
  type EstadoDemo,
  type IniciarOut,
  type ProductoDemo,
} from './demoApi';

/**
 * Simulador de la API de la demo (`NEXT_PUBLIC_DEMO_MOCK=1`), para probar
 * `/demo` completa sin backend. Solo datos ficticios. Lo carga `demoApi.ts`
 * con `import()` únicamente en modo simulado.
 *
 * Imita el contrato mientras el backend (#613) no existe. Solo datos
 * ficticios. Para probar los estados, escribe en el nombre de la empresa:
 *   «tope»  → 429 al iniciar           «sinred» → falla de red al iniciar
 *   «lento» → lista a los 30 s (aviso de demora a los 20 s)
 *   «falla» → estado=error a los 9 s   «nunca» → generando para siempre (corte de 90 s)
 * En el chat: «asesor», «reservar» o «pagar» → handoff (sin texto de
 * contacto, como el backend); «fallar» → falla de red; «404» → demo no
 * disponible; «tope» o el turno 15 → finished=true (tope de turnos).
 * Eventos (`registrarEvento`): se cuentan en `gloma_demo_mock[id].eventos`.
 * Como el backend real, el historial y el contador viven del lado del
 * «servidor» (aquí, el registro simulado) y `session` llega siempre null.
 */
export const mock = (() => {
  const CLAVE_MOCK = 'gloma_demo_mock';
  type Registro = {
    token: string;
    empresa: string;
    tipo: string;
    creadoMs: number;
    listoEnMs: number | null;
    falla: boolean;
    turnos: number;
  };

  const esperar = (ms: number) => new Promise((r) => setTimeout(r, ms));

  function leer(): Record<string, Registro> {
    try {
      return JSON.parse(almacen()?.getItem(CLAVE_MOCK) || '{}');
    } catch {
      return {};
    }
  }
  function escribir(todo: Record<string, Registro>) {
    try {
      almacen()?.setItem(CLAVE_MOCK, JSON.stringify(todo));
    } catch {
      /* no-op */
    }
  }
  function registro(id: string, token: string): Registro {
    const r = leer()[id];
    if (!r || r.token !== token) throw new DemoApiError(404);
    return r;
  }

  function productos(tipo: string): ProductoDemo[] {
    if (tipo === 'hotel' || tipo === 'hostal' || tipo === 'glamping_finca' || tipo === 'apartamentos') {
      return [
        { nombre: 'Habitación Doble Vista al Valle', resumen: 'Cama doble, desayuno incluido y balcón. $280.000 la noche.' },
        { nombre: 'Suite Familiar Los Guaduales', resumen: 'Dos habitaciones, cocineta y zona de hamacas. $460.000 la noche.' },
        { nombre: 'Plan Escapada 2 noches', resumen: 'Dos noches, cena de bienvenida y caminata guiada. $690.000 por pareja.' },
      ];
    }
    if (tipo === 'restaurante') {
      return [
        { nombre: 'Menú Degustación de la Casa', resumen: 'Seis tiempos con productos de la región. $185.000 por persona.' },
        { nombre: 'Almuerzo Ejecutivo', resumen: 'Entrada, plato fuerte, bebida y postre. $42.000.' },
        { nombre: 'Cena Romántica en Terraza', resumen: 'Mesa privada, tres tiempos y copa de vino. $260.000 por pareja.' },
      ];
    }
    return [
      { nombre: 'Plan Isla Coral 4 días / 3 noches', resumen: 'Vuelos, hotel con desayuno y tour en lancha. Desde $1.750.000 por persona.' },
      { nombre: 'Escapada Ciudad Amurallada 3 días / 2 noches', resumen: 'Hotel en el centro histórico y recorrido a pie. Desde $1.090.000 por persona.' },
      { nombre: 'Pasadía Bahía Escondida', resumen: 'Transporte, almuerzo típico y playa. $295.000 por persona.' },
    ];
  }

  async function iniciar(datos: DatosIniciar): Promise<IniciarOut> {
    await esperar(900);
    const e = datos.empresa.toLowerCase();
    if (e.includes('tope')) throw new DemoApiError(429);
    if (e.includes('sinred')) throw new DemoApiError(0);
    if (!TIPOS_EMPRESA.some((t) => t.clave === datos.tipo_empresa)) throw new DemoApiError(422, ['tipo_empresa']);
    // Como `normalizar_telefono` del backend: E.164, 8 a 15 dígitos (#634).
    if (!/^\+[1-9]\d{7,14}$/.test(datos.telefono)) throw new DemoApiError(422, ['telefono']);
    const id = `mock-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    const token = `mock-${Math.random().toString(36).slice(2)}`;
    const todo = leer();
    todo[id] = {
      token,
      empresa: datos.empresa.trim(),
      tipo: datos.tipo_empresa,
      creadoMs: Date.now(),
      listoEnMs: e.includes('nunca') ? null : e.includes('lento') ? 30000 : e.includes('falla') ? 9000 : 6000,
      falla: e.includes('falla'),
      turnos: 0,
    };
    escribir(todo);
    return { demo_id: id, token };
  }

  async function estado(id: string, token: string): Promise<EstadoDemo> {
    await esperar(150);
    const r = registro(id, token);
    const listo = r.listoEnMs !== null && Date.now() - r.creadoMs >= r.listoEnMs;
    if (!listo) return { estado: 'generando', empresa: r.empresa, productos: [], mensaje_sugerido: null };
    if (r.falla) return { estado: 'error', empresa: r.empresa, productos: [], mensaje_sugerido: null };
    const ps = productos(r.tipo);
    return {
      estado: 'lista',
      empresa: r.empresa,
      productos: ps,
      mensaje_sugerido: `Hola, vi el ${ps[0].nombre}. ¿Qué incluye y cuánto cuesta para 2 personas?`,
    };
  }

  async function chat(
    id: string,
    token: string,
    message: string,
  ): Promise<ChatOut> {
    await esperar(1800);
    const texto = message.toLowerCase();
    if (texto.includes('fallar')) throw new DemoApiError(0);
    if (texto.includes('404')) throw new DemoApiError(404);
    const todo = leer();
    const r = registro(id, token);
    r.turnos += 1;
    todo[id] = r;
    escribir(todo);
    const ps = productos(r.tipo);
    if (/asesor|reserv|separ|pagar/.test(texto)) {
      return {
        actions: [{ type: 'say', text: `Listo, te paso con un asesor de *${r.empresa}* para confirmar. Ya le dejé todo lo que hablamos.` }],
        finished: true,
        handoff: true,
      };
    }
    if (r.turnos >= 15 || texto.includes('tope')) {
      return {
        actions: [{ type: 'say', text: 'Fue un gusto atenderte. ¡Que tengas un excelente día!' }],
        finished: true,
        handoff: false,
      };
    }
    const respuestas: string[][] = [
      [
        `¡Hola! Qué bueno que te interese el *${ps[0].nombre}*.`,
        `${ps[0].resumen}\n\nPara 2 personas te lo puedo cotizar ya mismo.`,
        '¿Para qué fechas lo estás mirando?',
      ],
      ['Perfecto. Esas fechas se llenan rápido, así que conviene separarlo pronto.', '¿Quieres que te ayude a reservarlo?'],
      [`Claro. También tenemos *${ps[1].nombre}* y *${ps[2].nombre}*. ¿Te cuento de alguno?`],
    ];
    return {
      actions: respuestas[Math.min(r.turnos - 1, respuestas.length - 1)].map((t) => ({ type: 'say', text: t })),
      finished: false,
      handoff: false,
    };
  }

  /** `POST /demo/{id}/evento` → 204. Token inválido → 404 (no se cuenta). */
  async function evento(id: string, token: string, tipo: string): Promise<void> {
    await esperar(120);
    const todo = leer();
    const r = registro(id, token);
    const eventos = ((r as Registro & { eventos?: Record<string, number> }).eventos ||= {});
    eventos[tipo] = (eventos[tipo] || 0) + 1;
    todo[id] = r;
    escribir(todo);
  }

  return { iniciar, estado, chat, evento };
})();
