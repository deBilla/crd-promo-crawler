/* App controller — state management and event wiring */

const state = {
  page: 1,
  perPage: 12,
  bank: "",
  category: "",
  activeOnly: false,
  keyword: "",
};

async function loadStats() {
  const stats = await API.getStats();
  document.getElementById("stats").innerHTML = renderStats(stats);
  populateFilters(stats);
}

async function loadDeals() {
  let data;
  if (state.keyword) {
    data = await API.searchDeals(state.keyword, { page: state.page, per_page: state.perPage });
  } else {
    data = await API.getDeals({
      page: state.page,
      per_page: state.perPage,
      bank_name: state.bank,
      category: state.category,
      active_only: state.activeOnly,
    });
  }
  document.getElementById("deals").innerHTML = renderDeals(data.deals);
  document.getElementById("pagination").innerHTML = renderPagination(data.page, data.total, data.per_page);
}

function goToPage(page) {
  state.page = page;
  loadDeals();
  window.scrollTo({ top: 300, behavior: "smooth" });
}

async function showDeal(id) {
  const deal = await API.getDeal(id);
  document.getElementById("modal-content").innerHTML = renderDealModal(deal);
  document.getElementById("modal-overlay").classList.add("visible");
}

function closeModal() {
  document.getElementById("modal-overlay").classList.remove("visible");
}

// Event listeners
let searchTimeout;
document.getElementById("search-input").addEventListener("input", (e) => {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    state.keyword = e.target.value.trim();
    state.page = 1;
    loadDeals();
  }, 400);
});

document.getElementById("bank-filter").addEventListener("change", (e) => {
  state.bank = e.target.value;
  state.page = 1;
  state.keyword = "";
  document.getElementById("search-input").value = "";
  loadDeals();
});

document.getElementById("category-filter").addEventListener("change", (e) => {
  state.category = e.target.value;
  state.page = 1;
  state.keyword = "";
  document.getElementById("search-input").value = "";
  loadDeals();
});

document.getElementById("active-filter").addEventListener("change", (e) => {
  state.activeOnly = e.target.checked;
  state.page = 1;
  loadDeals();
});

document.getElementById("modal-overlay").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeModal();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeModal();
});

// Init
loadStats();
loadDeals();
