"""Aplica en RDS la contraseña nueva de `demo@gmail.com`.

Corre DENTRO de una task de ECS (vía `rds_exec.sh`), que es la única forma de
llegar a la base: RDS no está expuesta a internet.

La contraseña **se lee de SSM acá adentro**, no llega por variable de entorno.
`rds_exec.sh` mete las env vars en el `containerOverrides` de la llamada a la
API, así que pasarla por ahí la dejaría escrita en CloudTrail y en el
`describe-tasks` de la task. Nunca se imprime: al log solo va si el cambio
funcionó.

Motivo de la rotación: la contraseña anterior quedó en 79 commits del
repositorio, que es público.
"""
import os
import sys

sys.path.insert(0, "/app")

import boto3

from app import crud
from app.database import SessionLocal

CORREO = "demo@gmail.com"
PARAMETRO = "/multiagente/prod/DEMO_PASSWORD"

ssm = boto3.client("ssm", region_name=os.getenv("AWS_REGION", "sa-east-1"))
nueva = ssm.get_parameter(Name=PARAMETRO, WithDecryption=True)["Parameter"]["Value"]
if not nueva or len(nueva) < 12:
    sys.exit("RESULTADO: la contraseña de SSM llegó vacía o demasiado corta")

db = SessionLocal()
try:
    user = crud.get_user_by_email(db, CORREO)
    if user is None:
        sys.exit(f"RESULTADO: {CORREO} no existe en esta base")

    user.hashed_password = crud.pwd_context.hash(nueva)
    db.add(user)
    db.commit()
    db.refresh(user)

    # La comprobación que importa: que la contraseña nueva de verdad autentique.
    ok = crud.pwd_context.verify(nueva, user.hashed_password)
    print(f"RESULTADO: contraseña actualizada para {CORREO} | verifica={ok}")
    print(f"RESULTADO: longitud={len(nueva)} (el valor no se imprime)")
finally:
    db.close()
