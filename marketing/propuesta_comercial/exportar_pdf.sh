#!/usr/bin/env bash
# Convierte una propuesta comercial en HTML a PDF con Chrome headless.
#
#   ./marketing/propuesta_comercial/exportar_pdf.sh                      # las 3 opciones
#   ./marketing/propuesta_comercial/exportar_pdf.sh opcion_b.html        # una sola
#   ./marketing/propuesta_comercial/exportar_pdf.sh opcion_b.html --publicar
#
# Con --publicar, el PDF de esa opción queda además en
# frontend/public/gloma/propuesta-comercial-gloma.pdf, que es el que descarga
# el botón de la landing.
#
# Chrome: en el Mac usa el de /Applications; en otro lado, el de $CHROME o el
# primero que encuentre en el PATH. En la nube no viene instalado
# (se baja con: npx -y @puppeteer/browsers install chrome@stable).
#
# Los HTML deben declarar <meta charset="utf-8">: sin eso Chrome rompe las
# tildes. El tamaño de página lo pone el @page del HTML (A4), no este script.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
RAIZ="$(cd "$DIR/../.." && pwd)"
SALIDA="$DIR/pdf"
PUBLICO="$RAIZ/frontend/public/gloma/propuesta-comercial-gloma.pdf"

MAC_CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ -n "${CHROME:-}" ]; then
  :
elif [ -x "$MAC_CHROME" ]; then
  CHROME="$MAC_CHROME"
else
  CHROME="$(command -v google-chrome || command -v chromium || command -v chromium-browser || command -v chrome || true)"
fi
if [ -z "$CHROME" ] || [ ! -x "$CHROME" ]; then
  echo "No encontré Chrome. Define CHROME=/ruta/al/chrome." >&2
  exit 1
fi

# Como root (la nube), Chrome no arranca con su sandbox.
extra=()
if [ "$(id -u)" = "0" ]; then
  extra+=(--no-sandbox)
fi

publicar=0
archivos=()
for arg in "$@"; do
  case "$arg" in
    --publicar) publicar=1 ;;
    *) archivos+=("$arg") ;;
  esac
done

if [ ${#archivos[@]} -eq 0 ]; then
  archivos=(opcion_a.html opcion_b.html opcion_c.html)
fi
if [ $publicar -eq 1 ] && [ ${#archivos[@]} -ne 1 ]; then
  echo "Con --publicar se pasa una sola opción (la elegida)." >&2
  exit 1
fi

mkdir -p "$SALIDA"
for html in "${archivos[@]}"; do
  origen="$DIR/$(basename "$html")"
  if [ ! -f "$origen" ]; then
    echo "No existe $origen (se omite)" >&2
    continue
  fi
  pdf="$SALIDA/$(basename "${html%.html}").pdf"
  # El presupuesto de tiempo virtual deja que carguen las fuentes de Google.
  "$CHROME" --headless=new --disable-gpu --no-pdf-header-footer ${extra[@]+"${extra[@]}"} \
    --virtual-time-budget=10000 --print-to-pdf="$pdf" "file://$origen" 2>/dev/null
  echo "OK  $pdf  ($(du -h "$pdf" | cut -f1))"
  if [ $publicar -eq 1 ]; then
    cp "$pdf" "$PUBLICO"
    echo "Publicado en $PUBLICO"
  fi
done
