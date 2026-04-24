from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import Base, engine
from .routers import auth, usuario, mensajes, campanas, bots, teams, meta_webhook, internal, landing

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
app.include_router(internal.router)
app.include_router(landing.router)
