document.addEventListener("DOMContentLoaded", () => {
  const $ = (id) => document.getElementById(id),
    form = $("settingsForm");
  const mapping = {
    residenceType: "residence_type",
    occupants: "occupants",
    unitPrice: "default_unit_price",
    serviceCharge: "default_service_charge",
    monthlyBudget: "monthly_budget",
  };
  const fields = Object.keys(mapping),
    residences = {
      unknown: "ยังไม่ระบุ",
      dormitory: "หอพัก",
      apartment: "อพาร์ตเมนต์ / คอนโด",
      house: "บ้าน",
      other: "อื่น ๆ",
    };
  let saved = null,
    ready = false,
    pending = false,
    authenticated = false;
  const format = (value, digits) =>
    Number(value).toLocaleString("en-US", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  function display(id, field, suffix, digits) {
    const input = $(field);
    $(id).textContent =
      input.value === ""
        ? "ยังไม่ระบุ"
        : input.validity.valid
          ? `${format(input.value, digits)} ${suffix}`
          : "กรุณาตรวจข้อมูล";
  }
  function render() {
    $("summaryResidence").textContent = residences[$("residenceType").value];
    display("summaryOccupants", "occupants", "คน", 0);
    display("summaryPrice", "unitPrice", "บาท / kWh", 4);
    display("summaryService", "serviceCharge", "บาท", 2);
    const budget = $("monthlyBudget");
    $("summaryBudget").textContent =
      budget.value === ""
        ? "ยังไม่กำหนดงบ"
        : budget.validity.valid
          ? `${format(budget.value, 2)} บาท`
          : "กรุณาตรวจงบ";
  }
  function populate(record) {
    fields.forEach(
      (id) =>
        ($(id).value =
          record?.[mapping[id]] ?? (id === "residenceType" ? "unknown" : "")),
    );
    render();
  }
  function lock(value) {
    pending = value;
    fields.forEach((id) => ($(id).disabled = value || !ready));
    form.querySelector("button[type=submit]").disabled = value || !ready;
    $("resetSettings").disabled = value || !ready;
    $("settingsRetry").disabled = value;
  }
  function status(message) {
    $("settingsStatus").hidden = !message;
    $("settingsStatus").textContent = message;
  }
  function error(message) {
    $("settingsError").textContent = message;
    $("settingsError").hidden = false;
  }
  async function load() {
    ready = false;
    lock(true);
    $("settingsError").hidden = true;
    $("settingsSuccess").hidden = true;
    $("settingsRetry").hidden = true;
    status("กำลังโหลดการตั้งค่า...");
    try {
      if (!authenticated) {
        const auth = await fetch("/api/auth/me", {
          credentials: "same-origin",
          cache: "no-store",
        });
        if (auth.status === 401 || auth.status === 403) {
          window.location.replace("/login");
          return;
        }
        if (!auth.ok) throw new Error("ตรวจสอบบัญชีไม่สำเร็จ");
        const { user } = await auth.json();
        if (user.role !== "user") {
          window.location.replace("/admin/dashboard");
          return;
        }
        $("settingsUser").textContent = user.full_name || "ผู้ใช้งาน";
        authenticated = true;
      }
      const response = await fetch("/api/settings", {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (response.status === 401) {
        window.location.replace("/login");
        return;
      }
      if (!response.ok) throw new Error("โหลดการตั้งค่าไม่สำเร็จ กรุณาลองใหม่");
      const result = await response.json();
      saved = result.settings;
      populate(saved);
      ready = true;
      status(saved ? "" : "ยังไม่มีการตั้งค่า กรอกข้อมูลแล้วกดบันทึกได้เลย");
      $("settingsSummaryCaption").textContent = saved
        ? "ข้อมูลที่บันทึกไว้"
        : "ยังไม่มีข้อมูลที่บันทึก";
    } catch (cause) {
      status("");
      error(cause.message);
      $("settingsRetry").hidden = false;
    } finally {
      lock(false);
    }
  }
  form.addEventListener("input", () => {
    $("settingsSuccess").hidden = true;
    $("settingsError").hidden = true;
    $("settingsSummaryCaption").textContent =
      "ตัวอย่างค่าที่กำลังแก้ไข · ยังไม่ได้บันทึก";
    render();
  });
  form.addEventListener("change", render);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (pending || !ready || !form.reportValidity()) return;
    const data = { expected_updated_at: saved?.updated_at ?? null };
    fields.forEach(
      (id) =>
        (data[mapping[id]] =
          id === "residenceType"
            ? $(id).value
            : $(id).value === ""
              ? null
              : id === "occupants"
                ? Number($(id).value)
                : $(id).value),
    );
    lock(true);
    $("settingsError").hidden = true;
    $("settingsSuccess").hidden = true;
    status("กำลังบันทึกการตั้งค่า...");
    try {
      const response = await fetch("/api/settings", {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (response.status === 401) {
        window.location.replace("/login");
        return;
      }
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "กรุณาตรวจจำนวนคนและรูปแบบจำนวนเงิน",
        );
      saved = result.settings;
      populate(saved);
      $("settingsSummaryCaption").textContent = "ข้อมูลที่บันทึกไว้";
      $("settingsSuccess").textContent = "บันทึกการตั้งค่าสำเร็จ";
      $("settingsSuccess").hidden = false;
      status("");
    } catch (cause) {
      ready = false;
      status("");
      error(cause.message + " กรุณาโหลดข้อมูลล่าสุดก่อนลองบันทึกใหม่");
      $("settingsRetry").hidden = false;
    } finally {
      lock(false);
    }
  });
  $("resetSettings").addEventListener("click", () => {
    populate(saved);
    $("settingsError").hidden = true;
    $("settingsSuccess").hidden = true;
    $("settingsSummaryCaption").textContent = saved
      ? "ข้อมูลที่บันทึกไว้"
      : "ยังไม่มีข้อมูลที่บันทึก";
  });
  $("settingsRetry").addEventListener("click", load);
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) load();
  });
  document
    .querySelectorAll("[aria-disabled=true]")
    .forEach((link) =>
      link.addEventListener("click", (event) => event.preventDefault()),
    );
  render();
  load();
});
