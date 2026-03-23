/* Render functions — return HTML strings */

function renderStats(stats) {
  const bankItems = Object.entries(stats.by_bank || {})
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => `<span>${name}: <strong>${count}</strong></span>`)
    .join("");

  const categoryItems = Object.entries(stats.by_category || {})
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => `<span>${name}: <strong>${count}</strong></span>`)
    .join("");

  return `
    <div class="stat-card">
      <h3>Total Deals</h3>
      <div class="value">${stats.total_deals || 0}</div>
    </div>
    <div class="stat-card">
      <h3>By Bank</h3>
      <div class="value">${Object.keys(stats.by_bank || {}).length}</div>
      <div class="breakdown">${bankItems || "No data"}</div>
    </div>
    <div class="stat-card">
      <h3>By Category</h3>
      <div class="value">${Object.keys(stats.by_category || {}).length}</div>
      <div class="breakdown">${categoryItems || "No data"}</div>
    </div>
  `;
}

function renderDealCard(deal) {
  const badges = [];
  badges.push(`<span class="badge badge-category">${esc(deal.category)}</span>`);
  if (deal.discount_percentage)
    badges.push(`<span class="badge badge-discount">${deal.discount_percentage}% off</span>`);
  if (deal.discount_amount)
    badges.push(`<span class="badge badge-discount">LKR ${deal.discount_amount}</span>`);
  if (deal.merchant_name)
    badges.push(`<span class="badge badge-merchant">${esc(deal.merchant_name)}</span>`);
  if (deal.valid_until)
    badges.push(`<span class="badge badge-validity">Until ${deal.valid_until}</span>`);

  return `
    <article class="deal-card" onclick="showDeal(${deal.id})">
      <div class="bank-name">${esc(deal.bank_name)}</div>
      <div class="title">${esc(deal.promotion_title)}</div>
      <div class="description">${esc(deal.description)}</div>
      <div class="meta">${badges.join("")}</div>
    </article>
  `;
}

function renderDeals(deals) {
  if (!deals.length) return `<div class="no-deals">No deals found</div>`;
  return deals.map(renderDealCard).join("");
}

function renderPagination(page, total, perPage) {
  const totalPages = Math.ceil(total / perPage);
  if (totalPages <= 1) return "";

  const buttons = [];
  buttons.push(`<button ${page <= 1 ? "disabled" : ""} onclick="goToPage(${page - 1})">&laquo;</button>`);

  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, page + 2);

  if (start > 1) buttons.push(`<button onclick="goToPage(1)">1</button>`);
  if (start > 2) buttons.push(`<button disabled>...</button>`);

  for (let i = start; i <= end; i++) {
    buttons.push(`<button class="${i === page ? "active" : ""}" onclick="goToPage(${i})">${i}</button>`);
  }

  if (end < totalPages - 1) buttons.push(`<button disabled>...</button>`);
  if (end < totalPages) buttons.push(`<button onclick="goToPage(${totalPages})">${totalPages}</button>`);

  buttons.push(`<button ${page >= totalPages ? "disabled" : ""} onclick="goToPage(${page + 1})">&raquo;</button>`);
  return buttons.join("");
}

function renderDealModal(deal) {
  const rows = [
    ["Bank", deal.bank_name],
    ["Card", deal.card_name],
    ["Card Types", (deal.card_types || []).join(", ")],
    ["Category", deal.category],
    ["Discount", deal.discount_percentage ? `${deal.discount_percentage}%` : deal.discount_amount ? `LKR ${deal.discount_amount}` : "N/A"],
    ["Max Discount", deal.max_discount_lkr ? `LKR ${deal.max_discount_lkr}` : "N/A"],
    ["Merchant", deal.merchant_name || "N/A"],
    ["Valid From", deal.valid_from || "N/A"],
    ["Valid Until", deal.valid_until || "N/A"],
    ["Valid Days", (deal.valid_days || []).join(", ") || "N/A"],
  ].filter(([, v]) => v && v !== "N/A")
   .map(([label, value]) => `<div class="detail-row"><span class="label">${label}</span><span class="value">${esc(String(value))}</span></div>`)
   .join("");

  const terms = deal.terms_and_conditions
    ? `<div class="terms"><strong>Terms & Conditions:</strong><br>${esc(deal.terms_and_conditions)}</div>`
    : "";

  return `
    <div class="modal-bank">${esc(deal.bank_name)}</div>
    <h2>${esc(deal.promotion_title)}</h2>
    <p style="color:#555;margin-bottom:1rem">${esc(deal.description)}</p>
    ${rows}
    ${terms}
    <a class="source-link" href="${esc(deal.source_url)}" target="_blank" rel="noopener">View source page &rarr;</a>
  `;
}

function populateFilters(stats) {
  const bankSelect = document.getElementById("bank-filter");
  Object.keys(stats.by_bank || {}).sort().forEach(bank => {
    const opt = document.createElement("option");
    opt.value = bank;
    opt.textContent = bank;
    bankSelect.appendChild(opt);
  });

  const catSelect = document.getElementById("category-filter");
  Object.keys(stats.by_category || {}).sort().forEach(cat => {
    const opt = document.createElement("option");
    opt.value = cat;
    opt.textContent = cat;
    catSelect.appendChild(opt);
  });
}

function esc(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
