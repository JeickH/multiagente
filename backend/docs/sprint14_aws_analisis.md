# Sprint 14 — Análisis AWS del módulo Bots

> **Tarea**: #185 del Sprint 14 (ver `BITACORA.md`).
> **Región**: `sa-east-1` (São Paulo). **Cuenta**: `747456040509`.
> **Fecha**: 2026-05-13.
> **Autor**: Deploy AWS (delegación PM por agente fuera de cuota; analítica realizada inline por el PM con la información de `CLAUDE.md` y precios públicos AWS sa-east-1).

## §1 Estado actual verificado

El módulo Bots **no tiene infraestructura dedicada**: vive dentro del backend monolítico que corre en ECS Fargate, persiste en la misma RDS PostgreSQL y se sirve detrás del mismo ALB. La pantalla `/bots` y `/bots/[id]` se sirven desde el frontend Next.js en Amplify.

| Recurso | Identificador | Sizing | Notas |
|---------|---------------|--------|-------|
| ECS Cluster | `multiagente-cluster` | — | Un cluster, una service |
| ECS Service | `multiagente-backend-service` | 1 task | Sin auto-scaling |
| Task definition | `multiagente-backend` | 0.25 vCPU / 0.5 GB | El más pequeño posible en Fargate sa-east-1 |
| ECR repo | `multiagente-backend` | — | 1 imagen Docker, ~1 GB |
| RDS instance | `multiagente-db` | `db.t3.micro` PostgreSQL 15 | Single-AZ, 20 GB GP2 |
| ALB | `multiagente-alb-1689721042` | 1 ALB, 2 target groups | $0.027/hr fijo + LCU |
| Route 53 | `glomabeauty.com` | 1 hosted zone | Alias al ALB |
| Amplify app | `d1cfl9ey07f61o` | Frontend Next.js | Build automático desde GitHub |
| SSM Param | `/multiagente/prod/APP_ENCRYPTION_KEY` | SecureString | Para cifrado de tokens Meta |
| CloudWatch Logs | `/ecs/multiagente-backend` | Retención: probable "Never expire" (default) | A confirmar y acotar |

**Carga real**: hasta hoy 2 usuarios reales (demo CEO + pruebas). Pico observado <1 RPS. CPU promedio del task estimada <5%. Margen amplio.

**Costo agregado actual estimado**: ~$42-47/mes (alineado con `CLAUDE.md`).

## §2 Gaps y oportunidades

| # | Gap | Impacto |
|---|-----|---------|
| G1 | **No hay cron en prod** que invoque `POST /internal/bot-scheduler/tick`. En cuanto se conecte una cuenta Meta real y un bot use `delay`, los pasos pendientes quedan colgados para siempre. | **Bloqueante** para subir bots a prod con `delay`. |
| G2 | ALB cuesta ~$20/mes fijo y serves a 1 task. Sobrediseñado para la carga actual. | Ahorro potencial $15-20/mes. |
| G3 | RDS `db.t3.micro` x86 — `db.t4g.micro` (Graviton2) es ~20% más barato a igual perf en cargas pequeñas. | Ahorro $3-5/mes drop-in. |
| G4 | Sin auto-scaling configurado en ECS — quedaría corto en pico, pero hoy no hay pico. | Operativo, no de costo. |
| G5 | Logs de CloudWatch probablemente sin retención → crecen indefinidamente. | Costo futuro a 5-10 usuarios. |
| G6 | Fargate Spot no usado. Para workloads tolerantes (un task único con health check del ALB) podría ser 70% más barato. | Ahorro $6-7/mes. Riesgo: terminación esporádica de la task (~5 min de re-inicio). |
| G7 | Una sola task = sin HA. Caída del task = caída del backend (~30-60s mientras ECS recrea). | Operativo, no de costo. Acepta para esta etapa. |
| G8 | Migraciones de BD aún manuales (sin Alembic). Cada release con cambios de schema requiere `aws ecs run-task` con override. | Operativo. Ya documentado como follow-up en BITACORA. |

## §3 Propuestas de optimización

| # | Cambio | Ahorro estimado | Complejidad | Riesgo |
|---|--------|-----------------|-------------|--------|
| P1 | **Provisionar cron del scheduler de bots** con EventBridge Scheduler → Lambda invoker → `POST /internal/bot-scheduler/tick` cada 60s | $0 (free tier) | Baja (1 Lambda + 1 schedule) | Bajo. Sin esto, `delay` no funciona en prod |
| P2 | **RDS → `db.t4g.micro` Graviton** (drop-in) | -$3 a -$5/mes | Baja (snapshot + restore o `ModifyDBInstance`) | Bajo (cambio in-place ≈ 5min downtime) |
| P3 | **Quitar ALB y servir Fargate público + Route 53 alias** vía CloudMap o API Gateway HTTP API | -$15 a -$20/mes | Media (cambio de DNS, target group fuera, TLS via API Gateway o ACM en task) | Medio. Requiere replantear health checks. **Recomendado SOLO si la app sigue siendo un único endpoint** |
| P4 | **Pasar Fargate a Fargate Spot** | -$6 a -$7/mes | Baja (capacity-provider strategy en la service) | Medio. Terminación con 2min de warning; 30-60s downtime al reciclar |
| P5 | **Retención CloudWatch Logs a 30 días** | -$0.50/mes hoy, escala con carga | Trivial (`aws logs put-retention-policy`) | Nulo |
| P6 | **CloudFront delante de Amplify** (o usar Amplify-incluido CDN) | $0-2/mes; mejora latencia LATAM | Baja | Bajo |
| P7 | **Auto-scaling ECS** (1 a 4 tasks por CPU > 60%) | $0 (mismo costo en idle) — habilita escalar a 10+ usuarios sin redeploy | Baja (`aws application-autoscaling`) | Bajo |
| P8 | **NAT Gateway**: verificar si existe. Si las task están en subnets públicas con `assignPublicIp=ENABLED`, no hace falta NAT (-$32/mes ahorrados ya hoy si estaba puesto) | -$32/mes si aplica | Trivial verificación | Nulo (sólo verificar) |

> **Comando para verificar G5** (retención logs):
> ```
> aws logs describe-log-groups --region sa-east-1 \
>   --log-group-name-prefix /ecs/multiagente-backend \
>   --query 'logGroups[].[logGroupName,retentionInDays]'
> ```
> **Comando para verificar G7/P8** (subnets/IP pública):
> ```
> aws ecs describe-services --region sa-east-1 \
>   --cluster multiagente-cluster --services multiagente-backend-service \
>   --query 'services[0].networkConfiguration'
> ```

## §4 Proyección de costos (sa-east-1)

### Escenario A — 2 usuarios concurrentes (estado actual + demos)

Sizing: lo que ya hay. Sin cambios.

| Componente | Sizing | Precio unitario (sa-east-1) | $/mes |
|------------|--------|----------------------------|-------|
| ECS Fargate | 0.25 vCPU × 730h + 0.5 GB × 730h | $0.04656/vCPU-hr + $0.00511/GB-hr | $10.34 |
| ECR | 1 GB | $0.10/GB-mo | $0.10 |
| RDS `db.t3.micro` + 20 GB GP2 | 730 h + 20 GB | $0.022/hr + $0.138/GB-mo | $18.82 |
| ALB | 1 LB + ~5 LCU | $0.027/hr + ~$8/mes LCU | $27.71 |
| Route 53 | 1 hosted zone + 100k queries | $0.50 + $0.04 | $0.54 |
| Amplify (Next.js prod, baja carga) | Build + serve mínimo | — | $1.00 |
| CloudWatch Logs | 1 GB ingestion | $0.76/GB | $0.76 |
| EventBridge Scheduler | 43 200 invocaciones/mes | Free tier (14M) | $0.00 |
| Lambda tick | 43 200 inv × ~200ms × 128MB | Free tier (1M req + 400k GB-s) | $0.00 |
| Data transfer out | ~1 GB | $0.15/GB primer GB free; $0.09/GB despues | $0.15 |
| **Total** | | | **~$59/mes** |

> El número de `CLAUDE.md` (~$42-47/mes) era anterior al ALB y antes de incluir LCU reales; con el ALB el piso realista en sa-east-1 está en $55-60/mes.

### Escenario B — 5 usuarios concurrentes

Sizing: la misma task aguanta (<5% CPU). Sólo crece tráfico.

| Componente | Sizing | $/mes |
|------------|--------|-------|
| ECS Fargate | mismo (0.25/0.5GB) | $10.34 |
| ECR | 1 GB | $0.10 |
| RDS `db.t3.micro` + 20 GB | mismo | $18.82 |
| ALB | 1 LB + ~10 LCU | $30.00 |
| Route 53 | 1 hosted zone + 500k queries | $0.70 |
| Amplify | build + ~10 GB serve | $4.00 |
| CloudWatch Logs | 5 GB | $3.80 |
| EventBridge + Lambda tick | igual | $0.00 |
| Data transfer out | ~5 GB | $0.45 |
| **Total** | | **~$68/mes** |

### Escenario C — 10 usuarios concurrentes

Sizing: subir Fargate a 0.5 vCPU / 1 GB y mantener 1 task (con auto-scaling 1→2 para picos). RDS sigue siendo `db.t3.micro` hasta que las conexiones sobrepasen el límite (~85 conexiones); con SQLAlchemy pool 10 + 10 usuarios = OK.

| Componente | Sizing | $/mes |
|------------|--------|-------|
| ECS Fargate | 0.5 vCPU × 730h + 1 GB × 730h (1 task base + scaling) | $20.68 |
| ECR | 1 GB | $0.10 |
| RDS `db.t3.micro` + 20 GB | mismo | $18.82 |
| ALB | 1 LB + ~20 LCU | $35.00 |
| Route 53 | 1 hosted zone + 2M queries | $1.30 |
| Amplify | build + ~30 GB serve | $7.00 |
| CloudWatch Logs | 15 GB | $11.40 |
| EventBridge + Lambda tick | igual | $0.00 |
| Data transfer out | ~15 GB | $1.35 |
| **Total** | | **~$96/mes** |

> Si para 10 usuarios queremos HA real (2 tasks Fargate base), sumar +$10/mes → ~$106/mes.

## §5 Arquitectura recomendada + roadmap incremental

**Filosofía**: la app vale más como producto a $60-100/mes con HA y cron funcionando, que como app a $40 sin cron y sin HA. Prioridad #1 es operacional (G1, P1), no costo.

### Orden recomendado

1. **P1 — Cron del scheduler de bots (BLOQUEANTE para producción real)**. Cualquier cambio posterior espera a esto. Coste prácticamente nulo. Ver §6.
2. **P5 — Retención de logs a 30 días**. 1 comando, ahorro inmediato y futuro.
3. **P2 — RDS a `db.t4g.micro`**. Modify in-place, 5 min downtime. Ahorro $3-5/mes.
4. **P7 — Auto-scaling ECS**. No ahorra hoy, pero habilita el escenario C sin pelearnos en el momento.
5. **P8 — Verificación NAT/subnets**. Si hay NAT colgado, quitarlo libera $32/mes.
6. **(Opcional, posterior)** P3 — quitar ALB. Sólo si la app sigue siendo un único endpoint y aceptamos perder health checks managed. Ahorro $15-20/mes pero introduce complejidad. **No recomendado en esta fase.**
7. **(Descartado)** P4 — Fargate Spot. Para 1 task crítico no vale la pena el riesgo de terminación.

### Arquitectura objetivo Sprint 14

```
Internet ── Route 53 (glomabeauty.com)
              │
              ├─ Amplify (app.glomabeauty.com)  ← frontend Next.js
              │
              └─ ALB (HTTPS:443)                ← se mantiene
                    │
                    └─ ECS Fargate (multiagente-backend-service)
                          ├─ Task base: 0.25 vCPU / 0.5 GB    ← hoy
                          └─ Auto-scaling: 1 → 4 si CPU > 60% ← P7

EventBridge Scheduler (rate=1 minute)        ← P1 NUEVO
   └─ Lambda  multiagente-bot-tick           ← P1 NUEVO
         └─ POST https://app.glomabeauty.com/internal/bot-scheduler/tick
              (header X-Internal-Api-Key = SSM:/multiagente/prod/INTERNAL_API_KEY)

RDS:  db.t4g.micro PostgreSQL 15            ← P2
CloudWatch Logs: retención 30 días          ← P5
```

**Costo objetivo a 5 usuarios**: ~$65/mes (P2 + P5 + P1 sin costo adicional vs $68 hoy).
**Costo objetivo a 10 usuarios**: ~$93/mes (mismo set + auto-scaling).

## §6 Apéndice — Cómo provisionar el cron del scheduler

**Opción recomendada**: EventBridge Scheduler → Lambda invoker. Más simple y barato que ECS Scheduled Task.

### Paso A — Crear la Lambda

```bash
# 1) Crear el zip
cat > /tmp/lambda_function.py <<'PY'
import os, urllib.request, json
def lambda_handler(event, context):
    url = os.environ["TICK_URL"]
    key = os.environ["INTERNAL_API_KEY"]
    req = urllib.request.Request(
        url, method="POST",
        headers={"X-Internal-Api-Key": key, "Content-Type": "application/json"},
        data=b"{}",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return {"status": r.status, "body": r.read().decode()[:500]}
PY
cd /tmp && zip lambda.zip lambda_function.py

# 2) Rol IAM mínimo (basic execution)
aws iam create-role --region sa-east-1 \
  --role-name multiagente-bot-tick-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy \
  --role-name multiagente-bot-tick-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# 3) Crear la Lambda
aws lambda create-function --region sa-east-1 \
  --function-name multiagente-bot-tick \
  --runtime python3.11 \
  --handler lambda_function.lambda_handler \
  --role arn:aws:iam::747456040509:role/multiagente-bot-tick-role \
  --zip-file fileb:///tmp/lambda.zip \
  --timeout 30 \
  --environment 'Variables={TICK_URL=https://app.glomabeauty.com/internal/bot-scheduler/tick,INTERNAL_API_KEY=__INTERNAL_API_KEY__}'
```

> **Seguridad**: en producción, leer `INTERNAL_API_KEY` desde SSM Parameter Store (SecureString) en cada invocación, no como env var plana. Crear primero `aws ssm put-parameter --name /multiagente/prod/INTERNAL_API_KEY --type SecureString --value <random>`.

### Paso B — Crear el schedule

```bash
aws scheduler create-schedule --region sa-east-1 \
  --name multiagente-bot-tick \
  --schedule-expression 'rate(1 minute)' \
  --flexible-time-window 'Mode=OFF' \
  --target '{
    "Arn":"arn:aws:lambda:sa-east-1:747456040509:function:multiagente-bot-tick",
    "RoleArn":"arn:aws:iam::747456040509:role/EventBridgeSchedulerInvokeLambdaRole"
  }'
```

(Rol `EventBridgeSchedulerInvokeLambdaRole` con `lambda:InvokeFunction` sobre la Lambda.)

### Paso C — Verificación

```bash
# Ver últimas invocaciones
aws logs tail /aws/lambda/multiagente-bot-tick --region sa-east-1 --since 5m
# En la app, confirmar 200 OK con body {"processed": N, ...}
```

**Costo total del cron**: $0/mes en escenario A/B/C (cabe holgado en el free tier de Lambda y EventBridge Scheduler).

---

**Fin del documento**. Estado: para revisión del CEO + PM antes de iniciar tarea #186 (priorización) y #187 (implementación).
