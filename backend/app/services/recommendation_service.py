from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.models.dataset_model import load_dataset
from app.utils.errors import AnalysisError, SelectionError

# Categorías que tienen sentido para recomendar una bebida o café.
RECOMMENDABLE_CATEGORIES = (
    "Coffee",
    "Coffee beans",
    "Tea",
    "Drinking Chocolate",
)

# Variables categóricas y numéricas que forman el vector de cada producto.
CATEGORICAL_FEATURES = ["product_category", "product_type"]
NUMERIC_FEATURES = [
    "mean_price",
    "units_per_ticket",
    "morning_share",
    "afternoon_share",
    "evening_share",
    "weekend_share",
]


@dataclass(frozen=True)
class RecommendationModel:
    # Guarda el catálogo, la matriz de features y el buscador KNN ya entrenado.
    store_id: int | None
    store_location: str
    products: pd.DataFrame
    matrix: np.ndarray
    neighbors: NearestNeighbors


def _extract_base_name(product_name: str) -> str:
    # Quita el tamaño para no recomendar el mismo café en otro tamaño.
    for suffix in (" Sm", " Rg", " Lg"):
        if product_name.endswith(suffix):
            return product_name[: -len(suffix)]
    return product_name


def _extract_size(product_name: str) -> str:
    # Guarda el tamaño solo para mostrarlo en la respuesta.
    for suffix in (" Sm", " Rg", " Lg"):
        if product_name.endswith(suffix):
            return suffix.strip()
    return "Único"


def _time_share(product: pd.Series, hour: int) -> float:
    # Usa la franja horaria pedida para priorizar productos populares a esa hora.
    if 6 <= hour < 12:
        return float(product["morning_share"])
    if 12 <= hour < 18:
        return float(product["afternoon_share"])
    return float(product["evening_share"])


def _build_catalog(store_id: int | None) -> tuple[pd.DataFrame, str]:
    # Carga el mismo CSV que usa el resto del backend.
    full = load_dataset()
    available_stores = set(full["store_id"].dropna().unique())

    if store_id is not None and store_id not in available_stores:
        raise SelectionError(f"La tienda {store_id} no existe.")

    df = full.copy() if store_id is None else full[full["store_id"] == store_id].copy()
    if df.empty:
        raise SelectionError("La tienda seleccionada no tiene transacciones.")

    store_location = (
        "Todas las tiendas"
        if store_id is None
        else str(df["store_location"].iloc[0])
    )

    # Solo trabajamos con productos que se pueden recomendar como café o bebida.
    df = df[df["product_category"].isin(RECOMMENDABLE_CATEGORIES)].copy()
    if df.empty:
        raise AnalysisError("No hay productos recomendables en el catálogo.")

    # Normaliza cantidades y extrae la hora para calcular participación por franja.
    df["transaction_qty"] = pd.to_numeric(df["transaction_qty"], errors="coerce").fillna(0)
    df["hour"] = pd.to_datetime(
        df["transaction_time"], format="%H:%M:%S", errors="coerce"
    ).dt.hour
    df["is_morning"] = df["hour"].between(6, 11)
    df["is_afternoon"] = df["hour"].between(12, 17)
    df["is_evening"] = df["hour"].between(18, 23)
    df["is_weekend"] = df["transaction_date"].dt.dayofweek.isin([5, 6])

    # Agrupa por producto para obtener precio, popularidad y hábitos horarios.
    catalog = (
        df.groupby(
            [
                "product_id",
                "product_category",
                "product_type",
                "product_detail",
            ],
            dropna=False,
        )
        .agg(
            mean_price=("unit_price", "mean"),
            units_sold=("transaction_qty", "sum"),
            ticket_count=("transaction_id", "count"),
            morning_count=("is_morning", "sum"),
            afternoon_count=("is_afternoon", "sum"),
            evening_count=("is_evening", "sum"),
            weekend_count=("is_weekend", "sum"),
        )
        .reset_index()
    )

    # Convierte los conteos en proporciones para que sean comparables.
    safe_tickets = catalog["ticket_count"].replace(0, np.nan)
    catalog["morning_share"] = catalog["morning_count"] / safe_tickets
    catalog["afternoon_share"] = catalog["afternoon_count"] / safe_tickets
    catalog["evening_share"] = catalog["evening_count"] / safe_tickets
    catalog["weekend_share"] = catalog["weekend_count"] / safe_tickets
    catalog["units_per_ticket"] = catalog["units_sold"] / safe_tickets

    # Limpia filas sin datos suficientes para construir un vector.
    catalog["base_name"] = catalog["product_detail"].map(_extract_base_name)
    catalog["size"] = catalog["product_detail"].map(_extract_size)
    catalog["popularity"] = catalog["units_sold"].fillna(0)
    catalog = catalog.dropna(subset=["mean_price", "units_per_ticket"])
    catalog = catalog[catalog["ticket_count"] > 0].copy()
    catalog = catalog.fillna(
        {
            "morning_share": 0.0,
            "afternoon_share": 0.0,
            "evening_share": 0.0,
            "weekend_share": 0.0,
            "units_per_ticket": 0.0,
        }
    )

    if catalog.empty:
        raise AnalysisError("No hay productos con datos suficientes para recomendar.")

    catalog = catalog.sort_values(
        ["product_category", "product_type", "product_detail"]
    ).reset_index(drop=True)

    return catalog, store_location


@lru_cache(maxsize=8)
def _get_model(store_id: int | None) -> RecommendationModel:
    # El catálogo es estático; se cachea el modelo por tienda.
    catalog, store_location = _build_catalog(store_id)

    if len(catalog) < 2:
        raise AnalysisError("Se necesitan al menos dos productos para recomendar.")

    # One-hot para categorías y escalado para precios/popularidad.
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            ),
            ("numeric", StandardScaler(), NUMERIC_FEATURES),
        ]
    )
    matrix = np.asarray(preprocessor.fit_transform(catalog), dtype=float)

    # La distancia coseno mide qué tan parecidos son los vectores de producto.
    neighbors = NearestNeighbors(
        n_neighbors=min(10, len(catalog)),
        metric="cosine",
    )
    neighbors.fit(matrix)

    return RecommendationModel(
        store_id=store_id,
        store_location=store_location,
        products=catalog,
        matrix=matrix,
        neighbors=neighbors,
    )


def _candidate_mask(
    products: pd.DataFrame,
    category: str | None,
    product_type: str | None,
    max_price: float | None,
) -> pd.Series:
    # Filtra el catálogo sin modificar la matriz original del KNN.
    mask = pd.Series(True, index=products.index)
    if category:
        mask &= products["product_category"].eq(category)
    if product_type:
        mask &= products["product_type"].eq(product_type)
    if max_price is not None:
        mask &= products["mean_price"].le(max_price)
    return mask


def _normalize_filter(value: str | None) -> str | None:
    # Evita diferencias por espacios accidentales desde el frontend.
    if value is None:
        return None
    clean = value.strip()
    return clean or None


def _recommendation_payload(
    product: pd.Series,
    similarity: float | None,
    reason: str,
    hour: int,
) -> dict:
    # Convierte la fila de pandas a un JSON simple para FastAPI.
    return {
        "product_id": int(product["product_id"]),
        "name": str(product["product_detail"]),
        "base_name": str(product["base_name"]),
        "category": str(product["product_category"]),
        "product_type": str(product["product_type"]),
        "size": str(product["size"]),
        "price": round(float(product["mean_price"]), 2),
        "popularity": int(product["popularity"]),
        "units_per_ticket": round(float(product["units_per_ticket"]), 3),
        "time_share": round(_time_share(product, hour), 4),
        "similarity": (
            None if similarity is None else round(float(similarity), 4)
        ),
        "reason": reason,
    }


def get_coffee_options(store_id: int | None = None) -> dict:
    # Devuelve categorías, tipos y productos para llenar el formulario.
    model = _get_model(store_id)
    products = model.products

    types_by_category = {
        str(category): sorted(
            str(value)
            for value in products.loc[
                products["product_category"] == category, "product_type"
            ].unique()
        )
        for category in RECOMMENDABLE_CATEGORIES
        if (products["product_category"] == category).any()
    }

    price_min = float(products["mean_price"].min())
    price_max = float(products["mean_price"].max())

    return {
        "store_id": store_id,
        "store_location": model.store_location,
        "categories": [
            category
            for category in RECOMMENDABLE_CATEGORIES
            if (products["product_category"] == category).any()
        ],
        "types_by_category": types_by_category,
        "price_range": {
            "min": round(price_min, 2),
            "max": round(price_max, 2),
        },
        "products": [
            {
                "product_id": int(row.product_id),
                "name": str(row.product_detail),
                "category": str(row.product_category),
                "product_type": str(row.product_type),
                "size": str(row.size),
                "price": round(float(row.mean_price), 2),
            }
            for row in products.itertuples()
        ],
    }


def recommend_coffees(
    store_id: int | None = None,
    hour: int = 8,
    category: str | None = None,
    product_type: str | None = None,
    max_price: float | None = None,
    seed_product_id: int | None = None,
    top_k: int = 5,
) -> dict:
    # Valida la entrada antes de construir o consultar el modelo.
    if not 0 <= hour <= 23:
        raise SelectionError("La hora debe estar entre 0 y 23.")
    if not 1 <= top_k <= 20:
        raise SelectionError("top_k debe estar entre 1 y 20.")
    if max_price is not None and max_price < 0:
        raise SelectionError("El precio máximo no puede ser negativo.")

    category = _normalize_filter(category)
    product_type = _normalize_filter(product_type)
    model = _get_model(store_id)
    products = model.products

    if category and category not in set(products["product_category"]):
        raise SelectionError(f"La categoría '{category}' no está disponible.")
    if product_type and product_type not in set(products["product_type"]):
        raise SelectionError(f"El tipo '{product_type}' no está disponible.")

    mask = _candidate_mask(products, category, product_type, max_price)
    if not mask.any():
        raise SelectionError("No hay productos que cumplan los filtros elegidos.")

    # Calcula cuántos vecinos revisar para poder descartar duplicados por tamaño.
    search_k = min(max(top_k * 4, top_k + 10), len(products))
    scored: list[tuple[pd.Series, float | None]] = []

    if seed_product_id is not None:
        # Estrategia 1: recomendar productos parecidos a uno ya conocido.
        seed_indices = products.index[
            products["product_id"].eq(seed_product_id)
        ].tolist()
        if not seed_indices:
            raise SelectionError(
                f"El producto {seed_product_id} no está en el catálogo de la tienda."
            )

        seed_index = int(seed_indices[0])
        seed_product = products.iloc[seed_index]
        distances, indices = model.neighbors.kneighbors(
            model.matrix[seed_index : seed_index + 1],
            n_neighbors=search_k,
        )

        for distance, index in zip(distances[0], indices[0]):
            index = int(index)
            if index == seed_index or not bool(mask.iloc[index]):
                continue
            candidate = products.iloc[index]
            if candidate["base_name"] == seed_product["base_name"]:
                continue
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            scored.append((candidate, similarity))

        strategy = "seed"
        reason = f"Similar a {seed_product['product_detail']}"

    elif category or product_type or max_price is not None:
        # Estrategia 2: promediar los productos que cumplen la preferencia.
        profile_vector = model.matrix[mask.to_numpy()].mean(axis=0).reshape(1, -1)
        distances, indices = model.neighbors.kneighbors(
            profile_vector,
            n_neighbors=search_k,
        )

        for distance, index in zip(distances[0], indices[0]):
            index = int(index)
            if not bool(mask.iloc[index]):
                continue
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            scored.append((products.iloc[index], similarity))

        strategy = "preferences"
        reason = "Coincide con tu preferencia"

    else:
        # Estrategia 3: cliente nuevo sin preferencia; usar popularidad y hora.
        ranked = products.loc[mask].copy()
        ranked["time_share"] = ranked.apply(
            lambda row: _time_share(row, hour), axis=1
        )
        ranked["popularity_score"] = ranked["popularity"] * (
            0.25 + ranked["time_share"]
        )
        ranked = ranked.sort_values(
            ["popularity_score", "popularity"], ascending=False
        )

        scored = [(row, None) for _, row in ranked.iterrows()]
        strategy = "popular"
        reason = "Popular en esta franja"

    # Evita repetir el mismo café base en distintos tamaños.
    recommendations = []
    seen_base_names: set[str] = set()
    for product, similarity in scored:
        base_name = str(product["base_name"])
        if base_name in seen_base_names:
            continue
        seen_base_names.add(base_name)
        recommendations.append(
            _recommendation_payload(product, similarity, reason, hour)
        )
        if len(recommendations) >= top_k:
            break

    if not recommendations:
        raise SelectionError("No se encontraron recomendaciones con esos filtros.")

    return {
        "store_id": store_id,
        "store_location": model.store_location,
        "hour": hour,
        "strategy": strategy,
        "filters": {
            "category": category,
            "product_type": product_type,
            "max_price": max_price,
            "seed_product_id": seed_product_id,
        },
        "catalog_size": int(len(products)),
        "model": {
            "name": "KNN content-based",
            "metric": "cosine",
            "k": top_k,
            "features": CATEGORICAL_FEATURES + NUMERIC_FEATURES,
        },
        "recommendations": recommendations,
    }
