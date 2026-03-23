/* API client — all fetch calls to the backend */

const API = {
  async getStats() {
    const res = await fetch("/deals/stats");
    return res.json();
  },

  async getDeals({ page = 1, per_page = 12, bank_name, category, active_only } = {}) {
    const params = new URLSearchParams({ page, per_page });
    if (bank_name) params.set("bank_name", bank_name);
    if (category) params.set("category", category);
    if (active_only) params.set("active_only", "true");
    const res = await fetch(`/deals?${params}`);
    return res.json();
  },

  async searchDeals(keyword, { page = 1, per_page = 12 } = {}) {
    const params = new URLSearchParams({ keyword, page, per_page });
    const res = await fetch(`/deals/search?${params}`);
    return res.json();
  },

  async getDeal(id) {
    const res = await fetch(`/deals/${id}`);
    return res.json();
  },
};
