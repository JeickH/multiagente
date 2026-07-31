#!/usr/bin/env bash
# Corre una consulta SQL de solo lectura contra la BD de producción (RDS
# `multiagente-db`, sa-east-1) sin exponer la base a internet: lanza una task
# ECS efímera dentro de la VPC y devuelve el resultado por CloudWatch.
#
# Uso:
#   ./backend/scripts/rds_query.sh "SELECT * FROM demo_bookings ORDER BY id DESC LIMIT 20"
#
# Requiere: AWS CLI configurado con el perfil de la cuenta 747456040509.
# Ojo: la task usa las credenciales del task role; cualquier SQL es válido,
# así que evita UPDATE/DELETE salvo que sea a propósito.
set -euo pipefail

SQL="${1:?Uso: rds_query.sh \"SELECT ...\"}"
REGION="sa-east-1"
CLUSTER="multiagente-cluster"
TASKDEF="${TASKDEF:-multiagente-backend:15}"
SUBNETS="subnet-07829afbd13c5bb8f,subnet-00f56d6ce74d72a2e"
SG="sg-0499ec72831ef7da9"

RUNNER='import os
from app.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
rows = db.execute(text(os.environ["SQL"]))
print(" | ".join(rows.keys()))
for r in rows:
    print(" | ".join("" if v is None else str(v) for v in r))'

OVERRIDES=$(python3 - "$RUNNER" "$SQL" <<'PY'
import json, sys
runner, sql = sys.argv[1], sys.argv[2]
print(json.dumps({"containerOverrides": [{
    "name": "multiagente-backend",
    "command": ["python", "-c", runner],
    "environment": [{"name": "SQL", "value": sql}],
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
aws logs tail /ecs/multiagente-backend --region "$REGION" --since 5m --format short \
  | grep "/$TASK\$" -A0 >/dev/null 2>&1 || true
aws logs get-log-events --region "$REGION" \
  --log-group-name /ecs/multiagente-backend \
  --log-stream-name "ecs/multiagente-backend/$TASK" \
  --query 'events[].message' --output text | tr '\t' '\n'
