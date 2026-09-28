/**
 * Rangos de "¿cuántos chats reciben al mes?" del formulario de la landing.
 * Van alineados con los paquetes de conversaciones (600 / 2.000 / 6.000) para
 * llegar a la demo con el paquete ya calculado. Los valores son los que acepta
 * `LeadIn.chats_mes` en `backend/app/routers/landing.py`.
 */
export const CHATS_MES_OPCIONES = [
  { value: 'menos_600', label: 'Menos de 600' },
  { value: '600_2000', label: 'Entre 600 y 2.000' },
  { value: '2000_6000', label: 'Entre 2.000 y 6.000' },
  { value: 'mas_6000', label: 'Más de 6.000' },
  { value: 'no_se', label: 'No lo sé todavía' },
] as const;

export function etiquetaChatsMes(value: string | null | undefined): string | null {
  if (!value) return null;
  return CHATS_MES_OPCIONES.find((o) => o.value === value)?.label ?? value;
}
