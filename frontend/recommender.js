const API_BASE = "https://starbucks-prediction-1.onrender.com";
const STORE_LABELS = {
  3: "Tienda San Isidro",
  5: "Lower Manhattan",
  8: "Hell's Kitchen",
};

const CATEGORY_LABELS = {
  Coffee: "Café",
  "Coffee beans": "Café en grano",
  Tea: "Té",
  "Drinking Chocolate": "Chocolate",
};

const CATEGORY_HINTS = {
  Coffee: "Espresso, latte, filtrado",
  "Coffee beans": "Para llevar a casa",
  Tea: "Negro, verde, chai",
  "Drinking Chocolate": "Chocolate caliente",
};

const TYPE_LABELS = {
  "Barista Espresso": "Espresso y leche",
  "Drip coffee": "Café filtrado",
  "Gourmet brewed coffee": "Café gourmet",
  "Organic brewed coffee": "Café orgánico",
  "Premium brewed coffee": "Café premium",
  "Espresso Beans": "Granos espresso",
  "Gourmet Beans": "Granos gourmet",
  "Green beans": "Granos verdes",
  "House blend Beans": "Mezcla de la casa",
  "Organic Beans": "Granos orgánicos",
  "Premium Beans": "Granos premium",
  "Brewed Black tea": "Té negro",
  "Brewed Chai tea": "Té chai",
  "Brewed Green tea": "Té verde",
  "Brewed herbal tea": "Té herbal",
  "Hot chocolate": "Chocolate caliente",
};

const HOUR_LABELS = {
  8: "Mañana",
  14: "Tarde",
  19: "Noche",
};

const params = new URLSearchParams(window.location.search);
const storeId = Number(params.get("store_id")) || 3;
const storeLabel = STORE_LABELS[storeId] || `Tienda ${storeId}`;

const form = document.querySelector("#rec-form");
const categoriesEl = document.querySelector("#rec-categories");
const typeSelect = document.querySelector("#rec-type");
const hourSelect = document.querySelector("#rec-hour");
const budgetInput = document.querySelector("#rec-budget");
const seedSelect = document.querySelector("#rec-seed");
const submitButton = document.querySelector("#rec-submit");
const resultsEl = document.querySelector("#rec-results");
const storeEl = document.querySelector("#rec-store");

let options = null;
let selectedCategory = "";
let busy = false;
let requestSerial = 0;

// Crea nodos con clase y texto sin usar innerHTML.
function el(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = text;
  return node;
}

function categoryLabel(value) {
  return CATEGORY_LABELS[value] || value;
}

function typeLabel(value) {
  return TYPE_LABELS[value] || value;
}

function hourLabel(value) {
  return HOUR_LABELS[value] || `${value}:00`;
}

function formatPrice(value) {
  return `$${Number(value).toFixed(2)}`;
}

function formatNumber(value) {
  return Number(value).toLocaleString("es-PE");
}

function errorMessage(payload, fallback) {
  if (payload && typeof payload.detail === "string") return payload.detail;
  if (payload && Array.isArray(payload.detail)) {
    const messages = payload.detail.map((item) => item.msg).filter(Boolean);
    if (messages.length) return messages.join(" ");
  }
  return fallback;
}

function setDefaultHour() {
  const currentHour = new Date().getHours();
  hourSelect.value = currentHour < 12 ? "8" : currentHour < 18 ? "14" : "19";
}

function setBusy(isBusy) {
  busy = isBusy;
  submitButton.disabled = isBusy || !options;
  submitButton.textContent = isBusy ? "Buscando cafés…" : "Recomendar cafés";
  form.setAttribute("aria-busy", String(isBusy));
  resultsEl.setAttribute("aria-busy", String(isBusy));
}

function updateCategoryButtons() {
  for (const button of categoriesEl.querySelectorAll(".rec-choice")) {
    button.setAttribute("aria-pressed", String(button.dataset.category === selectedCategory));
  }
}

function renderTypeOptions() {
  typeSelect.replaceChildren(new Option("Cualquiera", ""));

  if (!selectedCategory || !options) {
    typeSelect.disabled = true;
    return;
  }

  typeSelect.disabled = false;
  const types = options.types_by_category[selectedCategory] || [];
  for (const type of types) {
    typeSelect.append(new Option(typeLabel(type), type));
  }
}

function selectCategory(value) {
  selectedCategory = value;
  seedSelect.value = "";
  updateCategoryButtons();
  renderTypeOptions();
}

function renderCategories() {
  if (!options) return;

  const choices = [
    {
      value: "",
      label: "No sé, sorpréndeme",
      hint: "Lo más pedido de la tienda",
    },
    ...options.categories.map((category) => ({
      value: category,
      label: categoryLabel(category),
      hint: CATEGORY_HINTS[category] || "Opciones disponibles",
    })),
  ];

  const buttons = choices.map((choice) => {
    const button = el("button", "rec-choice");
    button.type = "button";
    button.dataset.category = choice.value;
    button.setAttribute("aria-pressed", String(choice.value === selectedCategory));
    button.append(
      el("span", "rec-choice-label", choice.label),
      el("span", "rec-choice-hint", choice.hint),
    );
    button.addEventListener("click", () => selectCategory(choice.value));
    return button;
  });

  categoriesEl.replaceChildren(...buttons);
}

function renderSeedOptions() {
  seedSelect.replaceChildren(new Option("Ninguno", ""));

  if (!options) return;

  for (const product of options.products) {
    const label = `${product.name} · ${typeLabel(product.product_type)} · ${formatPrice(product.price)}`;
    seedSelect.append(new Option(label, String(product.product_id)));
  }
}

function showLoading() {
  const box = el("div", "rec-loading-box");
  const spinner = el("span", "rec-spinner");
  spinner.setAttribute("aria-hidden", "true");
  box.append(spinner, el("p", "", "Buscando cafés parecidos…"));
  resultsEl.replaceChildren(box);
}

function showError(message) {
  const box = el("div", "rec-error");
  box.setAttribute("role", "alert");
  box.append(
    el("strong", "", "No pudimos obtener recomendaciones."),
    el("p", "", message),
  );
  resultsEl.replaceChildren(box);
}

function renderCard(item, index) {
  const card = el("article", "rec-card");
  const top = el("div", "rec-card-top");
  top.append(
    el("span", "rec-rank", String(index + 1).padStart(2, "0")),
    el("span", "rec-badge", item.similarity == null ? "Popular" : "Recomendado"),
  );

  const metaParts = [categoryLabel(item.category), typeLabel(item.product_type)];
  if (item.size && item.size !== "Único") metaParts.push(item.size);

  card.append(
    top,
    el("h3", "rec-name", item.name),
    el("p", "rec-meta", metaParts.join(" · ")),
    el("p", "rec-price", formatPrice(item.price)),
    el("p", "rec-reason", item.reason),
  );

  if (item.similarity != null) {
    const percent = Math.max(0, Math.min(100, Math.round(item.similarity * 100)));
    const box = el("div", "rec-similarity");
    const row = el("div", "rec-similarity-row");
    row.append(el("span", "", "Similitud"), el("strong", "", `${percent}%`));

    const bar = el("div", "rec-bar");
    const fill = el("i");
    fill.style.width = `${percent}%`;
    bar.append(fill);
    box.append(row, bar);
    card.append(box);
  } else {
    card.append(el("p", "rec-popular", "Sugerencia por popularidad"));
  }

  card.append(el("p", "rec-popularity", `${formatNumber(item.popularity)} unidades vendidas`));
  return card;
}

function resetRecommender() {
  selectedCategory = "";
  budgetInput.value = "";
  seedSelect.value = "";
  updateCategoryButtons();
  renderTypeOptions();
  resultsEl.replaceChildren(
    el("p", "rec-empty", "Elegí una opción y tocá «Recomendar cafés» para ver sugerencias."),
  );
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderRecommendations(payload) {
  if (!payload || !Array.isArray(payload.recommendations)) {
    throw new Error("El recomendador devolvió una respuesta inesperada.");
  }

  if (!payload.recommendations.length) {
    showError("No encontramos cafés con esos filtros. Probá con otra preferencia.");
    return;
  }

  const titles = {
    seed: "Parecidos a tu elección",
    preferences: "Elegidos para tu preferencia",
    popular: "Los más pedidos en esta franja",
  };

  const header = el("div", "rec-results-head");
  const copy = el("div");
  copy.append(
    el("h2", "", titles[payload.strategy] || "Recomendaciones para vos"),
    el(
      "p",
      "",
      `${storeLabel} · ${hourLabel(payload.hour)} · ${payload.recommendations.length} opciones`,
    ),
  );
  header.append(copy);

  const grid = el("div", "rec-grid");
  payload.recommendations.forEach((item, index) => grid.append(renderCard(item, index)));

  const reset = el("button", "rec-reset", "Volver a empezar");
  reset.type = "button";
  reset.addEventListener("click", resetRecommender);

  resultsEl.replaceChildren(header, grid, reset);
}

function readForm() {
  const rawBudget = budgetInput.value.trim();
  const budget = rawBudget === "" ? null : Number(rawBudget);
  const maxPrice = budget != null && Number.isFinite(budget) && budget >= 0 ? budget : null;

  return {
    store_id: storeId,
    hour: Number(hourSelect.value),
    category: selectedCategory || null,
    product_type: typeSelect.value || null,
    max_price: maxPrice,
    seed_product_id: seedSelect.value ? Number(seedSelect.value) : null,
    top_k: 5,
  };
}

async function loadOptions() {
  try {
    const response = await fetch(`${API_BASE}/api/coffee-options?store_id=${storeId}`); // Agregada la API v2
    const payload = await response.json().catch(() => null);

    if (!response.ok) {
      throw new Error(errorMessage(payload, "No se pudo cargar el catálogo."));
    }

    options = payload;
    storeEl.textContent = storeLabel;
    renderCategories();
    renderTypeOptions();
    renderSeedOptions();
    seedSelect.disabled = false;
    setBusy(false);
  } catch (error) {
    submitButton.disabled = true;
    categoriesEl.replaceChildren(
      el("p", "rec-empty", "No se pudieron cargar las opciones."),
    );
    showError(error.message || "No hay conexión con el catálogo.");
  }
}

async function loadRecommendations() {
  if (!options || busy) return;

  const serial = ++requestSerial;
  const body = readForm();
  setBusy(true);
  showLoading();

  try {
    const response = await fetch(`${API_BASE}/api/recommend-coffees`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => null);

    if (serial !== requestSerial) return;
    if (!response.ok) {
      throw new Error(errorMessage(payload, "El recomendador no respondió."));
    }

    renderRecommendations(payload);
  } catch (error) {
    if (serial !== requestSerial) return;
    showError(error.message || "No hay conexión con el recomendador.");
  } finally {
    if (serial === requestSerial) setBusy(false);
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadRecommendations();
});

seedSelect.addEventListener("change", () => {
  if (!seedSelect.value) return;
  selectedCategory = "";
  updateCategoryButtons();
  renderTypeOptions();
});

setDefaultHour();
storeEl.textContent = storeLabel;
seedSelect.disabled = true;
typeSelect.disabled = true;
loadOptions();
