"""Recetas del importador de productos: una por catálogo de cliente.

Cada módulo de acá sabe leer **un** archivo del cliente (un Excel, el JSON de
temporada) y devolver un `base.Catalogo`: la forma normalizada que el importador
compara contra la base y escribe. Nada de este paquete toca la base; eso lo hace
`base.py`, y solo después de que un humano aprobó el diff.

El precedente es `scripts/fuentes/` (las fuentes de mascotas): mismo reparto —
el módulo de la fuente lee, el `base` compara, arma el HTML y carga.
"""
