#!/usr/bin/env bash
#
# Deja el bucket y el rol listos para la subida DIRECTA de adjuntos a S3.
#
# Por qué existe: el archivo que el asesor manda por la ventana de Mensajes ya
# no viaja por nuestra API. Entre el navegador y ECS hay dos saltos con techo
# propio —el compute de Amplify (~4,4 MB, porque el cuerpo va en base64 dentro
# de un payload de Lambda) y el API Gateway HTTP (10 MB duros, cuota que AWS no
# deja subir)—, así que un video de 10 MB no pasaba por más que el código dijera
# 16. Ahora el navegador sube contra S3 con un POST prefirmado, y para eso hacen
# falta tres cosas que no viven en el repo:
#
#   1. CORS en el bucket: sin esto el navegador ni siquiera manda el POST.
#   2. Una regla de ciclo de vida sobre `adjuntos-tmp/`, la zona de tránsito:
#      si el asesor abandona la pestaña entre el `preparar` y el `confirmar`,
#      el archivo queda ahí y nadie lo va a borrar a mano.
#   3. Permiso del rol de ECS sobre los dos prefijos.
#
# Es idempotente: se puede correr las veces que haga falta.
#
#   ./backend/scripts/configurar_s3_adjuntos.sh
#
set -euo pipefail

REGION="sa-east-1"
BUCKET="${ADJUNTOS_BUCKET:-gloma-mascotas-747456040509}"
ROL="multiagente-ecs-task-role"
POLICY="adjuntos-s3-subida-directa"

echo "==> Bucket: ${BUCKET} (${REGION})"

# --- 1. CORS -----------------------------------------------------------------
# Solo POST, y solo desde nuestros orígenes. `localhost` está para que el flujo
# se pueda probar entero desde una máquina de desarrollo apuntando al bucket.
# No se expone ningún header: el navegador no necesita leer nada de la
# respuesta de S3, le alcanza con el 204.
echo "==> CORS"
aws s3api put-bucket-cors --bucket "${BUCKET}" --region "${REGION}" \
  --cors-configuration '{
    "CORSRules": [
      {
        "AllowedMethods": ["POST"],
        "AllowedOrigins": [
          "https://app.glomabeauty.com",
          "https://www.glomabeauty.com",
          "https://glomabeauty.com",
          "https://main.d1cfl9ey07f61o.amplifyapp.com",
          "http://localhost:3000"
        ],
        "AllowedHeaders": ["*"],
        "MaxAgeSeconds": 3000
      }
    ]
  }'

# --- 2. Ciclo de vida de la zona de tránsito ---------------------------------
# 1 día es el mínimo que acepta S3 y sobra: entre el `preparar` y el
# `confirmar` pasan segundos, y el POST prefirmado expira a los 10 minutos.
#
# OJO: `put-bucket-lifecycle-configuration` REEMPLAZA todas las reglas del
# bucket, no agrega. Por eso se leen las que ya hay y se reescriben junto con
# la nueva — el bucket lo comparten las fotos de mascotas.
echo "==> Ciclo de vida de adjuntos-tmp/"
ACTUALES=$(aws s3api get-bucket-lifecycle-configuration \
  --bucket "${BUCKET}" --region "${REGION}" --query 'Rules' --output json 2>/dev/null || echo '[]')

REGLAS=$(python3 - "$ACTUALES" <<'PY'
import json, sys
reglas = [r for r in json.loads(sys.argv[1]) if r.get("ID") != "borrar-adjuntos-temporales"]
reglas.append({
    "ID": "borrar-adjuntos-temporales",
    "Status": "Enabled",
    "Filter": {"Prefix": "adjuntos-tmp/"},
    "Expiration": {"Days": 1},
    "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
})
print(json.dumps({"Rules": reglas}))
PY
)
aws s3api put-bucket-lifecycle-configuration --bucket "${BUCKET}" --region "${REGION}" \
  --lifecycle-configuration "${REGLAS}"

# --- 3. Permisos del rol de ECS ----------------------------------------------
# Acotado a los dos prefijos de adjuntos y nada más. `adjuntos/*` se declara
# explícito aunque hoy la escritura ya funcione: que un permiso del que depende
# el envío de archivos esté escrito en algún lado y no se sepa dónde es un
# problema esperando a que alguien "limpie" políticas.
echo "==> IAM: ${POLICY} en ${ROL}"
aws iam put-role-policy --role-name "${ROL}" --policy-name "${POLICY}" \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "AdjuntosDefinitivos",
        "Effect": "Allow",
        "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
        "Resource": "arn:aws:s3:::'"${BUCKET}"'/adjuntos/*"
      },
      {
        "Sid": "ZonaDeTransitoDeSubidas",
        "Effect": "Allow",
        "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
        "Resource": "arn:aws:s3:::'"${BUCKET}"'/adjuntos-tmp/*"
      }
    ]
  }'

echo
echo "==> Listo. Verificación:"
aws s3api get-bucket-cors --bucket "${BUCKET}" --region "${REGION}" \
  --query 'CORSRules[0].AllowedOrigins' --output text
aws s3api get-bucket-lifecycle-configuration --bucket "${BUCKET}" --region "${REGION}" \
  --query 'Rules[?ID==`borrar-adjuntos-temporales`].[ID,Status,Expiration.Days]' --output text
aws iam get-role-policy --role-name "${ROL}" --policy-name "${POLICY}" \
  --query 'PolicyDocument.Statement[].Resource' --output text
