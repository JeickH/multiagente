# Carga en la shell las credenciales de UNA cuenta de Twilio y dice cuál quedó activa.
#
# Hay dos cuentas de Twilio independientes (no son matriz y subcuenta):
#   multiagente  → la de Arranquemos Pues      → CREDENCIALES_TWILIO.txt
#   gloma        → el WhatsApp propio de Gloma → CREDENCIALES_TWILIO_GLOMA.txt
# Cualquier otra se agrega creando CREDENCIALES_TWILIO_<NOMBRE>.txt en la raíz.
# Los archivos están en .gitignore (`CREDENCIALES*.txt`) y nunca se commitean.
#
# Uso (se hace `source`, no se ejecuta, para que las variables queden en la shell):
#   source backend/scripts/twilio_cuenta.sh gloma
#   curl -s -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" "https://api.twilio.com/..."
#
# Cada llamada de Bash de Claude abre una shell nueva: el `source` va en el
# mismo comando que la consulta, nunca en uno aparte.
#
# Exporta TWILIO_CUENTA, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN y, si están en el
# archivo, TWILIO_API_KEY_SID / TWILIO_API_KEY_SECRET. Antes de devolver el
# control imprime nombre, estado y saldo de la cuenta. Nunca imprime un secreto.

_tw_cuenta="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
_tw_raiz="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

case "$_tw_cuenta" in
  multiagente|arranquemos) _tw_archivo="$_tw_raiz/CREDENCIALES_TWILIO.txt" ;;
  "")
    echo "Uso: source backend/scripts/twilio_cuenta.sh <multiagente|gloma|...>" >&2
    _tw_archivo="" ;;
  *) _tw_archivo="$_tw_raiz/CREDENCIALES_TWILIO_$(printf '%s' "$_tw_cuenta" | tr '[:lower:]' '[:upper:]').txt" ;;
esac

if [ -n "$_tw_archivo" ] && [ ! -f "$_tw_archivo" ]; then
  echo "No existe $(basename "$_tw_archivo"): créalo en la raíz del repo con TWILIO_ACCOUNT_SID= y TWILIO_AUTH_TOKEN=" >&2
  _tw_archivo=""
fi

if [ -n "$_tw_archivo" ]; then
  # Se limpian las de la cuenta anterior para que una clave vieja no se cuele.
  unset TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN TWILIO_API_KEY_SID TWILIO_API_KEY_SECRET
  while IFS='=' read -r _tw_k _tw_v; do
    _tw_k="$(printf '%s' "$_tw_k" | tr -d '[:space:]')"
    _tw_v="$(printf '%s' "$_tw_v" | tr -d '[:space:]')"
    case "$_tw_k" in
      TWILIO_ACCOUNT_SID|TWILIO_AUTH_TOKEN|TWILIO_API_KEY_SID|TWILIO_API_KEY_SECRET)
        [ -n "$_tw_v" ] && export "$_tw_k=$_tw_v" ;;
    esac
  done < "$_tw_archivo"
  export TWILIO_CUENTA="$_tw_cuenta"

  if [ -z "${TWILIO_ACCOUNT_SID:-}" ] || [ -z "${TWILIO_AUTH_TOKEN:-}" ]; then
    echo "[$_tw_cuenta] faltan TWILIO_ACCOUNT_SID o TWILIO_AUTH_TOKEN en $(basename "$_tw_archivo")" >&2
  else
    # Un 401 con "not active" es cuenta suspendida, no clave mala (ver memoria).
    curl -s -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
      "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID.json" \
      | python3 -c 'import sys,json; d=json.load(sys.stdin); print("[%s] %s… %s | %s %s" % (sys.argv[1], sys.argv[2][:8], d.get("friendly_name") or "", d.get("status") or "ERROR", d.get("message") or ""))' \
        "$_tw_cuenta" "$TWILIO_ACCOUNT_SID"
    curl -s -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
      "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/Balance.json" \
      | python3 -c 'import sys,json; d=json.load(sys.stdin); b=d.get("balance"); b is not None and print("    saldo:", b, d.get("currency"))'
  fi
fi

unset _tw_cuenta _tw_raiz _tw_archivo _tw_k _tw_v
