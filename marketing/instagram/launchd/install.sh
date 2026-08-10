#!/bin/zsh
# Instala/actualiza el runner del cron FUERA de ~/Documents.
#
# Por qué: macOS (TCC) bloquea a los agentes de launchd el acceso a
# ~/Documents, así que el cron no puede ejecutar nada que viva en el repo.
# Este script copia el publicador a ~/Library/Application Support/gloma-igpost
# y recarga los jobs. Correrlo de nuevo tras cualquier cambio en igpost.py/ig/.
set -euo pipefail

REPO="/Users/equipo/Documents/gloma_software/marketing/instagram"
DEST="$HOME/Library/Application Support/gloma-igpost"
LOGS="$HOME/Library/Logs/gloma-igpost"

mkdir -p "$DEST" "$LOGS"
rsync -a --delete --exclude '__pycache__' "$REPO/igpost.py" "$REPO/ig" "$DEST/"

# Runner: corre run-due desde la copia instalada; silencia los ticks vacíos.
cat > "$DEST/run_due.sh" <<'SH'
#!/bin/zsh
cd "$HOME/Library/Application Support/gloma-igpost" || exit 1
SALIDA=$(/opt/anaconda3/envs/multiagente/bin/python igpost.py run-due 2>&1)
CODIGO=$?
if [[ "$SALIDA" != "Nada por publicar." ]]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] exit=$CODIGO"
  echo "$SALIDA"
fi
exit $CODIGO
SH
chmod +x "$DEST/run_due.sh"

# Los plists del repo apuntan a la copia instalada; recargar.
cp "$REPO/launchd/com.gloma.igpost.rundue.plist" \
   "$REPO/launchd/com.gloma.igpost.refresh.plist" "$HOME/Library/LaunchAgents/"
launchctl bootout "gui/$(id -u)/com.gloma.igpost.rundue" 2>/dev/null || true
launchctl bootout "gui/$(id -u)/com.gloma.igpost.refresh" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.gloma.igpost.rundue.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.gloma.igpost.refresh.plist"

echo "Instalado en: $DEST"
echo "Logs en:      $LOGS"
launchctl list | grep com.gloma
