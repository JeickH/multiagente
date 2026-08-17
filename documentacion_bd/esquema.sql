-- Esquema de referencia del módulo Recupera Tu Mascota.
-- Generado por documentacion_bd/generar.py el 2026-08-17 08:46.
-- NO es la fuente de verdad: eso es backend/app/models.py. Sirve para montar
-- un entorno nuevo o comparar dos entornos a ojo.

CREATE TABLE mascotas (
    id integer NOT NULL,
    codigo varchar(16) NOT NULL,
    tipo_registro varchar(16) NOT NULL,
    especie varchar(24) NOT NULL,
    especie_otra varchar(60),
    raza varchar(80),
    color varchar(80),
    nombre varchar(80),
    sexo varchar(16),
    edad varchar(40),
    tamano varchar(24),
    senas text,
    ubicacion varchar(255) NOT NULL,
    maps_url varchar(500),
    barrio varchar(120),
    contacto_nombre varchar(120),
    contacto_telefono varchar(32),
    fecha_evento date,
    estado varchar(24) NOT NULL DEFAULT 'activo'::character varying,
    notas text,
    bot_id integer,
    source varchar(24) NOT NULL DEFAULT 'web'::character varying,
    created_at timestamp NOT NULL DEFAULT now(),
    updated_at timestamp NOT NULL DEFAULT now(),
    origen_url varchar(500),
    origen_id varchar(120),
    reconocida_at timestamp,
    reconocida_chat varchar(64),
    ciudad varchar(120),
    departamento varchar(120),
    esterilizado boolean,
    vacunado boolean,
    desparasitado boolean,
    peso_kg numeric(5),
    salud varchar(255),
    resguardo varchar(40),
    resguardo_nombre varchar(120),
    rescatado_por varchar(120),
    rescatado_por_telefono varchar(32),
    recompensa boolean,
    estado_origen varchar(60),
    publicado_origen_at timestamp,
    sincronizado_at timestamp
);
ALTER TABLE mascotas ADD CONSTRAINT ck_mascotas_estado CHECK (((estado)::text = ANY ((ARRAY['activo'::character varying, 'reconocida'::character varying, 'reunida'::character varying, 'cerrado'::character varying])::text[])));
ALTER TABLE mascotas ADD CONSTRAINT ck_mascotas_tipo CHECK (((tipo_registro)::text = ANY ((ARRAY['perdida'::character varying, 'encontrada'::character varying])::text[])));
ALTER TABLE mascotas ADD CONSTRAINT mascotas_bot_id_fkey FOREIGN KEY (bot_id) REFERENCES bots(id) ON DELETE SET NULL;
ALTER TABLE mascotas ADD CONSTRAINT mascotas_codigo_key UNIQUE (codigo);
CREATE INDEX ix_mascotas_barrio ON public.mascotas USING btree (barrio);
CREATE INDEX ix_mascotas_bot_id ON public.mascotas USING btree (bot_id);
CREATE INDEX ix_mascotas_ciudad ON public.mascotas USING btree (ciudad);
CREATE INDEX ix_mascotas_codigo ON public.mascotas USING btree (codigo);
CREATE INDEX ix_mascotas_created_at ON public.mascotas USING btree (created_at);
CREATE INDEX ix_mascotas_departamento ON public.mascotas USING btree (departamento);
CREATE INDEX ix_mascotas_especie ON public.mascotas USING btree (especie);
CREATE INDEX ix_mascotas_estado ON public.mascotas USING btree (estado);
CREATE INDEX ix_mascotas_origen_id ON public.mascotas USING btree (origen_id);
CREATE INDEX ix_mascotas_reconocida_at ON public.mascotas USING btree (reconocida_at);
CREATE INDEX ix_mascotas_resguardo ON public.mascotas USING btree (resguardo);
CREATE INDEX ix_mascotas_source ON public.mascotas USING btree (source);
CREATE INDEX ix_mascotas_tipo_estado ON public.mascotas USING btree (tipo_registro, estado);
CREATE INDEX ix_mascotas_tipo_registro ON public.mascotas USING btree (tipo_registro);
CREATE UNIQUE INDEX mascotas_codigo_key ON public.mascotas USING btree (codigo);
CREATE UNIQUE INDEX uq_mascota_origen ON public.mascotas USING btree (source, origen_id) WHERE (origen_id IS NOT NULL);

CREATE TABLE mascota_fotos (
    id integer NOT NULL,
    mascota_id integer,
    upload_session varchar(64),
    storage_key varchar(400) NOT NULL,
    content_type varchar(60) NOT NULL DEFAULT 'image/jpeg'::character varying,
    bytes_size integer,
    created_at timestamp NOT NULL DEFAULT now(),
    optimizada boolean NOT NULL DEFAULT false,
    optimizada_at timestamp,
    bytes_original integer
);
ALTER TABLE mascota_fotos ADD CONSTRAINT mascota_fotos_mascota_id_fkey FOREIGN KEY (mascota_id) REFERENCES mascotas(id) ON DELETE CASCADE;
CREATE INDEX ix_mascota_fotos_mascota_id ON public.mascota_fotos USING btree (mascota_id);
CREATE INDEX ix_mascota_fotos_optimizada ON public.mascota_fotos USING btree (optimizada);
CREATE INDEX ix_mascota_fotos_upload_session ON public.mascota_fotos USING btree (upload_session);

CREATE TABLE mascota_coincidencias (
    id integer NOT NULL,
    perdida_id integer NOT NULL,
    encontrada_id integer NOT NULL,
    score integer NOT NULL,
    detalle jsonb,
    estado varchar(16) NOT NULL DEFAULT 'nueva'::character varying,
    notas text,
    created_at timestamp NOT NULL,
    updated_at timestamp NOT NULL
);
ALTER TABLE mascota_coincidencias ADD CONSTRAINT ck_match_estado CHECK (((estado)::text = ANY ((ARRAY['nueva'::character varying, 'revisada'::character varying, 'confirmada'::character varying, 'descartada'::character varying])::text[])));
ALTER TABLE mascota_coincidencias ADD CONSTRAINT mascota_coincidencias_encontrada_id_fkey FOREIGN KEY (encontrada_id) REFERENCES mascotas(id) ON DELETE CASCADE;
ALTER TABLE mascota_coincidencias ADD CONSTRAINT mascota_coincidencias_perdida_id_fkey FOREIGN KEY (perdida_id) REFERENCES mascotas(id) ON DELETE CASCADE;
ALTER TABLE mascota_coincidencias ADD CONSTRAINT uq_mascota_par UNIQUE (perdida_id, encontrada_id);
CREATE INDEX ix_mascota_coincidencias_created_at ON public.mascota_coincidencias USING btree (created_at);
CREATE INDEX ix_mascota_coincidencias_encontrada_id ON public.mascota_coincidencias USING btree (encontrada_id);
CREATE INDEX ix_mascota_coincidencias_estado ON public.mascota_coincidencias USING btree (estado);
CREATE INDEX ix_mascota_coincidencias_id ON public.mascota_coincidencias USING btree (id);
CREATE INDEX ix_mascota_coincidencias_perdida_id ON public.mascota_coincidencias USING btree (perdida_id);
CREATE INDEX ix_mascota_coincidencias_score ON public.mascota_coincidencias USING btree (score);
CREATE INDEX ix_match_created_at ON public.mascota_coincidencias USING btree (created_at);
CREATE INDEX ix_match_encontrada ON public.mascota_coincidencias USING btree (encontrada_id);
CREATE INDEX ix_match_estado ON public.mascota_coincidencias USING btree (estado);
CREATE INDEX ix_match_estado_score ON public.mascota_coincidencias USING btree (estado, score);
CREATE INDEX ix_match_perdida ON public.mascota_coincidencias USING btree (perdida_id);
CREATE INDEX ix_match_score ON public.mascota_coincidencias USING btree (score);
CREATE UNIQUE INDEX uq_mascota_par ON public.mascota_coincidencias USING btree (perdida_id, encontrada_id);
