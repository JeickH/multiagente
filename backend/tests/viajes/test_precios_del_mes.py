"""El "desde" es el del mes que pidió el cliente, no el más barato (F7).

Bug reportado por el CEO (Sprint 24): un cliente dijo que le interesaba
**septiembre**, preguntó por precios, y el bot le contestó con un "desde" que
era el **mínimo de todos los meses publicados**. Eso es cotizarle un viaje que
no va a hacer, y el reclamo llega cuando va a pagar.

La causa tiene dos mitades. Una vive en `services/tarifario.py` (la herramienta
le pegaba a su respuesta unas líneas con cifras constantes) y la arregla otro
agente. **La otra vive en el prompt**, y es la que cubre este archivo: el
documento traía dos precios escritos a mano —`$350.000` y `$389.000` para las
salidas entre semana— y, peor, una orden explícita de *"menciona la promo desde
$350.000"*. Con eso ahí, da igual lo que devuelva la herramienta: el modelo
tiene un número a la mano y lo dice.

Es el gotcha de siempre en este proyecto: **las reglas del prompt se diluyen
entre sí**. Justo al lado de "Las fechas concretas nunca salen de tu memoria"
había dos cifras de memoria y una orden de recitarlas. La regla fuerte perdía
contra el número concreto.

Por eso los tests de aquí son de dos clases:

- que la orden vieja y sus cifras **ya no estén** (barrido de dinero incluido,
  para que nadie vuelva a pegar un precio en el documento sin darse cuenta);
- que lo que la regla protegía **siga en pie**: el bot tiene que seguir
  contestando "sí, hay salidas entre semana", que era falso negar y por eso se
  escribió esa sección.
"""
from __future__ import annotations

import re

import pytest

from app.services import llm_engine

from tests.viajes.test_primer_mensaje import _plano, _prompt, _seccion


#: Cualquier cifra de dinero escrita en el documento.
_MONEDA = re.compile(r"\$\s?\d[\d.,]*")

#: Las tres únicas cifras que el bot sí puede decir de memoria, porque no
#: dependen del mes, ni del hotel, ni de la fecha. El resto lo dice la
#: herramienta. Se listan por su valor normalizado (sin puntos ni símbolo).
_CIFRAS_QUE_NO_DEPENDEN_DEL_MES = {
    "55000",    # seguro de viaje, menores de 2 años
    "195000",   # silla + seguro, de 3 a 4 años
    "25000",    # canoa a la Casa Flotante (opcional del itinerario)
    "3000",     # bici-taxi al Malecón
    "4000",     # bici-taxi al Malecón
}


def _cifras(texto: str) -> set:
    return {re.sub(r"\D", "", m.group(0)) for m in _MONEDA.finditer(texto)}


# ---------------------------------------------------------------------------
# F7.1 — la cifra memorizada ya no está en el prompt
# ---------------------------------------------------------------------------

class TestNingunPrecioDelPlanVivEnElPrompt:
    @pytest.mark.parametrize("cifra", ["350.000", "350000", "389.000", "389000"])
    def test_los_precios_de_entre_semana_desaparecieron(self, bot, cifra):
        """Los dos que citó el bug. Estaban en `### Días de salida`."""
        assert cifra not in _prompt(bot), (
            f"{cifra} sigue en el prompt: el modelo lo va a decir aunque la "
            f"herramienta le entregue el del mes correcto"
        )

    def test_ya_no_le_ordena_mencionar_una_promo_con_cifra(self, bot):
        """La frase más dañina no era el número suelto, era la orden de
        decirlo: "menciona la promo desde $350.000"."""
        texto = _plano(_prompt(bot))
        assert "menciona la promo desde" not in texto
        assert not re.search(r"menciona\w*\s+(?:la\s+)?promo[^.]{0,40}\$", texto), (
            "quedó una orden de mencionar un precio escrito a mano"
        )

    def test_los_ejemplos_ya_no_traen_un_precio_copiable(self, bot):
        """En `Cómo se ve bien hecho` había dos respuestas modelo con
        `$459.000` dentro. Se leen como un dato, no como un ejemplo: es el
        mismo bug con otra ropa."""
        seccion = _seccion(_prompt(bot), "Regla de oro: no afirmes NI niegues "
                                         "lo que no esté aquí")
        assert "459" not in seccion
        assert "$<" in seccion, (
            "los ejemplos perdieron el hueco `$<...>`: sin él, el modelo no "
            "sabe de dónde tiene que sacar la cifra"
        )

    def test_barrido_completo_de_cifras_de_dinero(self, bot):
        """El guardarraíl de verdad: **cualquier** precio nuevo que alguien
        pegue en el documento hace fallar este test.

        Sin él, arreglar los dos de hoy no impide que mañana entre otro — que
        es literalmente cómo llegó éste.
        """
        coladas = _cifras(_prompt(bot)) - _CIFRAS_QUE_NO_DEPENDEN_DEL_MES
        assert not coladas, (
            f"hay precios escritos a mano en el prompt: {sorted(coladas)}. "
            f"Si de verdad no dependen del mes ni del hotel, agrégalos a "
            f"`_CIFRAS_QUE_NO_DEPENDEN_DEL_MES` y documenta por qué"
        )


# ---------------------------------------------------------------------------
# F7.2 — la regla que protegía esas cifras sigue en pie
# ---------------------------------------------------------------------------

class TestSiguenExistiendoLasSalidasEntreSemana:
    """Quitar los números no puede costar la capacidad de contestar.

    La sección existe porque el bot decía "solo tenemos de viernes a lunes",
    que es **falso** y cierra la venta. Si al borrar los precios el bot se queda
    sin saber que hay salidas entre semana, cambié un bug por otro peor.
    """

    def test_el_prompt_sigue_diciendo_que_si_hay(self, bot):
        seccion = _seccion(_prompt(bot), "Conocimiento del plan Tolú & Coveñas")
        assert "Hay salidas" in seccion and "entre semana" in seccion
        assert "la respuesta es **sí, hay**" in seccion

    def test_y_sigue_prohibiendo_la_frase_falsa(self, bot):
        seccion = _seccion(_prompt(bot), "Conocimiento del plan Tolú & Coveñas")
        assert 'nunca "solo tenemos de viernes a lunes", que es falso' in seccion

    def test_sabe_que_son_mas_economicas_sin_decir_cuanto(self, bot):
        """Lo cualitativo se puede afirmar sin consultar; lo cuantitativo no.
        Es lo que permite contestar con seguridad y sin inventar."""
        seccion = _seccion(_prompt(bot), "Conocimiento del plan Tolú & Coveñas")
        assert "más económicas" in seccion
        assert "sin ninguna cifra" in seccion

    def test_la_salvedad_de_piedra_mar_no_se_perdio(self, bot):
        seccion = _seccion(_prompt(bot), "Conocimiento del plan Tolú & Coveñas")
        assert "no aplican para lunes festivos" in seccion


# ---------------------------------------------------------------------------
# F7.3 — la regla nueva: el "desde" es el del mes
# ---------------------------------------------------------------------------

class TestElDesdeEsElDelMes:
    def test_esta_escrito_y_es_explicito(self, bot):
        texto = _plano(_prompt(bot))
        assert (
            'El "desde" es el del mes del que están hablando, no el más barato '
            "que conozcas"
        ) in texto

    def test_cuenta_el_caso_que_lo_originó(self, bot):
        """El documento aprende de casos reales, no de reglas abstractas: es lo
        que hizo que la sección de cierre por fin funcionara."""
        texto = _plano(_prompt(bot))
        assert "alguien dijo que le interesaba *septiembre*" in texto
        assert "mínimo de todos los meses publicados" in texto

    def test_el_mes_dicho_manda_para_todo_lo_que_siga(self, bot):
        """El bug del CEO no fue en el turno del mes, fue **más adelante**: la
        persona dijo septiembre y varios turnos después preguntó el precio."""
        texto = _plano(_prompt(bot))
        assert "ese mes manda para todo lo que digas después" in texto
        assert "Si después cambia de mes, vuelves a consultar" in texto

    def test_los_precios_pesan_igual_que_las_fechas(self, bot):
        """El documento era enfático con las fechas ("nunca salen de tu
        memoria") y tibio con los precios ("salen siempre de la herramienta").
        El bug salió justo por esa asimetría."""
        texto = _plano(_prompt(bot))
        assert "**Las fechas concretas nunca salen de tu memoria**" in texto, (
            "la regla de las fechas desapareció"
        )
        assert "**Ninguna cifra de dinero sale de tu memoria.**" in texto
        assert "Esto pesa **igual** que la regla de las fechas" in texto

    def test_sin_haber_consultado_no_hay_precio_que_decir(self, bot):
        texto = _plano(_prompt(bot))
        assert "no tienes un solo precio que decir" in texto


class TestLaExcepcionQueEvitaLaContradiccion:
    """Una regla absoluta que el propio documento incumple se vuelve opcional.

    El documento **sí** le enseña tres cifras al bot: lo de los niños, los
    opcionales del itinerario y el 30% de la reserva. Si "ninguna cifra sale de
    tu memoria" no las excluye a mano, el modelo ve la contradicción y resuelve
    por su cuenta — que es la peor manera de resolverla.
    """

    def test_la_lista_de_excepciones_esta_escrita(self, bot):
        texto = _plano(_prompt(bot))
        assert "Las **únicas** cifras que sí puedes decir de memoria" in texto
        for excepcion in ("niños", "opcionales", "**30%**"):
            assert excepcion in texto, f"falta la excepción {excepcion!r}"

    def test_y_es_cerrada(self, bot):
        assert "Todo lo demás" in _plano(_prompt(bot))

    def test_ninos_sigue_siendo_algo_que_el_bot_sabe(self, bot):
        """Sin esto el bot escalaría "voy con un niño de 3 años", que es un
        dato que tiene en la mano y una fricción que no hace falta."""
        seccion = _seccion(_prompt(bot), "Conocimiento del plan Tolú & Coveñas")
        assert "Esto sí lo sabes" in seccion
        assert "$55.000" in seccion and "$195.000" in seccion


# ---------------------------------------------------------------------------
# F7.4 — no romper F3 de camino
# ---------------------------------------------------------------------------

class TestElPrimerMensajeSigueSinPrecios:
    def test_la_apertura_no_trae_ni_una_cifra_de_dinero(self, bot):
        """F3 metió el itinerario en el primer mensaje. El itinerario de abajo
        trae los opcionales con su valor; la versión de la apertura no puede
        arrastrarlos, o el bot abre cotizando sin saber el mes."""
        seccion = _seccion(_prompt(bot), "El primer mensaje")
        assert not _cifras(seccion), (
            f"la apertura trae cifras de dinero: {sorted(_cifras(seccion))}"
        )

    def test_y_sigue_llevando_el_itinerario_y_la_pregunta_del_nombre(self, bot):
        """El chequeo cruzado: que F7 no haya recortado lo de F3."""
        seccion = _seccion(_prompt(bot), "El primer mensaje")
        assert "Así es el plan día a día" in seccion
        assert "¿Con quién tengo el gusto? 😊" in seccion


# ---------------------------------------------------------------------------
# La herramienta sigue enchufada
# ---------------------------------------------------------------------------

class TestConsultarTarifarioSigueDisponible:
    def test_el_bot_tiene_la_herramienta(self, bot):
        """Quitarle los precios al prompt sólo es seguro si la herramienta
        está: si no, el bot se queda mudo ante "¿cuánto vale?"."""
        nombres = {t["name"] for t in llm_engine._tools_for(bot.cfg)}
        assert "consultar_tarifario" in nombres

    def test_y_recibe_el_mes(self, bot):
        """El "desde" del mes correcto depende de poder pasarle el mes."""
        tool = next(
            t for t in llm_engine._tools_for(bot.cfg)
            if t["name"] == "consultar_tarifario"
        )
        assert "mes" in tool["input_schema"]["properties"]
