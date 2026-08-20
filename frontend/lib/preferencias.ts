/**
 * Preferencias de interfaz que sobreviven al refresco (cuántas filas por
 * página, etc.).
 *
 * Vive aparte de `lib/session.ts` a propósito. La regla de seguridad #7 dice
 * que la sesión del navegador se toca SOLO por `session.ts`; este archivo no
 * toca la sesión ni el token, y no debe hacerlo nunca. Son gustos del usuario,
 * no credenciales: si se pierden, no pasa nada; si se leen, tampoco.
 *
 * Todo va bajo el prefijo `gloma.pref.` para que se distinga de un vistazo de
 * lo que sí es sesión, y para poder limpiarlo sin tocar nada más.
 */

const PREFIJO = 'gloma.pref.';

/** Lee un número guardado, validándolo contra las opciones permitidas.
 *
 * La validación no es paranoia: `localStorage` es texto que el usuario puede
 * editar, y un "por página" de 99999 llegaría al backend como un intento de
 * traerse la cuenta entera. El backend igual lo rechaza (el techo está en el
 * endpoint), pero acá se evita la pantalla rota antes de salir.
 */
export function leerNumero(clave: string, permitidos: number[], porDefecto: number): number {
  if (typeof window === 'undefined') return porDefecto;
  try {
    const crudo = window.localStorage.getItem(PREFIJO + clave);
    const valor = Number(crudo);
    return permitidos.includes(valor) ? valor : porDefecto;
  } catch {
    // Safari en modo privado tira al leer. Un gusto perdido no rompe la página.
    return porDefecto;
  }
}

export function guardarNumero(clave: string, valor: number): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(PREFIJO + clave, String(valor));
  } catch {
    // no-op: si no se puede guardar, la preferencia dura lo que la pestaña.
  }
}
