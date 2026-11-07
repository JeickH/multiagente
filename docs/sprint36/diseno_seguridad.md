# Sprint 36 — Revisión de diseño de seguridad (antes de implementar)

Agente `seguridad`, 7-nov-2026, solo lectura sobre `feature/bots-arranquemos-base` (`370f4f9`).
Sin Críticos. **Los Alto son bloqueantes para merge.** Los Medio solo pueden salir como
follow-up si el PM los acepta por escrito en la BITACORA; no se dejan fuera 2.6 (costo) ni 2.7 (24 h).

## Hallazgos de contexto

- Team: `/mensajes` resuelve el team en el servidor (`get_current_membership` →
  `crud.get_membership_for_user`) y carga con `crud.get_conversation(db, member.team_id, id)` (ajena → 404).
- `routers/supervision.py` es todo GET, detrás de `require_gloma_account` + `SUPERVISION_CUENTAS`.
- Hoy el que vuelve queda en silencio: `_marcar_abandonada` (`bot_runner.py`) asigna a una asesora y
  deja `pending`; `bot_router.resolve_bot_for_incoming_message` (paso 0) corta si `assigned_to != "bot"`.
  `cerrar_inactivas_arranquemos.py` cierra con nota y no toca `assigned_to`.
- Nadie escribe aún las columnas nuevas (ni `_marcar_abandonada`, ni el script, ni `crud.add_message`).
- Los webhooks (`process_twilio_inbound`, `meta_webhook.receive_webhook`) corren el turno en línea;
  no hay tope de turnos Bedrock por conversación en WhatsApp.
- Ningún router escribe `nota_interna` (solo el sistema).
- `record_decision` guarda en `bot_llm_decisions.tools_called` lo que el bot le pasa a cada tool.

## 0. Esquema `370f4f9`

Bien: CHECK del valor, índice único parcial de venta activa, `__repr__` sin valor ni nota, backfill
que solo llena NULL, `lock_timeout`. Faltan:

1. **[Alto]** `team_id` de la venta = `conv.team_id`, con la conversación cargada por
   `crud.get_conversation(db, member.team_id, cid)`. Nunca del body.
2. **[Medio]** Defensa en BD con FK compuesta: `CREATE UNIQUE INDEX CONCURRENTLY uq_conversations_id_team
   ON conversations (id, team_id)` + `ALTER TABLE conversation_sales ADD CONSTRAINT
   fk_conversation_sales_conv_team FOREIGN KEY (conversation_id, team_id) REFERENCES conversations (id, team_id)
   ON DELETE CASCADE`. Declararlo también en `models.py` (UniqueConstraint + ForeignKeyConstraint).
   `CONCURRENTLY` va en bloque autocommit. El verificador comprueba la FK.
3. **[Alto]** Escribir los marcadores con reset por episodio: `_marcar_abandonada` pone
   `abandono_at=now, abandono_asesor=asesor, reclamos_abandono=0` en el mismo commit;
   el script de inactividad pone `cerrada_por_inactividad_at=now, reclamos_abandono=0` en el mismo UPDATE.
4. **[Alto]** `ultimo_mensaje_humano_at` se mantiene en un solo lugar: `crud.add_message` cuando
   `direction=='outbound'`, `sent_by_user_id is not None` y `message_type != 'nota_interna'`
   (+ sello previo de 2.4b).
5. **[Bajo]** `ck_conversation_sales_anulacion CHECK ((anulada_at IS NULL AND motivo_anulacion IS NULL AND
   anulada_por_user_id IS NULL) OR (anulada_at IS NOT NULL AND motivo_anulacion IS NOT NULL))`.
6. **[Bajo]** La venta no se edita: corregir = anular + registrar otra.
7. **[Bajo, dato]** `conversation_sales.bot_id` (FK bots, `ON DELETE SET NULL`, nullable) para atribuir
   «ventas por bot» aunque el reenganche cambie de bot.
8. **[Bajo]** Documentar que `ON DELETE CASCADE` desde `conversations` borra ventas (solo limpieza de tenants/demos).
9. `__repr__` de `Conversation` y `ConversationSale`: bien.

## 1. Botón «venta cerrada»

Endpoints en `routers/mensajes.py`:
- `POST /mensajes/conversaciones/{conversation_id}/venta` (`VentaIn`).
- `POST /mensajes/conversaciones/{conversation_id}/venta/anular` (`AnularVentaIn`), sobre la venta activa;
  el id de la venta no viaja en la URL.
- Lectura: `ConversationWithMessages.venta` + `ventas_anuladas`; `ConversationOut.venta_valor_cop` en la
  bandeja (una consulta por página, como `previews_de_conversaciones`); en `supervision.py`,
  `HiloOut`/`HiloDetalleOut` con `venta_valor_cop` y `vendida_at`, solo lectura.

Controles:
1. **[Alto]** `require_permission("can_reply_messages")`; `crud.get_conversation(db, member.team_id, id)`;
   `None` → 404 «Conversación no encontrada» igual para ajena e inexistente; nada de team en el body.
2. **[Alto]** Supervisión solo ve: cero rutas no-GET en `supervision.py`; la admin de Gloma (team 7) que
   llame al POST sobre team 5 recibe 404. Ocultar el botón en `/conversaciones` es solo UX.
3. **[Medio]** Doble registro: `IntegrityError` sobre `uq_conversation_sales_activa` → rollback + 409.
   Anular = un solo `UPDATE ... WHERE conversation_id=:c AND team_id=:t AND anulada_at IS NULL`; 0 filas → 404.
4. **[Medio]** `VentaIn` con `extra="forbid"`: `valor_cop: Annotated[int, Field(strict=True, gt=0,
   le=models.VENTA_VALOR_MAX_COP)]`; `nota` ≤280, strip, vacío→None, sin caracteres de control salvo `\n`;
   `vendida_por` strip ≤64 y en `crud.asesores_del_team(db, member.team)` (si no, 422);
   `AnularVentaIn.motivo` obligatorio 3–280.
5. **[Medio]** `VentaOut` solo en el detalle de `/mensajes`: `{id, valor_cop, vendida_por, nota,
   registrada_at, registrada_por_nombre, anulada_at, motivo_anulacion}`. Lista: solo `venta_valor_cop`.
   Supervisión: solo `venta_valor_cop` y `vendida_at`. Nunca `team_id` ni campos de `users` salvo el nombre.
6. **[Medio]** Auditoría: `registrada_por_user_id`, `anulada_por_user_id`, `anulada_at`, motivo; sin DELETE.
   Logs solo con ids (`venta.registrada id=%s conversation_id=%s team_id=%s user_id=%s`). No se loggea valor,
   nota, `vendida_por`, motivo, nombre ni teléfono. Errores: `logger.exception` + mensaje genérico.
7. **[Bajo]** Login compartido de asesoras: la atribución real es `vendida_por` (documentar).
8. **[Bajo]** Front: nota como texto, campo numérico, sesión solo por `lib/session.ts`.

Tests exigidos: 201 con permiso / 403 sin él; ajena 404 sin cambios; admin team 7 sobre team 5 → 404;
test que recorre `supervision.router.routes` y exige GET; `0, -1, 500_000_001, "1000", 1000.5, true` → 422
y `500_000_000` pasa; `vendida_por` ajeno → 422; doble registro 409 y con dos sesiones Postgres gana una;
anular sin motivo 422, anular dos veces → 404, tras anular se registra otra; JSON de supervisión sin
`nota`/`motivo_anulacion`/`registrada_por_user_id`; `caplog` sin valor/nota/nombres; con FK compuesta,
INSERT con team distinto falla en Postgres.

## 2. Reenganche y reasignación

1. **[Alto]** Una transición atómica en un solo lugar: `services/reenganche.py::reclamar(db, team, conv,
   asignado_leido)`, llamada **solo** desde `bot_router.resolve_bot_for_incoming_message` antes del paso 0
   (cubre los dos webhooks). Nunca desde el tick, `process_pending_action` ni `run_turn`. Un solo UPDATE:
   ```sql
   UPDATE conversations SET reclamos_abandono = reclamos_abandono + 1, assigned_to='bot', status='open'
   WHERE id=:id AND team_id=:team AND reclamos_abandono=0 AND assigned_to=:asignado_leido
     AND ((abandono_at IS NOT NULL AND status='pending')
       OR (cerrada_por_inactividad_at IS NOT NULL AND status='closed'))
   ```
   1 fila = ganó.
2. **[Medio]** Las acciones humanas consumen el marcador: `close_conversation`, `reopen_conversation` y
   `assign_conversation` dejan `reclamos_abandono >= 1` (opcional `marcador_consumido` volvio|humano).
3. **[Alto]** Aislamiento del bot de reenganche. Preferido: `bots.es_reenganche BOOLEAN NOT NULL DEFAULT false`
   + `uq_bot_reenganche_por_owner ON bots(user_id) WHERE es_reenganche`. Alternativa `teams.bot_reenganche_id`
   (FK bots, SET NULL) con endpoint solo-owner que valide `bot.user_id == owner` (404 igual ajeno/inexistente)
   + trigger `BEFORE INSERT OR UPDATE OF bot_reenganche_id ON teams` (lo crea la migración, lo comprueba el
   verificador). En ambos casos, al usarlo: elegir solo de la lista `bots` que ya arma
   `resolve_bot_for_incoming_message` (`user_id == team.owner_user_id`, `status=='active'`, sin
   `llm_config.demo`, `engine=='llm'`); el respaldo (`ultima_sesion_cerrada(...).bot` o `conv.bot_asignado_id`)
   pasa el mismo filtro, si no → reparto normal. **Nunca** `db.query(Bot).get(id)` sin filtro. Historial solo
   por `BotSession.conversation_id == conv.id`.
4. **[Alto]** Regla de las 2 h: (a) `crud.add_message` (0.4); (b) en `send_message_in_conversation`,
   `_validar_guardar_y_enviar` y `start_new_conversation` sellar `ultimo_mensaje_humano_at` y commit **antes**
   de `messaging.send_*`; (c) en `reclamar`, antes de Bedrock: si `ultimo_mensaje_humano_at >= utcnow()-2h`,
   solo nota «Volvió» y consume el marcador; (d) en `run_turn`, ampliar `_cambio_de_dueno` para releer
   `ultimo_mensaje_humano_at` antes del primer envío; si cambió, se descarta el turno (todos los bots).
   «Tomada» no cuenta.
5. **[Alto]** Bucles: solo un entrante real (tras firma, aislamiento y dedupe) dispara el reclamo; la nota la
   escribe solo quien gana el UPDATE (máx. una por episodio); la nota es `nota_interna` con
   `sent_by_user_id` NULL y no cuenta como entrante, humano ni presentación; ninguna ruta saliente ni el tick
   llama a `reclamar`.
6. **[Medio, no se deja fuera]** Tope de turnos LLM por conversación en `bot_router`, contado en
   `bot_llm_decisions.conversation_id`: 30/hora y 120/día; exceso → sin turno, warning sin texto, una sola
   nota interna. Opcional: una pura cortesía (`llm_engine.es_cortesia`) solo deja nota.
7. **[Medio, no se deja fuera]** Ventana 24 h en `bot_runner._procesar_silencio` antes de `_send_text`: si
   `ahora >= ultimo_entrante + VENTANA_WHATSAPP - 10 min`, el recordatorio no sale, queda omitido («fuera de
   24 h») y la cadena sigue (si las siguientes también quedan fuera, directo al abandono).
   `VENTANA_WHATSAPP` está en `services/agendamientos.py`. Mismo chequeo en `_programar` tras
   `silencio.fuera_del_silencio`.
8. **[Medio, preexistente]** Serializar turnos por conversación con `pg_try_advisory_lock(conv.id)`; si no se
   obtiene, el mensaje queda guardado y lo levanta el turno en curso o el tick. Puede ir de follow-up.
9. **[Bajo]** Si el bot reclama, cerrar o anotar la llamada de rescate pendiente del abandono; no pisar
   `bot_asignado_id/at` sin decidirlo (atribución A/B); `_reabrir_conversacion` borra la etiqueta: poner la
   marca «Volvió» después.
10. **[Bajo]** Logs: `reenganche.reclamado conv=%s team=%s bot=%s via=abandono|inactividad`,
    `reenganche.solo_aviso conv=%s motivo=humano_2h`; sin texto, teléfono ni nombres; el resumen de la nota
    sin teléfonos ni cédula (reusar la redacción de `llm_engine`).

Tests exigidos: abandonada → `bot`, `reclamos=1`, una nota, un turno (Bedrock simulado), segundo entrante sin
otra nota; cerrada por inactividad se reclama; NO se reclaman la cerrada por asesora, la cerrada por despedida
del bot, la reabierta y la reasignada por owner; humano hace 1 h 59 → solo nota (una vez), 2 h 01 → bot toma;
`llm_engine.advance` parcheado que inserta un humano a mitad de turno → no envía; bot de reenganche de otro
owner forzado en BD se ignora (y pausado, demo, `flow`); dos reclamos concurrentes en Postgres → gana uno;
espía: tick y acciones pendientes nunca llaman `reclamar`; recordatorio corrido fuera de 24 h no sale y la
cadena llega al abandono, dentro sí sale; turno 31 en la hora no llama Bedrock; `add_message` sella solo
humano saliente no-nota; `caplog` sin texto ni teléfono.

## 3. Agenda de llamadas del bot D (puerta 2)

Piezas: franjas en `services/horario.py` (hoy sin festivos); tool en `llm_engine.py` con el patrón de
`franja_valida` (#291); datos en `models.Agendamiento` y `services/agendamientos.py`; resultado en
`routers/agendamientos.py`; avisos en el tick de `routers/internal.py`.

1. **[Alto]** Bandera en dos sitios: apagada (default) → la tool no se declara **y** su handler la rechaza.
   Se lee en el servidor desde `llm_config`.
2. **[Alto]** Determinismo: `agendar_llamada(opcion)` con `opcion` integer enum [1..5],
   `additionalProperties: false`; el modelo nunca envía fecha ni hora. Al ofrecer, el servidor arma las 5
   franjas (`horario.proximas_franjas_llamada(ahora, cfg, festivos, ocupacion)`) y las guarda en
   `state["franjas_ofrecidas"]` (inicio en UTC). El handler traduce la opción y **revalida**: inicio > ahora
   + 30 min, `horario.en_horario`, no festivo, no 23–05 h, hay cupo. Si falla, no guarda y devuelve la lista
   recalculada.
3. **[Alto]** Cupo en BD. Columnas nuevas en `agendamientos`: `franja_inicio TIMESTAMP NULL`,
   `puesto SMALLINT NULL CHECK (puesto >= 1)`, `origen VARCHAR(16)` (`abandono`|`bot_llamada`),
   `resultado`, `resultado_por_user_id`, `resultado_at`, `aviso_inicio_at`, `alerta_fin_at`,
   `cotizacion TEXT` (≤1000). Índice `CREATE UNIQUE INDEX uq_agendamientos_franja_puesto ON agendamientos
   (team_id, franja_inicio, puesto) WHERE franja_inicio IS NOT NULL AND estado = 'pendiente'`. Inserción
   probando puestos 1..cupo en `db.begin_nested()`; `IntegrityError` → siguiente puesto; agotados → «franja
   llena». Con `uq_agendamientos_conv_pendiente` (una pendiente por conversación): si ya existe la del
   abandono, **actualizar esa fila** en la misma transacción; cambiar de franja actualiza la misma fila y libera
   el puesto viejo.
4. **[Alto]** `PATCH /agendamientos/{id}/resultado` `{resultado: Literal['vendida','lo_pensara','no_contesto']}`
   `extra="forbid"`; `get_current_membership` (o `can_reply_messages`); filtro `Agendamiento.team_id ==
   member.team_id` en el WHERE (ajeno → mismo 404); guarda `resultado_por_user_id` y `resultado_at`;
   `vendida` **no** crea venta; supervisión solo lee.
5. **[Medio]** Avisos idempotentes: el tick ya exige `INTERNAL_API_KEY`; emitir solo si
   `UPDATE agendamientos SET aviso_inicio_at=now WHERE id=:id AND aviso_inicio_at IS NULL` toca 1 fila (igual
   `alerta_fin_at`). Avisos solo dentro de la plataforma (WhatsApp al celular de la asesora requiere revisión aparte).
6. **[Medio]** `cotizacion` la arma el servidor (plan, fechas, n.º personas, total, anticipo); sin cédula,
   teléfono, nombres ni edades; `tools_called` solo con la opción; logs `agenda.llamada conv=%s team=%s
   franja=%s puesto=%s`; `Agendamiento.__repr__` sin cotización; `AgendamientoOut` solo para el team.
7. **[Medio]** Festivos 2026–2027 en configuración; año no cubierto → ese día no se ofrecen franjas + warning
   una vez; el lunes 16-nov-2026 nunca se ofrece.
8. **[Bajo]** Zona `horario._zona` (America/Bogota), guardar UTC naive, front con `lib/fechas.ts`.
9. **[Bajo]** La franja solo se ofrece a conversaciones que llegaron al cierre; aplica el tope 2.6.

Tests exigidos: bandera apagada → tool ausente y handler directo rechaza sin filas; opción `0, 6, "3", 2.5`
o ausente → error; franja vencida → error + lista nueva; festivo, 23–05 h y fuera de horario nunca se
ofrecen; modelo simulado que pide «domingo 3 a.m.» o «franja 7» → rechazo; cupo=1 con dos sesiones
concurrentes → 1 fila y «llena»; cupo=2 con tres → 2; mismo cliente que cambia de franja → 1 fila; con
pendiente de abandono previa se actualiza sin `IntegrityError`; resultado: otro team 404, inválido 422, sin
token 401, auditoría guardada, `vendida` no crea venta; tick dos veces → un aviso y una alerta; 2028 → sin
franjas; `caplog` sin teléfono, nombre ni cotización.

## Preexistentes vistos de paso

- [Medio] Sin serialización de turnos por conversación ni tope Bedrock en WhatsApp (2.6, 2.8).
- [Bajo] `crud.get_membership_for_user` usa `.first()` sin `ORDER BY` → `order_by(TeamMember.id)`.
- [Bajo] Dedupe de entrantes por `meta_message_id` consulta-y-luego-inserta, índice no único.

## Bloqueantes para merge

Esquema 0.1, 0.3, 0.4 · Venta 1.1, 1.2 · Reenganche 2.1, 2.3, 2.4, 2.5 · Agenda 3.1, 3.2, 3.3, 3.4.
