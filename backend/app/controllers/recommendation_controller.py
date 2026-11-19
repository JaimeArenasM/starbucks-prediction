from fastapi import APIRouter, HTTPException

from app.schemas.recommendation_schema import (
    CoffeeOptionsResponse,
    CoffeeRecommendationRequest,
    CoffeeRecommendationResponse,
)
from app.services.recommendation_service import (
    get_coffee_options,
    recommend_coffees,
)
from app.utils.errors import AnalysisError, DatasetError, SelectionError

# Router del recomendador de cafés con KNN
router = APIRouter(tags=["Recomendación"])


@router.get("/coffee-options", response_model=CoffeeOptionsResponse)
def coffee_options(store_id: int | None = None):
    # Devuelve categorías, tipos y productos para llenar el formulario.
    try:
        return get_coffee_options(store_id)
    except SelectionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (DatasetError, AnalysisError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/recommend-coffees", response_model=CoffeeRecommendationResponse)
def recommend_coffee_products(request: CoffeeRecommendationRequest):
    # Ejecuta la estrategia elegida: semilla, preferencias o popularidad.
    try:
        return recommend_coffees(
            store_id=request.store_id,
            hour=request.hour,
            category=request.category,
            product_type=request.product_type,
            max_price=request.max_price,
            seed_product_id=request.seed_product_id,
            top_k=request.top_k,
        )
    except SelectionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (DatasetError, AnalysisError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
