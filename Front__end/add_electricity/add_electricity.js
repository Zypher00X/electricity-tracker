document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("electricityForm");
  const month = document.getElementById("billingMonth");
  const previous = document.getElementById("previousMeter");
  const current = document.getElementById("currentMeter");
  const price = document.getElementById("unitPrice");
  const charge = document.getElementById("serviceCharge");
  const button = form.querySelector('button[type="submit"]');
  const error = document.getElementById("formError");
  const success = document.getElementById("successMessage");
  const successText = document.getElementById("successMessageText");
  let pending = false,
    authenticated = false;
  const savedMonths = new Set();
  const now = new Date();
  const selected =
    now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0");
  month.replaceChildren();
  for (
    let year = now.getFullYear() + 1;
    year >= now.getFullYear() - 5;
    year--
  ) {
    for (let number = 12; number >= 1; number--) {
      const option = document.createElement("option");
      option.value = year + "-" + String(number).padStart(2, "0");
      option.textContent = new Intl.DateTimeFormat("th-TH", {
        month: "long",
        year: "numeric",
      }).format(new Date(year, number - 1, 1));
      option.selected = option.value === selected;
      month.append(option);
    }
  }
  price.min = "0.0001";
  button.textContent = "คำนวณและบันทึก";
  button.disabled = true;
  function showError(message) {
    error.textContent = message;
    error.classList.add("show");
  }
  function render(record) {
    const format = (value, places) =>
      new Intl.NumberFormat("th-TH", {
        minimumFractionDigits: places,
        maximumFractionDigits: places,
      }).format(Number(value));
    document.getElementById("resultUnits").textContent = format(
      record.units_used,
      0,
    );
    document.getElementById("resultEnergyCost").textContent = format(
      record.energy_cost,
      2,
    );
    document.getElementById("resultTotal").textContent = format(
      record.total_cost,
      2,
    );
  }
  async function loadRecords() {
    const response = await fetch("/api/electricity", {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!response.ok) throw new Error("Cannot load records");
    return (await response.json()).records;
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (pending || !authenticated) return;
    error.classList.remove("show");
    success.classList.remove("show");
    if (!form.reportValidity()) return;
    const before = Number(previous.value),
      after = Number(current.value);
    if (
      !Number.isSafeInteger(before) ||
      !Number.isSafeInteger(after) ||
      after < before
    ) {
      showError(
        "เลขมิเตอร์ต้องเป็นจำนวนเต็ม และมิเตอร์ปัจจุบันต้องไม่น้อยกว่าครั้งก่อน",
      );
      return;
    }
    const requestedMonth = month.value;
    if (savedMonths.has(requestedMonth)) {
      showError("มีข้อมูลค่าไฟของเดือนนี้แล้ว");
      return;
    }
    const payload = {
      billing_month: requestedMonth,
      previous_meter: before,
      current_meter: after,
      unit_price: price.value,
      service_charge: charge.value,
    };
    pending = true;
    button.disabled = true;
    button.textContent = "กำลังบันทึก...";
    const inputs = [month, previous, current, price, charge];
    inputs.forEach((input) => {
      input.disabled = true;
    });
    try {
      const response = await fetch("/api/electricity", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (response.status === 401) {
        window.location.replace("/login");
        return;
      }
      if (!response.ok) {
        if (response.status === 409) savedMonths.add(requestedMonth);
        showError(
          typeof result.detail === "string"
            ? result.detail
            : "กรุณาตรวจรูปแบบเดือน เลขมิเตอร์ และจำนวนเงิน",
        );
        return;
      }
      savedMonths.add(requestedMonth);
      render(result.record);
      successText.textContent = result.message;
      success.classList.add("show");
    } catch (_) {
      // A timeout may follow a successful write. Read back; never auto-retry POST.
      try {
        const records = await loadRecords();
        records.forEach((record) => savedMonths.add(record.billing_month));
        const record = records.find(
          (record) => record.billing_month === requestedMonth,
        );
        if (record) {
          render(record);
          successText.textContent =
            "พบข้อมูลเดือนนี้ที่บันทึกแล้ว กรุณาตรวจผลลัพธ์";
          success.classList.add("show");
        } else
          showError(
            "การเชื่อมต่อขัดข้อง ยังไม่พบข้อมูลเดือนนี้ กรุณาตรวจแล้วลองใหม่",
          );
      } catch (_) {
        showError("ยังยืนยันการบันทึกไม่ได้ กรุณาตรวจรายการก่อนลองใหม่");
      }
    } finally {
      pending = false;
      inputs.forEach((input) => {
        input.disabled = false;
      });
      button.disabled = !authenticated;
      button.textContent = "คำนวณและบันทึก";
    }
  });
  async function initialize() {
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
      const nameElement = document.getElementById("sidebarUserName");
      if (nameElement) nameElement.textContent = name;
      for (const id of ["sidebarAvatarText", "topbarAvatarText"]) {
        const element = document.getElementById(id);
        if (element)
          element.textContent = name.trim().charAt(0).toUpperCase() || "U";
      }
      authenticated = true;
      button.disabled = false;
      try {
        (await loadRecords()).forEach((record) =>
          savedMonths.add(record.billing_month),
        );
      } catch (_) {
        showError("โหลดรายการเดิมไม่สำเร็จ ระบบจะตรวจเดือนซ้ำเมื่อบันทึก");
      }
    } catch (_) {
      showError("ตรวจสอบการเข้าสู่ระบบไม่สำเร็จ กรุณารีเฟรชหน้าแล้วลองใหม่");
    }
  }
  initialize();
});
