# Documentación de la base de datos — módulo Recupera Tu Mascota

Todo lo que hay que saber sobre las tablas donde viven los reportes de mascotas,
y sobre cómo se mapea cada fuente externa contra ellas.

> El objetivo del esquema es **centralizar**: una sola tabla `mascotas` capaz de
> recibir lo que publica cualquiera de las seis fuentes, sin que ninguna tenga
> que meter datos dentro de un campo de texto libre para que quepan.

| Archivo | Qué es | Para quién |
|---|---|---|
| [`index.html`](index.html) | La documentación completa, con el diagrama y las tablas. **Empieza por aquí** | Todos |
| [`diccionario_datos.md`](diccionario_datos.md) | Campo por campo: qué significa, quién lo llena, qué pasa si está en NULL | Quien escribe código contra la tabla |
| [`mapeo_fuentes.md`](mapeo_fuentes.md) | Matriz fuente × campo: qué publica cada plataforma y qué se pierde | Quien agrega o arregla un importador |
| [`esquema_mascotas.puml`](esquema_mascotas.puml) | Diagrama entidad-relación (PlantUML) | Quien necesita el diagrama en otro formato |
| [`flujo_importacion.puml`](flujo_importacion.puml) | Diagrama de secuencia del flujo de importación con aprobación | Quien opera las cargas |
| [`esquema.sql`](esquema.sql) | DDL de referencia de las tres tablas | Quien monta un entorno nuevo |

## Cómo se regenera

`index.html`, `diccionario_datos.md` y `esquema.sql` se generan leyendo la base
**real**, no a mano: así no se desactualizan sin que nadie se dé cuenta.

```bash
source /opt/anaconda3/etc/profile.d/conda.sh && conda activate multiagente
python documentacion_bd/generar.py
```

Los `.puml` se editan a mano (son pocos y cambian poco). Para verlos como
imagen, cualquier visor de PlantUML sirve; en VS Code, la extensión PlantUML.

## Regla de paridad

La base local (docker-compose `db`) y la de producción (RDS `multiagente-db`,
sa-east-1) **deben tener siempre el mismo esquema**. Toda migración se aplica en
los dos entornos en el mismo PR. Si al generar esta documentación los conteos de
columnas no coinciden entre entornos, hay una migración a medio aplicar.

```bash
# local
docker compose -p wati exec -T -w /app -e PYTHONPATH=/app backend \
    python scripts/migrate_campos_multifuente.py
# producción
TASKDEF=multiagente-backend:NN ./backend/scripts/rds_exec.sh \
    backend/scripts/migrate_campos_multifuente.py
```

## Contexto

- Manual operativo del módulo: [`../MANUAL_RECUPERA_TU_MASCOTA.md`](../MANUAL_RECUPERA_TU_MASCOTA.md)
- Importadores con revisión manual: `backend/scripts/actualizar_fuente.py`
- Modelo SQLAlchemy: `backend/app/models.py` (`Mascota`, `MascotaFoto`, `MascotaCoincidencia`)
