from fastapi import APIRouter

router = APIRouter()

@router.get('/mensajes')
def get_mensajes():
    return {"mensaje": "Módulo de atención a mensajes - Disponible próximamente"}
