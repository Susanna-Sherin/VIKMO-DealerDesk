/**
 * VIKMO DealerDesk — Enterprise Automotive Operations Portal Logic
 * Vanilla JavaScript (ES6+) | No External Dependencies | Live API Integration
 */

(function () {
  "use strict";

  // ---- State & Cache --------------------------------------------------------
  const state = {
    activeTab: "tab-overview",
    dealers: [],
    productsCache: [],
    sessionId: "desk-" + Math.random().toString(36).substring(2, 10),
    catalogue: {
      page: 1,
      pageSize: 15,
      totalCount: 0,
      search: "",
      category: "",
      vehicle: "",
    },
    dealersView: {
      page: 1,
      pageSize: 25,
      totalCount: 0,
      search: "",
    },
    ordersView: {
      page: 1,
      pageSize: 15,
      totalCount: 0,
      status: "",
      dealerId: "",
    },
    forecast: {
      suggestions: [],
    },
  };

  // ---- Helpers & Formatters -------------------------------------------------
  function formatMoney(amount) {
    if (amount === null || amount === undefined || amount === "") return "₹0.00";
    const num = typeof amount === "string" ? parseFloat(amount) : amount;
    if (isNaN(num)) return "₹0.00";
    return "₹" + num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function formatDateTime(isoString) {
    if (!isoString) return "--";
    try {
      const d = new Date(isoString);
      return d.toLocaleString("en-IN", {
        timeZone: "Asia/Kolkata",
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
      }) + " IST";
    } catch {
      return isoString;
    }
  }

  function getStockBadge(qty) {
    const stock = parseInt(qty, 10);
    if (isNaN(stock) || stock <= 0) {
      return '<span class="badge badge-outofstock">Out of Stock</span>';
    }
    if (stock < 15) {
      return `<span class="badge badge-lowstock">Low Stock (${stock})</span>`;
    }
    return `<span class="badge badge-instock">In Stock (${stock})</span>`;
  }

  function getOrderStatusBadge(status) {
    const s = (status || "").toUpperCase();
    switch (s) {
      case "DRAFT":
        return '<span class="badge badge-draft">Draft</span>';
      case "CONFIRMED":
        return '<span class="badge badge-confirmed">Confirmed</span>';
      case "DISPATCHED":
        return '<span class="badge badge-dispatched">Dispatched</span>';
      case "DELIVERED":
        return '<span class="badge badge-delivered">Delivered</span>';
      case "CANCELLED":
        return '<span class="badge badge-cancelled">Cancelled</span>';
      default:
        return `<span class="badge badge-draft">${s}</span>`;
    }
  }

  // ---- Toast Notifications --------------------------------------------------
  function showToast(message, type = "info", duration = 4000) {
    const container = document.getElementById("toastContainer");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
      <span>${escapeHtml(message)}</span>
      <button class="toast-close" aria-label="Dismiss">&times;</button>
    `;

    toast.querySelector(".toast-close").addEventListener("click", () => {
      toast.remove();
    });

    container.appendChild(toast);

    setTimeout(() => {
      if (toast.isConnected) {
        toast.style.opacity = "0";
        toast.style.transform = "translateX(40px)";
        toast.style.transition = "all 0.25s ease-out";
        setTimeout(() => toast.remove(), 250);
      }
    }, duration);
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // ---- API Fetch Client -----------------------------------------------------
  async function apiFetch(endpoint, options = {}) {
    try {
      const resp = await fetch(endpoint, {
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
          ...(options.headers || {}),
        },
        ...options,
      });

      const data = await resp.json().catch(() => ({}));

      if (!resp.ok) {
        let msg = "Request failed";
        if (data && data.error) {
          msg = data.error.message || msg;
          if (data.error.details && data.error.details.length > 0) {
            const detailMsgs = data.error.details.map(d => `${d.field ? d.field + ': ' : ''}${d.message}`).join(", ");
            msg += ` (${detailMsgs})`;
          }
        }
        const err = new Error(msg);
        err.status = resp.status;
        err.data = data;
        throw err;
      }

      return data;
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err);
      throw err;
    }
  }

  // ---- Modals ---------------------------------------------------------------
  function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
      modal.classList.add("open");
    }
  }

  function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
      modal.classList.remove("open");
    }
  }

  function setupModalDismissals() {
    document.querySelectorAll(".modal-overlay").forEach(overlay => {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) {
          overlay.classList.remove("open");
        }
      });
    });

    document.querySelectorAll(".modal-close").forEach(btn => {
      btn.addEventListener("click", () => {
        const modal = btn.closest(".modal-overlay");
        if (modal) modal.classList.remove("open");
      });
    });
  }

  // ---- Tab Navigation -------------------------------------------------------
  function switchTab(tabId) {
    state.activeTab = tabId;

    document.querySelectorAll(".nav-item").forEach(item => {
      if (item.getAttribute("data-tab") === tabId) {
        item.classList.add("active");
      } else {
        item.classList.remove("active");
      }
    });

    document.querySelectorAll(".tab-pane").forEach(pane => {
      if (pane.id === tabId) {
        pane.classList.add("active");
      } else {
        pane.classList.remove("active");
      }
    });

    // Update Header Headings
    const headings = {
      "tab-overview": { title: "Operations Overview", sub: "Real-time distributor operations and warehouse indicators" },
      "tab-catalogue": { title: "Catalogue & Warehouse Stock", sub: "Manage 600 SKUs, vehicle fitments, and stock reconciliations" },
      "tab-dealers": { title: "Authorized Dealers Directory", sub: "Manage 25 South India partner dealerships and credit limits" },
      "tab-orders": { title: "Orders & Fulfillment Pipeline", sub: "Review draft orders, confirm stock allocations, and track lifecycle" },
      "tab-assistant": { title: "AI Operations Assistant", sub: "Conversational dealer ordering, catalogue lookup, and inventory assistant" },
      "tab-forecast": { title: "Demand Forecasting & Reorders", sub: "4-week demand predictions and automated supplier reorder quantities" },
    };

    const h = headings[tabId] || headings["tab-overview"];
    document.getElementById("pageHeading").textContent = h.title;
    document.getElementById("pageSubheading").textContent = h.sub;

    // Trigger tab-specific refresh
    refreshCurrentTab();

    // Close mobile sidebar if open
    const sidebar = document.getElementById("sidebar");
    if (sidebar) sidebar.classList.remove("open");
  }

  function refreshCurrentTab() {
    switch (state.activeTab) {
      case "tab-overview":
        loadOverviewData();
        break;
      case "tab-catalogue":
        loadCatalogueData();
        break;
      case "tab-dealers":
        loadDealersData();
        break;
      case "tab-orders":
        loadOrdersData();
        break;
      case "tab-assistant":
        // assistant is interactive
        break;
      case "tab-forecast":
        loadForecastData();
        break;
    }
  }

  // ---- System Health & Live Clock -------------------------------------------
  async function checkSystemHealth() {
    const dot = document.getElementById("systemHealthDot");
    const text = document.getElementById("systemHealthText");
    try {
      const data = await apiFetch("/api/health/");
      if (data.status === "ok") {
        dot.className = "status-dot";
        text.textContent = "API & DB Connected";
      } else {
        dot.className = "status-dot error";
        text.textContent = "API Status Degraded";
      }
    } catch {
      dot.className = "status-dot error";
      text.textContent = "API Connection Error";
    }
  }

  function startLiveClock() {
    const clock = document.getElementById("liveClock");
    function update() {
      const now = new Date();
      clock.textContent = now.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour12: false }) + " IST";
    }
    update();
    setInterval(update, 1000);
  }

  // ---- Overview (Dashboard) -------------------------------------------------
  async function loadOverviewData() {
    try {
      // 1. Products count
      apiFetch("/api/products/?page=1&page_size=1").then(data => {
        document.getElementById("statTotalSkus").textContent = (data.count || 0).toLocaleString();
      }).catch(() => { });

      // 2. Dealers count
      apiFetch("/api/dealers/?page=1&page_size=1").then(data => {
        document.getElementById("statTotalDealers").textContent = (data.count || 0).toLocaleString();
      }).catch(() => { });

      // 3. Orders count & recent orders
      apiFetch("/api/orders/?page=1&page_size=5").then(data => {
        document.getElementById("statTotalOrders").textContent = (data.count || 0).toLocaleString();
        renderDashboardOrders(data.results || []);
      }).catch(err => {
        document.getElementById("dashboardOrdersBody").innerHTML = `
          <tr><td colspan="5" class="empty-state"><span class="empty-desc">Failed to load recent orders.</span></td></tr>
        `;
      });

      // 4. Reorder suggestions
      apiFetch("/api/reorder-suggestions/").then(data => {
        const list = data.results || data.suggestions || [];
        const urgent = list.filter(s => (s.reorder_qty || 0) > 0);
        document.getElementById("statReorderCount").textContent = urgent.length.toLocaleString();
        document.getElementById("statReorderSubtext").textContent = `${urgent.length} of ${list.length} SKUs below reorder point`;
        const badge = document.getElementById("reorderBadge");
        if (badge) {
          if (urgent.length > 0) {
            badge.textContent = urgent.length;
            badge.style.display = "inline-block";
          } else {
            badge.style.display = "none";
          }
        }
        renderDashboardReorders(urgent.length > 0 ? urgent.slice(0, 6) : list.slice(0, 6));
      }).catch(err => {
        document.getElementById("dashboardReorderBody").innerHTML = `
          <tr><td colspan="6" class="empty-state"><span class="empty-desc">Failed to load reorder suggestions.</span></td></tr>
        `;
      });
    } catch (e) {
      console.error("Overview error:", e);
    }
  }

  function renderDashboardOrders(orders) {
    const tbody = document.getElementById("dashboardOrdersBody");
    if (!orders || orders.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state"><span class="empty-desc">No orders placed yet. Create your first draft order.</span></td></tr>`;
      return;
    }

    tbody.innerHTML = orders.map(o => `
      <tr>
        <td>
          <a href="#" class="order-link sku-badge" data-orderno="${escapeHtml(o.order_number)}">${escapeHtml(o.order_number)}</a>
        </td>
        <td>
          <div style="font-weight:600;">${escapeHtml(o.dealer_name || "Dealer #" + o.dealer_id)}</div>
          <div style="font-size:0.75rem; color:var(--text-muted);">${escapeHtml(o.dealer_code || "")}</div>
        </td>
        <td>${getOrderStatusBadge(o.status)}</td>
        <td class="tabular-nums" style="font-weight:700;">${formatMoney(o.grand_total)}</td>
        <td style="font-size:0.78rem; color:var(--text-dim);">${formatDateTime(o.created_at)}</td>
      </tr>
    `).join("");

    tbody.querySelectorAll(".order-link").forEach(a => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        openOrderDetail(a.getAttribute("data-orderno"));
      });
    });
  }

  function renderDashboardReorders(suggestions) {
    const tbody = document.getElementById("dashboardReorderBody");
    if (!suggestions || suggestions.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-state"><span class="empty-desc">Warehouse stock levels are healthy. No urgent reorders required.</span></td></tr>`;
      return;
    }

    tbody.innerHTML = suggestions.map(s => {
      const reorderQty = s.reorder_qty !== undefined ? s.reorder_qty : (s.suggested_reorder_qty || 0);
      const demand = s.lead_time_demand !== undefined ? s.lead_time_demand : (s.forecasted_demand_4w || "--");
      const name = s.product_name || s.name || s.sku;
      return `
        <tr>
          <td><span class="sku-badge">${escapeHtml(s.sku)}</span></td>
          <td>
            <div style="font-weight:600; max-width:220px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(name)}</div>
          </td>
          <td>${getStockBadge(s.current_stock)}</td>
          <td class="tabular-nums">${demand} units</td>
          <td class="tabular-nums" style="color:var(--color-warning); font-weight:700;">
            ${reorderQty > 0 ? '+' + reorderQty : 'Optimal'}
          </td>
          <td>
            <button class="btn btn-secondary btn-sm btn-quick-reorder" data-sku="${escapeHtml(s.sku)}" data-qty="${reorderQty > 0 ? reorderQty : 10}">
              Draft Order
            </button>
          </td>
        </tr>
      `;
    }).join("");

    tbody.querySelectorAll(".btn-quick-reorder").forEach(btn => {
      btn.addEventListener("click", () => {
        const sku = btn.getAttribute("data-sku");
        const qty = parseInt(btn.getAttribute("data-qty"), 10) || 5;
        openCreateOrderModalWithItem(sku, qty);
      });
    });
  }

  // ---- Product Catalogue & Inventory ----------------------------------------
  async function loadCatalogueData() {
    const tbody = document.getElementById("catalogueTableBody");
    tbody.innerHTML = `
      <tr>
        <td colspan="9" class="loading-state">
          <div class="spinner"></div>
          <span>Loading products from catalogue...</span>
        </td>
      </tr>
    `;

    const { page, pageSize, search, category, vehicle } = state.catalogue;
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });

    if (search.trim()) params.append("search", search.trim());
    if (category) params.append("category", category);
    if (vehicle.trim()) params.append("vehicle", vehicle.trim());

    try {
      const data = await apiFetch(`/api/products/?${params.toString()}`);
      state.catalogue.totalCount = data.count || 0;
      renderCatalogueTable(data.results || []);
      renderCataloguePagination(data);
    } catch (err) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" class="empty-state">
            <span class="empty-title">Failed to load catalogue</span>
            <span class="empty-desc">${escapeHtml(err.message)}</span>
            <button class="btn btn-secondary btn-sm" id="btnRetryCatalogue" style="margin-top:10px;">Retry</button>
          </td>
        </tr>
      `;
      const retry = document.getElementById("btnRetryCatalogue");
      if (retry) retry.addEventListener("click", loadCatalogueData);
    }
  }

  function renderCatalogueTable(products) {
    const tbody = document.getElementById("catalogueTableBody");
    if (!products || products.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" class="empty-state">
            <span class="empty-icon">🔍</span>
            <span class="empty-title">No matching products</span>
            <span class="empty-desc">Try clearing search terms or category filters.</span>
          </td>
        </tr>
      `;
      return;
    }

    // Cache products for order builder lookup
    products.forEach(p => {
      if (!state.productsCache.some(existing => existing.sku === p.sku)) {
        state.productsCache.push(p);
      }
    });

    tbody.innerHTML = products.map(p => `
      <tr>
        <td><span class="sku-badge">${escapeHtml(p.sku)}</span></td>
        <td>
          <div style="font-weight:600; color:#fff;">${escapeHtml(p.name)}</div>
          <div style="font-size:0.75rem; color:var(--text-muted);">${escapeHtml(p.description || "")}</div>
        </td>
        <td>${escapeHtml(p.category || "--")}</td>
        <td>${escapeHtml(p.brand || "--")}</td>
        <td style="font-size:0.8rem; color:var(--text-dim);">${escapeHtml(p.vehicle_fitment || "--")}</td>
        <td class="tabular-nums" style="font-weight:700;">${formatMoney(p.price)}</td>
        <td class="tabular-nums">${p.stock !== undefined ? p.stock : "--"}</td>
        <td>${getStockBadge(p.stock)}</td>
        <td>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-secondary btn-sm btn-edit-stock" data-sku="${escapeHtml(p.sku)}" data-name="${escapeHtml(p.name)}" data-stock="${p.stock || 0}">
              Stock
            </button>
          </div>
        </td>
      </tr>
    `).join("");

    tbody.querySelectorAll(".btn-edit-stock").forEach(btn => {
      btn.addEventListener("click", () => {
        const sku = btn.getAttribute("data-sku");
        const name = btn.getAttribute("data-name");
        const stock = btn.getAttribute("data-stock");
        openInventoryModal(sku, name, stock);
      });
    });
  }

  function renderCataloguePagination(data) {
    const { page, pageSize, totalCount } = state.catalogue;
    const totalPages = Math.ceil(totalCount / pageSize) || 1;

    document.getElementById("cataloguePageInfo").textContent = `Page ${page} of ${totalPages} (${totalCount} total products)`;
    document.getElementById("btnCataloguePrev").disabled = !data.previous || page <= 1;
    document.getElementById("btnCatalogueNext").disabled = !data.next || page >= totalPages;
    document.getElementById("catalogueCountSummary").textContent = `Showing page ${page} of ${totalPages}`;
  }

  function openInventoryModal(sku, productName, currentStock) {
    document.getElementById("inventoryModalSku").textContent = sku;
    document.getElementById("inventoryModalProductName").textContent = productName;
    document.getElementById("inventoryQuantityInput").value = currentStock;
    document.getElementById("inventoryReasonInput").value = "Physical inventory reconciliation";
    openModal("modalInventoryUpdate");
  }

  async function submitInventoryUpdate() {
    const sku = document.getElementById("inventoryModalSku").textContent.trim();
    const quantity = parseInt(document.getElementById("inventoryQuantityInput").value, 10);
    const reason = document.getElementById("inventoryReasonInput").value.trim() || "Stock adjustment";

    if (isNaN(quantity) || quantity < 0) {
      showToast("Quantity must be a non-negative integer.", "error");
      return;
    }

    const submitBtn = document.getElementById("btnSubmitInventoryUpdate");
    submitBtn.disabled = true;
    submitBtn.textContent = "Updating...";

    try {
      await apiFetch(`/api/inventory/${encodeURIComponent(sku)}/`, {
        method: "PUT",
        body: JSON.stringify({ quantity, reason }),
      });
      showToast(`Stock updated for ${sku} (${quantity} units)`, "success");
      closeModal("modalInventoryUpdate");
      loadCatalogueData();
      loadOverviewData();
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Save Stock Count";
    }
  }

  // ---- Dealers Directory ----------------------------------------------------
  async function loadDealersData() {
    const tbody = document.getElementById("dealersTableBody");
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="loading-state">
          <div class="spinner"></div>
          <span>Loading dealers from network...</span>
        </td>
      </tr>
    `;

    try {
      const data = await apiFetch(`/api/dealers/?page=1&page_size=100`);
      state.dealers = data.results || [];
      populateDealerDropdowns(state.dealers);
      renderDealersTable(state.dealers);
    } catch (err) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5" class="empty-state">
            <span class="empty-title">Failed to load dealers</span>
            <span class="empty-desc">${escapeHtml(err.message)}</span>
          </td>
        </tr>
      `;
    }
  }

  function populateDealerDropdowns(dealers) {
    // 1. Order builder dropdown
    const orderSelect = document.getElementById("orderFormDealer");
    if (orderSelect) {
      const currentVal = orderSelect.value;
      orderSelect.innerHTML = `<option value="">-- Choose Authorized Dealer --</option>` +
        dealers.map(d => `<option value="${d.id}">${escapeHtml(d.name)} (${escapeHtml(d.dealer_code)} - ${escapeHtml(d.city)})</option>`).join("");
      if (currentVal) orderSelect.value = currentVal;
    }

    // 2. Orders filter dropdown
    const filterSelect = document.getElementById("orderDealerFilter");
    if (filterSelect) {
      const currentVal = filterSelect.value;
      filterSelect.innerHTML = `<option value="">All Dealers</option>` +
        dealers.map(d => `<option value="${d.id}">${escapeHtml(d.name)} (${escapeHtml(d.city)})</option>`).join("");
      if (currentVal) filterSelect.value = currentVal;
    }

    // 3. Assistant context dropdown
    const asstSelect = document.getElementById("assistantDealerSelect");
    if (asstSelect) {
      const currentVal = asstSelect.value;
      asstSelect.innerHTML = `<option value="">No Dealer Context</option>` +
        dealers.map(d => `<option value="${d.id}">${escapeHtml(d.name)} (${escapeHtml(d.city)})</option>`).join("");
      if (currentVal) asstSelect.value = currentVal;
    }
  }

  function renderDealersTable(dealers) {
    const tbody = document.getElementById("dealersTableBody");
    const query = (state.dealersView.search || "").toLowerCase().trim();

    const filtered = dealers.filter(d => {
      if (!query) return true;
      return (d.dealer_code || "").toLowerCase().includes(query) ||
        (d.name || "").toLowerCase().includes(query) ||
        (d.city || "").toLowerCase().includes(query);
    });

    document.getElementById("dealersCountSummary").textContent = `${filtered.length} Dealers Found`;
    document.getElementById("dealersPageInfo").textContent = `Showing 1 to ${filtered.length} of ${filtered.length} dealers`;

    if (filtered.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5" class="empty-state">
            <span class="empty-icon">🔍</span>
            <span class="empty-title">No dealers match your filter</span>
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = filtered.map(d => `
      <tr>
        <td><span class="sku-badge">${escapeHtml(d.dealer_code)}</span></td>
        <td>
          <div style="font-weight:600; color:#fff;">${escapeHtml(d.name)}</div>
        </td>
        <td>${escapeHtml(d.city)}</td>
        <td class="tabular-nums" style="font-weight:700;">${formatMoney(d.credit_limit)}</td>
        <td>
          <button class="btn btn-secondary btn-sm btn-dealer-order" data-id="${d.id}">
            + Create Order
          </button>
        </td>
      </tr>
    `).join("");

    tbody.querySelectorAll(".btn-dealer-order").forEach(btn => {
      btn.addEventListener("click", () => {
        const dealerId = btn.getAttribute("data-id");
        openCreateOrderModalWithDealer(dealerId);
      });
    });
  }

  async function submitAddDealer() {
    const dealer_code = document.getElementById("dealerCodeInput").value.trim();
    const name = document.getElementById("dealerNameInput").value.trim();
    const city = document.getElementById("dealerCityInput").value.trim();
    const credit_limit = document.getElementById("dealerCreditInput").value.trim();

    if (!dealer_code || !name || !city || !credit_limit) {
      showToast("Please complete all required dealer fields.", "error");
      return;
    }

    const btn = document.getElementById("btnSubmitAddDealer");
    btn.disabled = true;
    btn.textContent = "Registering...";

    try {
      const created = await apiFetch("/api/dealers/", {
        method: "POST",
        body: JSON.stringify({ dealer_code, name, city, credit_limit }),
      });
      showToast(`Dealer ${created.dealer_code} (${created.name}) registered successfully!`, "success");
      closeModal("modalAddDealer");
      document.getElementById("addDealerForm").reset();
      loadDealersData();
      loadOverviewData();
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Register Dealer";
    }
  }

  // ---- Orders Pipeline & Order Builder --------------------------------------
  async function loadOrdersData() {
    const tbody = document.getElementById("ordersTableBody");
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="loading-state">
          <div class="spinner"></div>
          <span>Loading order pipeline...</span>
        </td>
      </tr>
    `;

    const { page, pageSize, status, dealerId } = state.ordersView;
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });

    if (status) params.append("status", status);
    if (dealerId) params.append("dealer_id", dealerId);

    try {
      const data = await apiFetch(`/api/orders/?${params.toString()}`);
      state.ordersView.totalCount = data.count || 0;
      renderOrdersTable(data.results || []);
      renderOrdersPagination(data);
    } catch (err) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="empty-state">
            <span class="empty-title">Failed to load orders</span>
            <span class="empty-desc">${escapeHtml(err.message)}</span>
          </td>
        </tr>
      `;
    }
  }

  function renderOrdersTable(orders) {
    const tbody = document.getElementById("ordersTableBody");
    if (!orders || orders.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="empty-state">
            <span class="empty-icon">📋</span>
            <span class="empty-title">No orders found</span>
            <span class="empty-desc">Create a new draft order to get started.</span>
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = orders.map(o => `
      <tr>
        <td>
          <a href="#" class="order-link sku-badge" data-orderno="${escapeHtml(o.order_number)}">${escapeHtml(o.order_number)}</a>
        </td>
        <td>
          <div style="font-weight:600; color:#fff;">${escapeHtml(o.dealer_name || "Dealer #" + o.dealer_id)}</div>
          <div style="font-size:0.75rem; color:var(--text-muted);">${escapeHtml(o.dealer_code || "")}</div>
        </td>
        <td>${getOrderStatusBadge(o.status)}</td>
        <td class="tabular-nums">${(o.items || []).length} items</td>
        <td class="tabular-nums" style="font-weight:700;">${formatMoney(o.grand_total)}</td>
        <td style="font-size:0.78rem; color:var(--text-dim);">${formatDateTime(o.created_at)}</td>
        <td>
          <button class="btn btn-secondary btn-sm btn-view-order" data-orderno="${escapeHtml(o.order_number)}">
            View Details
          </button>
        </td>
      </tr>
    `).join("");

    tbody.querySelectorAll(".order-link, .btn-view-order").forEach(el => {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        openOrderDetail(el.getAttribute("data-orderno"));
      });
    });
  }

  function renderOrdersPagination(data) {
    const { page, pageSize, totalCount } = state.ordersView;
    const totalPages = Math.ceil(totalCount / pageSize) || 1;

    document.getElementById("ordersPageInfo").textContent = `Page ${page} of ${totalPages} (${totalCount} total orders)`;
    document.getElementById("btnOrdersPrev").disabled = !data.previous || page <= 1;
    document.getElementById("btnOrdersNext").disabled = !data.next || page >= totalPages;
    document.getElementById("ordersCountSummary").textContent = `Showing page ${page} of ${totalPages}`;
  }

  // ---- Order Detail & Lifecycle Actions -------------------------------------
  async function openOrderDetail(orderNumber) {
    const modal = document.getElementById("modalOrderDetail");
    document.getElementById("modalOrderDetailTitle").textContent = `Order ${orderNumber}`;
    document.getElementById("orderDetailSubtitle").textContent = "Fetching order details from API...";
    document.getElementById("orderDetailItemsBody").innerHTML = `
      <tr><td colspan="7" class="loading-state"><div class="spinner"></div></td></tr>
    `;
    document.getElementById("orderDetailActionsFooter").innerHTML = "";

    openModal("modalOrderDetail");

    try {
      const order = await apiFetch(`/api/orders/${encodeURIComponent(orderNumber)}/`);
      renderOrderDetailContent(order);
    } catch (err) {
      document.getElementById("orderDetailSubtitle").textContent = "Error loading order.";
      document.getElementById("orderDetailItemsBody").innerHTML = `
        <tr><td colspan="7" class="empty-state"><span class="empty-desc">${escapeHtml(err.message)}</span></td></tr>
      `;
    }
  }

  function renderOrderDetailContent(order) {
    document.getElementById("modalOrderDetailTitle").textContent = `Order ${order.order_number}`;
    document.getElementById("orderDetailSubtitle").textContent = `Dealer: ${order.dealer_name || order.dealer_id} (${order.dealer_code || ""}) &bull; City: ${order.dealer_city || "--"}`;
    document.getElementById("orderDetailStatusBadge").outerHTML = `<span class="badge" id="orderDetailStatusBadge">${getOrderStatusBadge(order.status)}</span>`;
    document.getElementById("orderDetailDate").textContent = `Created: ${formatDateTime(order.created_at)}`;

    // Items table
    const tbody = document.getElementById("orderDetailItemsBody");
    const items = order.items || [];
    tbody.innerHTML = items.map(it => `
      <tr>
        <td><span class="sku-badge">${escapeHtml(it.sku)}</span></td>
        <td style="font-weight:600;">${escapeHtml(it.name || it.sku)}</td>
        <td class="tabular-nums">${it.quantity}</td>
        <td class="tabular-nums">${formatMoney(it.unit_price)}</td>
        <td class="tabular-nums">${formatMoney(it.line_subtotal)}</td>
        <td class="tabular-nums">${formatMoney(it.line_tax)}</td>
        <td class="tabular-nums" style="font-weight:700;">${formatMoney(it.line_total)}</td>
      </tr>
    `).join("");

    // Totals
    document.getElementById("orderDetailSubtotal").textContent = formatMoney(order.subtotal);
    document.getElementById("orderDetailTax").textContent = formatMoney(order.tax_total);
    document.getElementById("orderDetailGrand").textContent = formatMoney(order.grand_total);

    // Dynamic lifecycle actions
    const footer = document.getElementById("orderDetailActionsFooter");
    footer.innerHTML = "";

    const closeBtn = document.createElement("button");
    closeBtn.className = "btn btn-secondary";
    closeBtn.textContent = "Close";
    closeBtn.addEventListener("click", () => closeModal("modalOrderDetail"));
    footer.appendChild(closeBtn);

    const status = (order.status || "").toUpperCase();

    if (status === "DRAFT") {
      const confirmBtn = document.createElement("button");
      confirmBtn.className = "btn btn-success";
      confirmBtn.textContent = "Confirm Order (Allocate Stock)";
      confirmBtn.addEventListener("click", () => executeOrderLifecycleAction(order.order_number, "confirm"));
      footer.appendChild(confirmBtn);

      const cancelBtn = document.createElement("button");
      cancelBtn.className = "btn btn-danger";
      cancelBtn.textContent = "Cancel Draft";
      cancelBtn.addEventListener("click", () => executeOrderLifecycleAction(order.order_number, "cancel"));
      footer.appendChild(cancelBtn);
    } else if (status === "CONFIRMED") {
      const dispatchBtn = document.createElement("button");
      dispatchBtn.className = "btn btn-primary";
      dispatchBtn.textContent = "Dispatch Order";
      dispatchBtn.addEventListener("click", () => executeOrderLifecycleAction(order.order_number, "dispatch"));
      footer.appendChild(dispatchBtn);

      const cancelBtn = document.createElement("button");
      cancelBtn.className = "btn btn-danger";
      cancelBtn.textContent = "Cancel Order (Restore Stock)";
      cancelBtn.addEventListener("click", () => executeOrderLifecycleAction(order.order_number, "cancel"));
      footer.appendChild(cancelBtn);
    } else if (status === "DISPATCHED") {
      const deliverBtn = document.createElement("button");
      deliverBtn.className = "btn btn-success";
      deliverBtn.textContent = "Mark as Delivered";
      deliverBtn.addEventListener("click", () => executeOrderLifecycleAction(order.order_number, "deliver"));
      footer.appendChild(deliverBtn);
    }
  }

  async function executeOrderLifecycleAction(orderNumber, action) {
    if (!confirm(`Are you sure you want to ${action.toUpperCase()} order ${orderNumber}?`)) {
      return;
    }

    try {
      await apiFetch(`/api/orders/${encodeURIComponent(orderNumber)}/${action}/`, {
        method: "POST",
      });
      showToast(`Order ${orderNumber} successfully updated: ${action.toUpperCase()}`, "success");
      openOrderDetail(orderNumber);
      loadOrdersData();
      loadOverviewData();
    } catch (err) {
      showToast(`Action failed: ${err.message}`, "error");
    }
  }

  // ---- Draft Order Creator Modal --------------------------------------------
  function openCreateOrderModal() {
    const tbody = document.getElementById("orderItemsBuilderBody");
    tbody.innerHTML = "";
    addOrderItemRow(); // add first item row by default
    updateOrderPreviewTotals();
    openModal("modalCreateOrder");
  }

  function openCreateOrderModalWithDealer(dealerId) {
    openCreateOrderModal();
    const select = document.getElementById("orderFormDealer");
    if (select) select.value = dealerId;
  }

  function openCreateOrderModalWithItem(sku, quantity) {
    switchTab("tab-orders");
    openCreateOrderModal();
    const row = document.querySelector("#orderItemsBuilderBody tr:last-child");
    if (row) {
      const skuInput = row.querySelector(".builder-sku-input");
      const qtyInput = row.querySelector(".builder-qty-input");
      if (skuInput) skuInput.value = sku;
      if (qtyInput) qtyInput.value = quantity;
      lookupRowSkuPrice(row);
    }
  }

  function addOrderItemRow() {
    const tbody = document.getElementById("orderItemsBuilderBody");
    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td>
        <input type="text" class="form-control builder-sku-input" placeholder="Enter SKU (e.g. BRK-1044)" autocomplete="off" required style="width:100%;">
        <div class="form-help builder-sku-desc" style="font-size:0.75rem; color:var(--text-muted);">Enter exact part SKU</div>
      </td>
      <td>
        <span class="price builder-price-display">₹0.00</span>
      </td>
      <td>
        <input type="number" class="form-control builder-qty-input" min="1" value="1" required style="max-width:110px;">
      </td>
      <td>
        <button type="button" class="btn btn-outline btn-sm btn-remove-row" title="Remove line">&times;</button>
      </td>
    `;

    const skuInput = tr.querySelector(".builder-sku-input");
    const qtyInput = tr.querySelector(".builder-qty-input");
    const removeBtn = tr.querySelector(".btn-remove-row");

    skuInput.addEventListener("change", () => lookupRowSkuPrice(tr));
    qtyInput.addEventListener("input", () => updateOrderPreviewTotals());
    removeBtn.addEventListener("click", () => {
      tr.remove();
      updateOrderPreviewTotals();
    });

    tbody.appendChild(tr);
  }

  async function lookupRowSkuPrice(tr) {
    const sku = tr.querySelector(".builder-sku-input").value.trim().toUpperCase();
    tr.querySelector(".builder-sku-input").value = sku;
    const priceDisplay = tr.querySelector(".builder-price-display");
    const descDisplay = tr.querySelector(".builder-sku-desc");

    if (!sku) {
      priceDisplay.textContent = "₹0.00";
      priceDisplay.removeAttribute("data-unit-price");
      descDisplay.textContent = "Enter exact part SKU";
      updateOrderPreviewTotals();
      return;
    }

    try {
      const product = await apiFetch(`/api/products/${encodeURIComponent(sku)}/`);
      const price = parseFloat(product.price) || 0;
      priceDisplay.textContent = formatMoney(price);
      priceDisplay.setAttribute("data-unit-price", price.toFixed(2));
      descDisplay.textContent = `${product.name} (Stock: ${product.stock})`;
    } catch {
      priceDisplay.textContent = "SKU not found";
      priceDisplay.removeAttribute("data-unit-price");
      descDisplay.textContent = "Invalid SKU";
    }

    updateOrderPreviewTotals();
  }

  function updateOrderPreviewTotals() {
    let subtotal = 0;
    let taxTotal = 0;

    document.querySelectorAll("#orderItemsBuilderBody tr").forEach(tr => {
      const priceDisplay = tr.querySelector(".builder-price-display");
      const qtyInput = tr.querySelector(".builder-qty-input");

      const unitPrice = parseFloat(priceDisplay.getAttribute("data-unit-price")) || 0;
      const qty = parseInt(qtyInput ? qtyInput.value : 0, 10) || 0;

      if (unitPrice > 0 && qty > 0) {
        const lineSubtotal = Math.round(unitPrice * qty * 100) / 100;
        // Standard 18% GST line-level rounding
        const lineTax = Math.round(lineSubtotal * 0.18 * 100) / 100;
        subtotal += lineSubtotal;
        taxTotal += lineTax;
      }
    });

    const grandTotal = subtotal + taxTotal;

    document.getElementById("orderPreviewSubtotal").textContent = formatMoney(subtotal);
    document.getElementById("orderPreviewTax").textContent = formatMoney(taxTotal);
    document.getElementById("orderPreviewGrand").textContent = formatMoney(grandTotal);
  }

  async function submitCreateDraftOrder() {
    const dealerSelect = document.getElementById("orderFormDealer");
    const dealerId = parseInt(dealerSelect.value, 10);

    if (!dealerId) {
      showToast("Please choose an authorized dealer.", "error");
      return;
    }

    const items = [];
    let hasError = false;

    document.querySelectorAll("#orderItemsBuilderBody tr").forEach(tr => {
      const sku = tr.querySelector(".builder-sku-input").value.trim();
      const qty = parseInt(tr.querySelector(".builder-qty-input").value, 10);

      if (!sku) {
        showToast("Line items cannot have empty SKUs.", "error");
        hasError = true;
        return;
      }
      if (isNaN(qty) || qty < 1) {
        showToast(`Quantity for SKU ${sku} must be at least 1.`, "error");
        hasError = true;
        return;
      }

      items.push({ sku, quantity: qty });
    });

    if (hasError) return;
    if (items.length === 0) {
      showToast("Please add at least one line item.", "error");
      return;
    }

    const submitBtn = document.getElementById("btnSubmitCreateOrder");
    submitBtn.disabled = true;
    submitBtn.textContent = "Creating Draft...";

    try {
      const payload = { dealer_id: dealerId, items };
      const created = await apiFetch("/api/orders/", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      showToast(`Draft Order ${created.order_number} created successfully!`, "success");
      closeModal("modalCreateOrder");
      loadOrdersData();
      loadOverviewData();
      openOrderDetail(created.order_number);
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Create Draft Order";
    }
  }

  // ---- AI Assistant Interface -----------------------------------------------
  async function sendAssistantMessage(userText = null) {
    const input = document.getElementById("assistantInput");
    const text = (userText !== null ? userText : input.value).trim();
    if (!text) return;

    if (userText === null) {
      input.value = "";
    }

    const history = document.getElementById("chatHistory");
    const dealerIdVal = document.getElementById("assistantDealerSelect").value;
    const dealerId = dealerIdVal ? parseInt(dealerIdVal, 10) : null;

    // 1. Render User Message
    const userMsgEl = document.createElement("div");
    userMsgEl.className = "chat-message user";
    userMsgEl.innerHTML = `
      <div class="chat-avatar">U</div>
      <div>
        <div class="chat-bubble">${escapeHtml(text)}</div>
        <div class="message-meta">
          <span>You</span> &bull; <span>${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
        </div>
      </div>
    `;
    history.appendChild(userMsgEl);
    history.scrollTop = history.scrollHeight;

    // 2. Typing indicator
    const typingEl = document.createElement("div");
    typingEl.className = "chat-message assistant";
    typingEl.innerHTML = `
      <div class="chat-avatar">V</div>
      <div>
        <div class="chat-bubble" style="display:flex; align-items:center; gap:8px;">
          <div class="spinner" style="width:16px; height:16px; border-width:2px;"></div>
          <span>Assistant is researching database...</span>
        </div>
      </div>
    `;
    history.appendChild(typingEl);
    history.scrollTop = history.scrollHeight;

    const startTime = Date.now();

    try {
      const body = {
        session_id: state.sessionId,
        message: text,
      };
      if (dealerId) {
        body.dealer_id = dealerId;
      }

      const resp = await apiFetch("/api/assistant/chat/", {
        method: "POST",
        body: JSON.stringify(body),
      });

      const latency = Date.now() - startTime;
      typingEl.remove();

      // Render Assistant Response
      const asstMsgEl = document.createElement("div");
      asstMsgEl.className = "chat-message assistant";
      const modelName = resp.model || "Gemini / Fallback";

      asstMsgEl.innerHTML = `
        <div class="chat-avatar">V</div>
        <div>
          <div class="chat-bubble">${escapeHtml(resp.reply)}</div>
          <div class="message-meta">
            <span>Model: ${escapeHtml(modelName)}</span> &bull;
            <span>${latency}ms</span> &bull;
            <span>${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
        </div>
      `;

      history.appendChild(asstMsgEl);
      history.scrollTop = history.scrollHeight;

      // Update badge
      document.getElementById("assistantModelBadge").textContent = `Model: ${modelName.split(" ")[0] || "Active"}`;

      // If an order was created in message, reload orders & overview
      if (text.toLowerCase().includes("order") || (resp.reply && resp.reply.includes("ORD-"))) {
        loadOrdersData();
        loadOverviewData();
      }
    } catch (err) {
      typingEl.remove();
      const errEl = document.createElement("div");
      errEl.className = "chat-message assistant";
      errEl.innerHTML = `
        <div class="chat-avatar" style="background:var(--color-danger);">!</div>
        <div>
          <div class="chat-bubble" style="border-color:var(--color-danger); color:#fca5a5;">
            Assistant error: ${escapeHtml(err.message)}
          </div>
        </div>
      `;
      history.appendChild(errEl);
      history.scrollTop = history.scrollHeight;
    }
  }

  // ---- Demand Forecast & Reorders -------------------------------------------
  async function loadForecastData() {
    const tbody = document.getElementById("forecastTableBody");
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="loading-state">
          <div class="spinner"></div>
          <span>Loading 4-week demand predictions and inventory calculations...</span>
        </td>
      </tr>
    `;

    try {
      const data = await apiFetch("/api/reorder-suggestions/");
      const list = data.results || data.suggestions || [];
      state.forecast.suggestions = list;
      const reorderNeeded = list.filter(s => (s.reorder_qty || 0) > 0);
      document.getElementById("forecastCountSummary").textContent = `${reorderNeeded.length} of ${list.length} SKUs require replenishment`;
      renderForecastTable(list);
    } catch (err) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="empty-state">
            <span class="empty-title">Failed to load forecast suggestions</span>
            <span class="empty-desc">${escapeHtml(err.message)}</span>
          </td>
        </tr>
      `;
    }
  }

  function renderForecastTable(suggestions) {
    const tbody = document.getElementById("forecastTableBody");
    if (!suggestions || suggestions.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="empty-state">
            <span class="empty-icon">✅</span>
            <span class="empty-title">Inventory in optimal state</span>
            <span class="empty-desc">Current warehouse inventory satisfies all 4-week projected demand with safety stock.</span>
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = suggestions.map(s => {
      const reorderQty = s.reorder_qty !== undefined ? s.reorder_qty : (s.suggested_reorder_qty || 0);
      const demand = s.lead_time_demand !== undefined ? s.lead_time_demand : (s.forecasted_demand_4w || "--");
      const leadTime = s.lead_time_weeks !== undefined ? `${s.lead_time_weeks} Weeks` : (s.lead_time_days ? `${s.lead_time_days} Days` : "7 Days");
      const name = s.product_name || s.name || s.sku;

      return `
        <tr>
          <td><span class="sku-badge">${escapeHtml(s.sku)}</span></td>
          <td>
            <div style="font-weight:600; color:#fff;">${escapeHtml(name)}</div>
            <div style="font-size:0.75rem; color:var(--text-muted);">ROP: ${s.reorder_point || "--"} &bull; Safety: ${s.safety_stock || "--"}</div>
          </td>
          <td>${getStockBadge(s.current_stock)}</td>
          <td class="tabular-nums" style="font-weight:600;">${demand} units</td>
          <td class="tabular-nums" style="color:var(--color-warning); font-weight:800; font-size:1rem;">
            ${reorderQty > 0 ? '+' + reorderQty : '<span style="color:var(--color-success); font-size:0.85rem;">Optimal</span>'}
          </td>
          <td>${leadTime}</td>
          <td>
            <div style="display:flex; gap:6px;">
              <button class="btn btn-secondary btn-sm btn-forecast-details" data-sku="${escapeHtml(s.sku)}" data-name="${escapeHtml(name)}">
                Forecast
              </button>
              <button class="btn btn-primary btn-sm btn-forecast-order" data-sku="${escapeHtml(s.sku)}" data-qty="${reorderQty > 0 ? reorderQty : 10}">
                Draft Order
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join("");

    tbody.querySelectorAll(".btn-forecast-details").forEach(btn => {
      btn.addEventListener("click", () => {
        const sku = btn.getAttribute("data-sku");
        const name = btn.getAttribute("data-name");
        openForecastDrilldownModal(sku, name);
      });
    });

    tbody.querySelectorAll(".btn-forecast-order").forEach(btn => {
      btn.addEventListener("click", () => {
        const sku = btn.getAttribute("data-sku");
        const qty = parseInt(btn.getAttribute("data-qty"), 10) || 5;
        openCreateOrderModalWithItem(sku, qty);
      });
    });
  }

  async function openForecastDrilldownModal(sku, productName) {
    document.getElementById("modalForecastTitle").textContent = `Demand Forecast: ${sku}`;
    document.getElementById("forecastModalSubtitle").textContent = productName;
    document.getElementById("forecastModalCurrentStock").textContent = "--";
    document.getElementById("forecastModalTotalDemand").textContent = "--";
    document.getElementById("forecastModalWeeksBody").innerHTML = `
      <tr><td colspan="2" class="loading-state"><div class="spinner"></div></td></tr>
    `;

    openModal("modalForecastDetail");

    const orderBtn = document.getElementById("btnForecastOrderAction");
    orderBtn.onclick = () => {
      closeModal("modalForecastDetail");
      openCreateOrderModalWithItem(sku, 10);
    };

    try {
      const data = await apiFetch(`/api/forecast/${encodeURIComponent(sku)}/`);
      const weeks = data.forecast || data.forecast_weeks || [];
      const totalDemand = Math.round(weeks.reduce((acc, w) => acc + (parseFloat(w.forecast_units !== undefined ? w.forecast_units : w.predicted_demand) || 0), 0) * 10) / 10;

      // Find stock from cache or fetch
      let currentStock = "--";
      const cached = state.forecast.suggestions.find(s => s.sku === sku);
      if (cached) currentStock = `${cached.current_stock} units`;

      document.getElementById("forecastModalCurrentStock").textContent = currentStock;
      document.getElementById("forecastModalTotalDemand").textContent = `${totalDemand} units`;

      const tbody = document.getElementById("forecastModalWeeksBody");
      tbody.innerHTML = weeks.map(w => {
        const weekLabel = w.week_start ? `Week of ${w.week_start}` : `Week ${w.week_number}`;
        const val = w.forecast_units !== undefined ? w.forecast_units : w.predicted_demand;
        return `
          <tr>
            <td style="font-weight:600; color:#fff;">${escapeHtml(weekLabel)}</td>
            <td class="tabular-nums" style="font-weight:700; color:var(--brand-cyan);">${val} units</td>
          </tr>
        `;
      }).join("");
    } catch (err) {
      document.getElementById("forecastModalWeeksBody").innerHTML = `
        <tr><td colspan="2" class="empty-state"><span class="empty-desc">${escapeHtml(err.message)}</span></td></tr>
      `;
    }
  }

  async function triggerSupplierSync() {
    const btn = document.getElementById("btnTriggerSupplierSync");
    btn.disabled = true;
    btn.textContent = "Syncing...";

    try {
      const res = await apiFetch("/api/sync/supplier/", { method: "POST" });
      showToast(`Supplier catalogue synchronized: ${res.updated_skus !== undefined ? res.updated_skus + ' SKUs processed' : 'Complete'}`, "success");
      loadForecastData();
      loadCatalogueData();
      loadOverviewData();
    } catch (err) {
      showToast(`Sync failed: ${err.message}`, "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<span>⚡</span> Sync Supplier Stock`;
    }
  }

  // ---- Event Handlers Initialization ----------------------------------------
  function setupEventHandlers() {
    // Tab Clicks
    document.querySelectorAll(".nav-item").forEach(item => {
      item.addEventListener("click", (e) => {
        e.preventDefault();
        const tab = item.getAttribute("data-tab");
        if (tab) switchTab(tab);
      });
    });

    // Mobile Menu Toggle
    const mobileBtn = document.getElementById("mobileMenuBtn");
    if (mobileBtn) {
      mobileBtn.addEventListener("click", () => {
        const sidebar = document.getElementById("sidebar");
        if (sidebar) sidebar.classList.toggle("open");
      });
    }

    // Refresh Active Tab
    document.getElementById("btnRefreshActiveTab").addEventListener("click", () => {
      refreshCurrentTab();
      showToast("View refreshed", "info", 1500);
    });

    // Header New Order Button
    document.getElementById("btnHeaderNewOrder").addEventListener("click", () => {
      switchTab("tab-orders");
      openCreateOrderModal();
    });

    // Overview buttons
    document.getElementById("btnViewAllForecast").addEventListener("click", () => switchTab("tab-forecast"));
    document.getElementById("btnViewAllOrders").addEventListener("click", () => switchTab("tab-orders"));

    // Catalogue Toolbar Controls
    const catSearch = document.getElementById("catalogueSearchInput");
    let catTimeout = null;
    catSearch.addEventListener("input", () => {
      clearTimeout(catTimeout);
      catTimeout = setTimeout(() => {
        state.catalogue.search = catSearch.value;
        state.catalogue.page = 1;
        loadCatalogueData();
      }, 300);
    });

    document.getElementById("catalogueCategoryFilter").addEventListener("change", (e) => {
      state.catalogue.category = e.target.value;
      state.catalogue.page = 1;
      loadCatalogueData();
    });

    const catVehicle = document.getElementById("catalogueVehicleFilter");
    let vehTimeout = null;
    catVehicle.addEventListener("input", () => {
      clearTimeout(vehTimeout);
      vehTimeout = setTimeout(() => {
        state.catalogue.vehicle = catVehicle.value;
        state.catalogue.page = 1;
        loadCatalogueData();
      }, 300);
    });

    document.getElementById("btnResetCatalogueFilters").addEventListener("click", () => {
      catSearch.value = "";
      document.getElementById("catalogueCategoryFilter").value = "";
      catVehicle.value = "";
      state.catalogue.search = "";
      state.catalogue.category = "";
      state.catalogue.vehicle = "";
      state.catalogue.page = 1;
      loadCatalogueData();
    });

    document.getElementById("btnCataloguePrev").addEventListener("click", () => {
      if (state.catalogue.page > 1) {
        state.catalogue.page--;
        loadCatalogueData();
      }
    });

    document.getElementById("btnCatalogueNext").addEventListener("click", () => {
      state.catalogue.page++;
      loadCatalogueData();
    });

    // Inventory Modal Handlers
    document.getElementById("btnCancelInventoryModal").addEventListener("click", () => closeModal("modalInventoryUpdate"));
    document.getElementById("btnSubmitInventoryUpdate").addEventListener("click", submitInventoryUpdate);

    // Dealers Directory Handlers
    const dealerSearch = document.getElementById("dealerSearchInput");
    dealerSearch.addEventListener("input", () => {
      state.dealersView.search = dealerSearch.value;
      renderDealersTable(state.dealers);
    });

    document.getElementById("btnOpenAddDealer").addEventListener("click", () => openModal("modalAddDealer"));
    document.getElementById("btnCancelAddDealer").addEventListener("click", () => closeModal("modalAddDealer"));
    document.getElementById("btnSubmitAddDealer").addEventListener("click", submitAddDealer);

    // Orders Filter Controls
    document.getElementById("orderStatusFilter").addEventListener("change", (e) => {
      state.ordersView.status = e.target.value;
      state.ordersView.page = 1;
      loadOrdersData();
    });

    document.getElementById("orderDealerFilter").addEventListener("change", (e) => {
      state.ordersView.dealerId = e.target.value;
      state.ordersView.page = 1;
      loadOrdersData();
    });

    document.getElementById("btnResetOrderFilters").addEventListener("click", () => {
      document.getElementById("orderStatusFilter").value = "";
      document.getElementById("orderDealerFilter").value = "";
      state.ordersView.status = "";
      state.ordersView.dealerId = "";
      state.ordersView.page = 1;
      loadOrdersData();
    });

    document.getElementById("btnOrdersPrev").addEventListener("click", () => {
      if (state.ordersView.page > 1) {
        state.ordersView.page--;
        loadOrdersData();
      }
    });

    document.getElementById("btnOrdersNext").addEventListener("click", () => {
      state.ordersView.page++;
      loadOrdersData();
    });

    document.getElementById("btnOpenCreateOrder").addEventListener("click", openCreateOrderModal);
    document.getElementById("btnCancelCreateOrder").addEventListener("click", () => closeModal("modalCreateOrder"));
    document.getElementById("btnAddOrderItemRow").addEventListener("click", addOrderItemRow);
    document.getElementById("btnSubmitCreateOrder").addEventListener("click", submitCreateDraftOrder);

    // AI Assistant Handlers
    document.getElementById("btnSendAssistant").addEventListener("click", () => sendAssistantMessage());
    document.getElementById("assistantInput").addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        sendAssistantMessage();
      }
    });

    document.querySelectorAll(".prompt-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        const p = chip.getAttribute("data-prompt");
        if (p) sendAssistantMessage(p);
      });
    });

    // Forecast Handlers
    document.getElementById("btnTriggerSupplierSync").addEventListener("click", triggerSupplierSync);
    document.getElementById("btnCloseForecastBtn").addEventListener("click", () => closeModal("modalForecastDetail"));

    setupModalDismissals();
  }

  // ---- Bootstrap Application ------------------------------------------------
  document.addEventListener("DOMContentLoaded", () => {
    startLiveClock();
    checkSystemHealth();
    setInterval(checkSystemHealth, 30000);

    setupEventHandlers();

    // Initial load: Overview & Dealers
    loadOverviewData();
    loadDealersData();
  });

})();
