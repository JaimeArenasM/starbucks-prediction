from fastapi import APIRouter, HTTPException
from app.schemas.inventory_schema import (
    InventoryOptimizationRequest,
    InventoryOptimizationResponse
)
from app.services.forecast_service import forecast_multi_day_demand
from app.services.inventory_service import optimize_replenishment
from app.utils.errors import DatasetError, AnalysisError, SelectionError

# Router del endpoint de optimización
router = APIRouter(tags=["Optimización"])

@router.post("/optimize-inventory", response_model=InventoryOptimizationResponse)
def optimize_inventory(request: InventoryOptimizationRequest):
    """Predice demanda diaria con SARIMAX y optimiza el plan de compras con A*."""
    try:
        # SARIMAX predice la demanda del horizonte
        demand_forecast = forecast_multi_day_demand(
            store_id=request.store_id,
            product_id=request.product_id,
            steps=request.horizon_days
        )

        # Si no envían costo de compra, usamos 50% del precio histórico
        applied_unit_cost = (
            request.unit_purchase_cost
            if request.unit_purchase_cost is not None
            else round(demand_forecast["unit_price"] * 0.5, 2)
        )

        # A* arma el plan con esa demanda y costo
        return optimize_replenishment(
            request=request,
            forecasted_demands=demand_forecast["predicted_demands"],
            forecast_dates=demand_forecast["dates"],
            applied_unit_cost=applied_unit_cost
        )

    # Errores de negocio a HTTP: 404 si no existe, 400 si faltan datos
    except SelectionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (DatasetError, AnalysisError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))