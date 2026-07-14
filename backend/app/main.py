import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import Base, engine
from .routers import auth, usuario, mensajes, campanas, bots, teams, meta_webhook, internal, landing, contacts, templates, campaigns, twilio_webhook

# #255: los logs de la app (p. ej. `llm_decision ...` del motor de bots) van a
# nivel INFO. Sin esto el root logger queda en WARNING y las decisiones del
# LLM no se ven en CloudWatch/docker logs.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Multiagente API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(usuario.router)
app.include_router(mensajes.router)
app.include_router(campanas.router)
app.include_router(bots.router)
app.include_router(teams.router)
app.include_router(meta_webhook.router)
app.include_router(twilio_webhook.router)
app.include_router(internal.router)
app.include_router(landing.router)
app.include_router(contacts.router)
app.include_router(templates.router)
app.include_router(campaigns.router)
