import heapq
from typing import List, Tuple, Dict
from app.schemas.inventory_schema import (
    InventoryOptimizationRequest,
    InventoryOptimizationResponse,
    DailyPlanStep
)
from app.utils.errors import AnalysisError

# Estado de la búsqueda: (día interno, stock al inicio del día)
State = Tuple[int, int]

# Tamaños de pedido permitidos; A* solo elige entre estos
ORDER_QUANTITY_OPTIONS = [0, 10, 20, 30, 50, 80, 100]

# Pista de costo mínimo restante (nunca exagera)
def _estimate_remaining_cost(
    day_index: int,
    inventory_level: int,
    daily_demands: List[int],
    purchase_cost_per_unit: float
) -> float:
    """Heurística admisible h(n) alimentada por SARIMAX."""
    remaining_demand_units = sum(daily_demands[day_index:])
    units_to_cover = max(0, remaining_demand_units - inventory_level)
    return units_to_cover * purchase_cost_per_unit

# A* sobre estados (día, stock): elige los pedidos de menor costo
def optimize_replenishment(
    request: InventoryOptimizationRequest,
    forecasted_demands: List[float],
    forecast_dates: List[str],
    applied_unit_cost: float
) -> InventoryOptimizationResponse:
    # Demanda entera por día, recortada al horizonte
    daily_demands = [max(0, round(d)) for d in forecasted_demands[:request.horizon_days]]
    planning_days = len(daily_demands)

    # La demanda y las fechas deben cubrir el horizonte solicitado
    if planning_days < request.horizon_days:
        raise AnalysisError("La demanda proyectada no cubre el horizonte solicitado.")
    if len(forecast_dates) < planning_days:
        raise AnalysisError("Las fechas no cubren el horizonte solicitado.")

    # Estado inicial y estructuras de la búsqueda
    initial_estimated_cost = _estimate_remaining_cost(
        0, request.initial_inventory, daily_demands, applied_unit_cost
    )
    # open_set: (costo estimado total, costo acumulado, día, stock), ordenado por el primero
    open_set = [(initial_estimated_cost, 0.0, 0, request.initial_inventory)]

    # came_from: estado destino -> (estado anterior, pedido, costo del día, no atendido)
    came_from: Dict[State, Tuple[State, int, float, int]] = {}
    # g_score: menor costo conocido para llegar a cada estado
    g_score: Dict[State, float] = {(0, request.initial_inventory): 0.0}

    expanded_state_count = 0
    goal_state = None

    # Sacamos el estado más prometedor; si es el último día, terminamos
    while open_set:
        _, current_cost, day_index, inventory_level = heapq.heappop(open_set)

        if day_index == planning_days:
            goal_state = (day_index, inventory_level)
            break

        # Si ya había un camino más barato a este estado, lo descartamos
        if current_cost > g_score.get((day_index, inventory_level), float("inf")):
            continue

        # Contamos solo los estados que realmente se expanden
        expanded_state_count += 1

        # Cuentas del día y opciones de pedido
        daily_demand = daily_demands[day_index]

        for order_quantity in ORDER_QUANTITY_OPTIONS:
            available_units = inventory_level + order_quantity
            served_units = min(available_units, daily_demand)
            ending_inventory = available_units - served_units
            unmet_units = daily_demand - served_units

            # Costo del día: pedido + almacenaje + faltante
            order_cost = (
                request.order_fixed_cost + order_quantity * applied_unit_cost
            ) if order_quantity > 0 else 0.0
            holding_cost = ending_inventory * request.holding_cost_per_unit
            stockout_cost = unmet_units * request.stockout_penalty_per_unit
            day_cost = order_cost + holding_cost + stockout_cost

            # Si el nuevo camino es más barato, guardamos costo y migas
            candidate_cost = current_cost + day_cost
            next_state = (day_index + 1, ending_inventory)

            if candidate_cost < g_score.get(next_state, float("inf")):
                g_score[next_state] = candidate_cost
                came_from[next_state] = (
                    (day_index, inventory_level),
                    order_quantity,
                    day_cost,
                    unmet_units,
                )

                # f = costo acumulado + heurística
                estimated_remaining_cost = _estimate_remaining_cost(
                    day_index + 1, ending_inventory, daily_demands, applied_unit_cost
                )
                estimated_total_cost = candidate_cost + estimated_remaining_cost
                heapq.heappush(
                    open_set,
                    (estimated_total_cost, candidate_cost, day_index + 1, ending_inventory),
                )

    # Si A* no llegó a la meta, no hay plan que reconstruir
    if goal_state is None:
        raise AnalysisError("No se encontró un plan factible para el horizonte.")

    # Reconstrucción: desde la meta hacia el inicio con came_from
    daily_plan: List[DailyPlanStep] = []
    current_state = goal_state
    total_cost = g_score[goal_state]

    while current_state in came_from:
        previous_state, order_quantity, day_cost, unmet_units = came_from[current_state]
        previous_day_index, starting_inventory = previous_state
        _, ending_inventory = current_state

        daily_plan.append(DailyPlanStep(
            day=previous_day_index + 1,
            date=forecast_dates[previous_day_index],
            predicted_demand=daily_demands[previous_day_index],
            starting_inventory=starting_inventory,
            order_quantity=order_quantity,
            ending_inventory=ending_inventory,
            unmet_demand=unmet_units,
            day_cost=round(day_cost, 2)
        ))
        current_state = previous_state

    # Invertimos para que el plan quede del día 1 al último
    daily_plan.reverse()

    # Respuesta: plan, costo total y nodos explorados
    return InventoryOptimizationResponse(
        store_id=request.store_id,
        product_id=request.product_id,
        unit_purchase_cost_used=round(applied_unit_cost, 2),
        total_cost=round(total_cost, 2),
        nodes_explored=expanded_state_count,
        plan=daily_plan
    )
