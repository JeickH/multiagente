#!/usr/bin/env bash
# Ejecuta un script Python arbitrario contra la BD de producción (RDS
# `multiagente-db`, sa-east-1) lanzando una task ECS efímera dentro de la VPC.
# Hermano de `rds_query.sh`, pero para escrituras/migraciones: sirve para correr
# un script de `backend/scripts/` que todavía NO está en la imagen de ECR.
#
# Uso:
#   ./backend/scripts/rds_exec.sh backend/scripts/migrate_sprint22_x.py VAR=valor ...
#
# El archivo se envía como el cuerpo de un `python -c`, así que debe ser
# autocontenido (sólo imports de `app.*`, que sí están en la imagen).
# Las env vars extra se pasan al contenedor. OJO: los overrides de ECS quedan
# registrados en CloudTrail — nunca pases secretos en claro por aquí (para
# passwords, pasa el hash bcrypt ya calculado, no el plaintext).
set -euo pipefail

PYFILE="${1:?Uso: rds_exec.sh <script.py> [VAR=valor ...]}"
shift
REGION="sa-east-1"
CLUSTER="multiagente-cluster"
TASKDEF="${TASKDEF:-multiagente-backend:15}"
SUBNETS="subnet-07829afbd13c5bb8f,subnet-00f56d6ce74d72a2e"
SG="sg-0499ec72831ef7da9"

OVERRIDES=$(python3 - "$PYFILE" "$@" <<'PY'
import json, sys
code = open(sys.argv[1]).read()
env = []
for pair in sys.argv[2:]:
    k, _, v = pair.partition("=")
    env.append({"name": k, "value": v})
print(json.dumps({"containerOverrides": [{
    "name": "multiagente-backend",
    "command": ["python", "-c", code],
    "environment": env,
}]}))
PY
)

TASK=$(aws ecs run-task --region "$REGION" --cluster "$CLUSTER" \
  --task-definition "$TASKDEF" --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=ENABLED}" \
  --overrides "$OVERRIDES" \
  --query 'tasks[0].taskArn' --output text | awk -F/ '{print $NF}')

echo "task=$TASK (esperando...)" >&2
aws ecs wait tasks-stopped --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK"
aws logs get-log-events --region "$REGION" \
  --log-group-name /ecs/multiagente-backend \
  --log-stream-name "ecs/multiagente-backend/$TASK" \
  --query 'events[].message' --output text | tr '\t' '\n'
