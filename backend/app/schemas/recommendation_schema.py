from typing import Literal

from pydantic import BaseModel, Field

# Entrada del recomendador KNN
class CoffeeRecommendationRequest(BaseModel):
    store_id: int | None = Field(
        default=3,
        ge=1,
        description="ID de tienda; None para considerar todas las tiendas",
    )
    hour: int = Field(
        default=8,
        ge=0,
        le=23,
        description="Hora del día usada para priorizar productos populares",
    )
    category: str | None = Field(
        default=None,
        description="Categoría del producto, por ejemplo Coffee o Tea",
    )
    product_type: str | None = Field(
        default=None,
        description="Tipo de café o bebida, por ejemplo Barista Espresso",
    )
    max_price: float | None = Field(
        default=None,
        ge=0,
        description="Precio máximo permitido para una recomendación",
    )
    seed_product_id: int | None = Field(
        default=None,
        ge=1,
        description="Producto de referencia para buscar cafés similares",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Cantidad de recomendaciones a devolver",
    )


# Información del modelo que se muestra en la respuesta
class RecommendationModelInfo(BaseModel):
    name: str
    metric: str
    k: int
    features: list[str]


# Filtros que se aplicaron a la recomendación
class RecommendationFilters(BaseModel):
    category: str | None
    product_type: str | None
    max_price: float | None
    seed_product_id: int | None


# Un producto recomendado
class CoffeeRecommendation(BaseModel):
    product_id: int
    name: str
    base_name: str
    category: str
    product_type: str
    size: str
    price: float
    popularity: int
    units_per_ticket: float
    time_share: float
    similarity: float | None
    reason: str


# Respuesta del endpoint de recomendación
class CoffeeRecommendationResponse(BaseModel):
    store_id: int | None
    store_location: str
    hour: int
    strategy: Literal["seed", "preferences", "popular"]
    filters: RecommendationFilters
    catalog_size: int
    model: RecommendationModelInfo
    recommendations: list[CoffeeRecommendation]


# Un producto disponible para el formulario
class CoffeeOptionProduct(BaseModel):
    product_id: int
    name: str
    category: str
    product_type: str
    size: str
    price: float


# Rango de precios del catálogo
class CoffeePriceRange(BaseModel):
    min: float
    max: float


# Opciones para llenar categorías, tipos y productos del formulario
class CoffeeOptionsResponse(BaseModel):
    store_id: int | None
    store_location: str
    categories: list[str]
    types_by_category: dict[str, list[str]]
    price_range: CoffeePriceRange
    products: list[CoffeeOptionProduct]
