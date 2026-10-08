import { useRouter } from 'next/router';
import { useCallback, useEffect, useRef, useState } from 'react';
import Layout from '../components/Layout';
import AvisoInteresados from '../components/agendamientos/AvisoInteresados';
import PanelInteresados from '../components/agendamientos/PanelInteresados';
import PanelLlamadas, { ResumenLlamadas } from '../components/agendamientos/PanelLlamadas';
import TabsAgendamientos from '../components/agendamientos/TabsAgendamientos';
import { useInteresados } from '../components/agendamientos/useInteresados';
import { Vista, vistaInicial } from '../lib/interesados';

/**
 * Agendamientos: dos listas de a quién contactar, cada una con su ritmo.
 *
 * - **Interesados** (#22, horas): clientes a los que el bot les notó intención
 *   de compra y que, `umbral_horas` después de su primer mensaje, siguen
 *   hablando con el bot. Hay que escribirles antes de que se cierre la ventana
 *   de 24 h de WhatsApp. Solo existe si algún bot del team tiene la detección
 *   encendida (`habilitado`); si no, la página es exactamente la de antes.
 * - **Llamadas agendadas** (días): quien dejó la conversación después de
 *   recibir información; el bot agenda la llamada para 3 días después.
 *
 * La pestaña activa vive en la URL (`?vista=interesados|llamadas`) para que se
 * pueda enlazar directo. Sin parámetro, abre Interesados si hay alguno por
 * contactar: es la lista que se vence en horas.
 *
 * La ven todas las cuentas del team — administrador y asesor —, por eso vive en
 * el menú de siempre y no detrás de un `/access` como los módulos internos.
 */
export default function AgendamientosPage() {
  const router = useRouter();
  const s = useInteresados();
  const [vista, setVista] = useState<Vista | null>(null);
  const [resumenLlamadas, setResumenLlamadas] = useState<ResumenLlamadas | null>(null);

  // ¿Se muestran las pestañas? 404 o `habilitado: false` → la página de antes.
  // Con error y sin datos no se sabe: se muestran, con el error en su panel.
  const conocido = s.noDisponible || s.datos !== null || !!s.error;
  const conPestanas = !s.noDisponible && (s.datos ? s.datos.habilitado : !!s.error);
  const resumen = s.datos?.resumen;
  const porContactar = resumen?.por_contactar ?? 0;

  // Elegir la pestaña la primera vez, y seguir a la URL si cambia por fuera
  // (un enlace a `?vista=interesados` con la página ya abierta).
  const pedidaPrevia = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!router.isReady) return;
    const q = router.query.vista;
    const pedida = Array.isArray(q) ? q[0] : q;

    if (vista === null) {
      if (pedida === 'llamadas') setVista('llamadas');
      else if (pedida === 'interesados' && !conocido) setVista('interesados');
      else if (conocido) setVista(vistaInicial(pedida, conPestanas, porContactar));
      pedidaPrevia.current = pedida;
      return;
    }
    if (vista === 'interesados' && conocido && !conPestanas) {
      setVista('llamadas');
      return;
    }
    if (pedida !== pedidaPrevia.current) {
      pedidaPrevia.current = pedida;
      if (pedida === 'llamadas' || (pedida === 'interesados' && conPestanas)) setVista(pedida);
    }
  }, [router.isReady, router.query.vista, vista, conocido, conPestanas, porContactar]);

  const cambiarVista = useCallback(
    (v: Vista) => {
      setVista(v);
      pedidaPrevia.current = v;
      router.replace(
        { pathname: router.pathname, query: { ...router.query, vista: v } },
        undefined,
        { shallow: true, scroll: false },
      );
    },
    [router],
  );

  const onResumenLlamadas = useCallback((r: ResumenLlamadas) => setResumenLlamadas(r), []);

  const enInteresados = conPestanas && vista === 'interesados';
  const decidiendo = vista === null;

  return (
    // `fullscreen` como el resto de los listados: el default (`centered`)
    // mete el contenido en una tarjeta angosta y la tabla se sale por los
    // lados.
    <Layout variant="fullscreen">
      <div className="p-4 md:p-8">
        <header className="mb-5">
          <h1 className="text-2xl md:text-3xl font-heading font-bold text-gloma-brown-darker">
            📞 Agendamientos
          </h1>
          <p className="text-gray-600 mt-1 text-sm md:text-base">
            {enInteresados ? (
              <>
                Clientes que mostraron intención de compra y siguen hablando con el bot.
                Escríbeles o llámalos antes de que se cierre la ventana de WhatsApp.
              </>
            ) : (
              <>
                Clientes potenciales que dejaron la conversación después de recibir
                información. El bot agenda la llamada para 3 días después.
              </>
            )}
          </p>
        </header>

        {conPestanas && vista !== null && (
          <TabsAgendamientos
            vista={vista}
            onCambiar={cambiarVista}
            porContactar={resumen ? resumen.por_contactar : null}
            urgentes={resumen?.urgentes ?? 0}
            pendientesLlamadas={resumenLlamadas ? resumenLlamadas.pendientes : null}
          />
        )}

        {decidiendo && (
          <div className="space-y-3" aria-busy="true">
            <span className="sr-only">Cargando…</span>
            <div className="h-11 w-full md:w-80 rounded-xl bg-gloma-soft-mint animate-pulse motion-reduce:animate-none" />
            <div className="h-28 rounded-xl bg-white border border-gray-200" />
          </div>
        )}

        {conPestanas && (
          <div
            id="panel-interesados"
            role="tabpanel"
            aria-labelledby="tab-interesados"
            hidden={vista !== 'interesados'}
          >
            <PanelInteresados
              s={s}
              activo={vista === 'interesados'}
              onIrALlamadas={() => cambiarVista('llamadas')}
            />
          </div>
        )}

        {/* Llamadas se monta siempre (aunque esté oculta): su resumen alimenta
            el contador de la pestaña. */}
        <div
          {...(conPestanas
            ? { id: 'panel-llamadas', role: 'tabpanel', 'aria-labelledby': 'tab-llamadas' }
            : {})}
          hidden={vista !== 'llamadas'}
        >
          <PanelLlamadas
            activo={vista === 'llamadas'}
            onResumen={onResumenLlamadas}
            aviso={
              conPestanas && resumen ? (
                <AvisoInteresados
                  porContactar={resumen.por_contactar}
                  urgentes={resumen.urgentes}
                  ventanaCerrada={resumen.ventana_cerrada}
                  onVer={() => cambiarVista('interesados')}
                />
              ) : null
            }
          />
        </div>
      </div>
    </Layout>
  );
}
