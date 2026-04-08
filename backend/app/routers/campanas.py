from fastapi import APIRouter

router = APIRouter()

@router.get('/campanas')
def get_campanas():
    return {"mensaje": "Módulo de campañas de envío masivo - Disponible próximamente"}
