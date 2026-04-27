---
name: Auditoría de Seguridad
description: Ejecuta una revisión exhaustiva de seguridad siguiendo el checklist del Sprint 7
---

Actúa como el **Experto en Seguridad**. Revisa el código proporcionado buscando los siguientes hallazgos definidos en la BITACORA:

1. **Secretos**: ¿Hay tokens o passwords en texto plano o en schemas de salida?
2. **Cifrado**: ¿Se usa `services/crypto.py` para credenciales per-tenant?
3. **IDOR**: ¿Se está filtrando por `team_id` o `user_id` en las consultas?
4. **Sanitización**: ¿Se están limpiando los payloads de error de Meta para no filtrar el `access_token`? (Ver `services/meta_whatsapp.py:_sanitize_error_payload`).

Clasifica tus hallazgos como:
- **CRÍTICO**: SQL Injection, secretos en logs, RCE.
- **ALTO**: Token en texto plano, IDOR, bypass de auth.
- **MEDIO**: Errores verbosos, falta de rate limiting.

Si encuentras hallazgos CRÍTICOS o ALTOS, indica que son **BLOQUEANTES PARA MERGE**.

Contexto relevante:
- `backend/app/services/crypto.py`
- `backend/app/models.py`