document.addEventListener("DOMContentLoaded", () => {
  const search = document.getElementById("searchInput"),
    filter = document.getElementById("yearFilter");
  const rows = document.getElementById("historyRows"),
    pagination = document.getElementById("pagination");
  const status = document.getElementById("historyStatus"),
    retry = document.getElementById("retryButton");
  const count = document.getElementById("recordCount"),
    empty = document.getElementById("emptyState");
  const months = [
    "ม.ค.",
    "ก.พ.",
    "มี.ค.",
    "เม.ย.",
    "พ.ค.",
    "มิ.ย.",
    "ก.ค.",
    "ส.ค.",
    "ก.ย.",
    "ต.ค.",
    "พ.ย.",
    "ธ.ค.",
  ];
  const money = (value) =>
    Number(value).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  let page = 1,
    controller,
    sequence = 0,
    timer,
    ready = false;
  function render(data) {
    page = data.page;
    rows.replaceChildren();
    pagination.replaceChildren();
    const selected = filter.value;
    filter.replaceChildren(new Option("ทั้งหมด", "all"));
    data.available_years.forEach((year) =>
      filter.add(new Option(`ปี ${year + 543}`, String(year))),
    );
    if (selected !== "all" && !data.available_years.includes(Number(selected)))
      filter.add(new Option(`ปี ${Number(selected) + 543}`, selected));
    filter.value = selected;
    data.records.forEach((record) => {
      const row = document.createElement("tr"),
        [year, month] = record.billing_month.split("-").map(Number);
      [
        `${months[month - 1]} ${year + 543}`,
        record.units_used,
        money(record.energy_cost),
        money(record.service_charge),
        money(record.total_cost),
      ].forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      });
      const cell = document.createElement("td"),
        trend = document.createElement("span");
      const change =
        record.change_percent === null ? null : Number(record.change_percent);
      trend.className = `trend ${change === null || change === 0 ? "neutral" : change > 0 ? "up" : "down"}`;
      trend.textContent =
        change === null
          ? "–"
          : `${change > 0 ? "↑ " : change < 0 ? "↓ " : ""}${Math.abs(change).toFixed(1)}%`;
      trend.setAttribute(
        "aria-label",
        change === null
          ? "ไม่มีข้อมูลเดือนก่อนสำหรับเปรียบเทียบ"
          : change === 0
            ? "ค่าใช้จ่ายเท่าเดิม"
            : `${change > 0 ? "เพิ่มขึ้น" : "ลดลง"} ${Math.abs(change)} เปอร์เซ็นต์จากเดือนก่อน`,
      );
      cell.append(trend);
      row.append(cell);
      window.dispatchEvent(new CustomEvent('history:row', {detail:{record,row}}));
      rows.append(row);
    });
    empty.hidden = data.total > 0;
    empty.textContent =
      search.value.trim() || filter.value !== "all"
        ? "ไม่พบข้อมูลที่ตรงกับการค้นหา"
        : "ยังไม่มีประวัติค่าไฟ เริ่มบันทึกข้อมูลที่เมนูเพิ่มข้อมูลค่าไฟ";
    count.textContent = data.total
      ? `แสดง ${(page - 1) * data.page_size + 1}–${Math.min(page * data.page_size, data.total)} จาก ${data.total} รายการ`
      : "0 รายการ";
    if (!data.total) return;
    function button(label, target, disabled = false) {
      const element = document.createElement("button");
      element.type = "button";
      element.textContent = label;
      element.disabled = disabled;
      element.setAttribute(
        "aria-label",
        label === "‹"
          ? "หน้าก่อนหน้า"
          : label === "›"
            ? "หน้าถัดไป"
            : `หน้า ${label}`,
      );
      if (String(page) === label) element.setAttribute("aria-current", "page");
      element.addEventListener("click", () => {
        page = target;
        load(`กำลังโหลดข้อมูลหน้า ${page}...`);
      });
      pagination.append(element);
    }
    button("‹", page - 1, page === 1);
    const numbers = [
      ...new Set([1, page - 1, page, page + 1, data.total_pages]),
    ]
      .filter((n) => n >= 1 && n <= data.total_pages)
      .sort((a, b) => a - b);
    let last = 0;
    numbers.forEach((number) => {
      if (last && number - last > 1) {
        const gap = document.createElement("span");
        gap.textContent = "…";
        pagination.append(gap);
      }
      button(String(number), number);
      last = number;
    });
    button("›", page + 1, page === data.total_pages);
  }
  function showLoading(message) {
    status.hidden = false;
    status.dataset.loading = "true";
    status.textContent = message;
    retry.hidden = true;
    empty.hidden = true;
    document.querySelector("section").setAttribute("aria-busy", "true");
  }
  async function load(message = "กำลังโหลดข้อมูลค่าไฟ...") {
    if (!ready) return;
    controller?.abort();
    controller = new AbortController();
    const current = ++sequence;
    rows.replaceChildren();
    pagination.replaceChildren();
    empty.hidden = true;
    count.textContent = "";
    retry.hidden = true;
    showLoading(message);
    const params = new URLSearchParams({
      q: search.value.trim(),
      page: String(page),
      page_size: "6",
    });
    if (filter.value !== "all") params.set("year", filter.value);
    try {
      const response = await fetch(`/api/history?${params}`, {
        credentials: "same-origin",
        cache: "no-store",
        signal: controller.signal,
      });
      if (current !== sequence) return;
      if (response.status === 401) {
        window.location.replace("/login");
        return;
      }
      if (response.status === 403) {
        window.location.replace("/admin/dashboard");
        return;
      }
      if (!response.ok) throw new Error("History unavailable");
      const data = await response.json();
      if (current !== sequence) return;
      render(data);
      status.hidden = true;
    } catch (error) {
      if (error.name === "AbortError" || current !== sequence) return;
      delete status.dataset.loading;
      status.textContent = "โหลดประวัติไม่สำเร็จ กรุณาลองใหม่อีกครั้ง";
      retry.hidden = false;
    } finally {
      if (current === sequence)
        document.querySelector("section").setAttribute("aria-busy", "false");
    }
  }
  search.disabled = true;
  filter.disabled = true;
  search.addEventListener("input", () => {
    controller?.abort();
    sequence++;
    clearTimeout(timer);
    page = 1;
    rows.replaceChildren();
    pagination.replaceChildren();
    count.textContent = "";
    showLoading("กำลังค้นหาข้อมูล...");
    timer = setTimeout(() => load("กำลังค้นหาข้อมูล..."), 300);
  });
  filter.addEventListener("change", () => {
    clearTimeout(timer);
    page = 1;
    load("กำลังโหลดข้อมูลตามปีที่เลือก...");
  });
  retry.addEventListener("click", () => (ready ? load() : initialize()));
  document
    .querySelectorAll('[aria-disabled="true"]')
    .forEach((link) =>
      link.addEventListener("click", (event) => event.preventDefault()),
    );
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) load();
  });
  window.addEventListener('history:changed', () => load());
  async function initialize() {
    showLoading("กำลังโหลดข้อมูลค่าไฟ...");
    try {
      const response = await fetch("/api/auth/me", {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (response.status === 401 || response.status === 403) {
        window.location.replace("/login");
        return;
      }
      if (!response.ok) throw new Error("Authentication unavailable");
      const { user } = await response.json();
      if (user.role !== "user") {
        window.location.replace("/admin/dashboard");
        return;
      }
      const name = user.full_name || "ผู้ใช้งาน";
      document.getElementById("sidebarUserName").textContent = name;
      document.getElementById("sidebarAvatarText").textContent =
        name.trim().charAt(0).toUpperCase() || "U";
      ready = true;
      search.disabled = false;
      filter.disabled = false;
      load();
    } catch (error) {
      delete status.dataset.loading;
      document.querySelector("section").setAttribute("aria-busy", "false");
      status.textContent = "ตรวจสอบการเข้าสู่ระบบไม่สำเร็จ กรุณาลองใหม่";
      retry.hidden = false;
    }
  }
  initialize();
});
