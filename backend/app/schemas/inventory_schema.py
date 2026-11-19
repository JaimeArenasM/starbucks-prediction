from pydantic import BaseModel, Field
from typing import List

# Entrada de A* (que producto, cuantos dias, stock actual y costos)
class InventoryOptimizationRequest(BaseModel):
    store_id: int | None = Field(default=3, example=3, description="ID de tienda (None para global)")
    product_id: int = Field(..., example=22)
    horizon_days: int = Field(default=7, ge=1, le=30, description="Días a planificar")
    initial_inventory: int = Field(default=10, ge=0, description="Stock actual en tienda")

    # Costos que A* compara en cada decision (pedir, almacenar y quedarse sin stock)
    order_fixed_cost: float = Field(default=15.0, ge=0, description="Costo fijo por envío/pedido")
    unit_purchase_cost: float | None = Field(
        default=None, ge=0,
        description="Costo unitario de compra (si es None, usa 50% del unit_price histórico)"
    )
    holding_cost_per_unit: float = Field(default=0.5, ge=0, description="Costo diario por almacenar unidad sobrante")
    stockout_penalty_per_unit: float = Field(default=5.0, ge=0, description="Penalización por unidad de demanda no atendida")

#Una fila del plan
class DailyPlanStep(BaseModel):
    day: int
    date: str
    predicted_demand: int
    starting_inventory: int
    order_quantity: int
    ending_inventory: int
    unmet_demand: int
    day_cost: float

# Salida de A* (plan completo, costo y cuantos estados exploró)
class InventoryOptimizationResponse(BaseModel):
    store_id: int | None
    product_id: int
    unit_purchase_cost_used: float
    total_cost: float
    nodes_explored: int
    plan: List[DailyPlanStep]