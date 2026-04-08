from fastapi import APIRouter

router = APIRouter()

@router.get('/bots')
def get_bots():
    return {"mensaje": "Módulo de bots de servicio WhatsApp - Disponible próximamente"}
