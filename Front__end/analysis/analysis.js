document.addEventListener("DOMContentLoaded", () => {
  const $ = (id) => document.getElementById(id),
    NS = "http://www.w3.org/2000/svg";
  let model = null,
    ready = false,
    sequence = 0,
    controller;
  const money = (value) =>
    Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 });
  const axis = (value) =>
    Number(value) >= 100000
      ? new Intl.NumberFormat("en-US", {
          notation: "compact",
          maximumFractionDigits: 1,
        }).format(value)
      : money(value);
  const month = (value) => {
    if (!value) return "–";
    const [y, m] = value.split("-").map(Number);
    return new Intl.DateTimeFormat("th-TH", {
      month: "short",
      year: "numeric",
    }).format(new Date(y, m - 1, 1));
  };
  const text = (id, value) => ($(id).textContent = value);
  function change(id, value) {
    const el = $(id);
    el.classList.remove("increase", "decrease");
    if (value === null || value === undefined) {
      el.textContent = "– ไม่มีข้อมูลเดือนก่อน หรือยอดเดิมเป็นศูนย์";
      return;
    }
    const n = Number(value);
    el.textContent = `${n > 0 ? "↑ " : n < 0 ? "↓ " : ""}${Math.abs(n).toFixed(1)}% จากเดือนก่อน`;
    el.classList.add(n > 0 ? "increase" : n < 0 ? "decrease" : "neutral");
  }
  function element(tag, attrs = {}, value) {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([key, value]) =>
      node.setAttribute(key, value),
    );
    if (value !== undefined) node.textContent = value;
    return node;
  }
  function empty(host, message) {
    host.replaceChildren();
    const p = document.createElement("p");
    p.className = "chart-empty";
    p.textContent = message;
    host.append(p);
  }
  function chart(id, combined = false) {
    const host = $(id),
      series = model?.series || [];
    if (!series.some((r) => r.units_used !== null)) {
      empty(host, "ยังไม่มีบิลค่าไฟในช่วงที่เลือก");
      return;
    }
    const costOnly = !combined && $("chartMetric").value === "cost";
    const left = 55,
      right = combined ? 70 : 25,
      top = 28,
      height = 275,
      base = 225,
      width = 760,
      area = width - left - right;
    const maxOf = (values) => {
      const max = Math.max(0, ...values.filter((v) => v !== null).map(Number));
      return max === 0 ? 1 : Math.ceil((max * 1.15) / 4) * 4;
    };
    const unitsMax = maxOf(series.map((r) => r.units_used)),
      costMax = maxOf(series.map((r) => r.total_cost)),
      max = costOnly ? costMax : unitsMax;
    const svg = element("svg", {
      viewBox: `0 0 ${width} ${height}`,
      role: "img",
      "aria-label": combined ? "หน่วยไฟและค่าใช้จ่ายรายเดือน" : "กราฟรายเดือน",
    });
    for (let tick = 0; tick <= 4; tick++) {
      const y = base - ((base - top) * tick) / 4;
      svg.append(
        element("line", {
          x1: left,
          y1: y,
          x2: width - right,
          y2: y,
          stroke: "#e5edf8",
          "stroke-dasharray": "3 5",
        }),
      );
      svg.append(
        element(
          "text",
          {
            x: left - 9,
            y: y + 4,
            "text-anchor": "end",
            fill: "#8da1bb",
            "font-size": 10,
          },
          axis((max * tick) / 4),
        ),
      );
      if (combined)
        svg.append(
          element(
            "text",
            {
              x: width - right + 10,
              y: y + 4,
              fill: "#8da1bb",
              "font-size": 10,
            },
            axis((costMax * tick) / 4),
          ),
        );
    }
    svg.append(
      element(
        "text",
        { x: left, y: 12, fill: "#7293b9", "font-size": 10 },
        costOnly ? "บาท" : "kWh",
      ),
    );
    if (combined)
      svg.append(
        element(
          "text",
          { x: width - right, y: 12, fill: "#7293b9", "font-size": 10 },
          "บาท",
        ),
      );
    const step = area / series.length,
      barWidth = Math.min(34, step * 0.48),
      segments = [];
    let segment = [];
    series.forEach((r, index) => {
      const x = left + step * (index + 0.5),
        value = r[costOnly ? "total_cost" : "units_used"];
      svg.append(
        element(
          "text",
          {
            x,
            y: height - 22,
            "text-anchor": "middle",
            fill: "#7d95b5",
            "font-size": 9,
          },
          month(r.month).replace(" 25", " "),
        ),
      );
      if (value === null) {
        svg.append(
          element(
            "text",
            {
              x,
              y: base - 6,
              "text-anchor": "middle",
              fill: "#a2b1c5",
              "font-size": 14,
            },
            "–",
          ),
        );
        if (segment.length) {
          segments.push(segment);
          segment = [];
        }
        return;
      }
      const h = (Number(value) / max) * (base - top),
        bar = element("rect", {
          x: x - barWidth / 2,
          y: base - h,
          width: barWidth,
          height: h,
          rx: 3,
          fill: "#2388f7",
          tabindex: 0,
          "aria-label": `${month(r.month)} ${r.units_used} kWh ${money(r.total_cost)} บาท`,
        });
      bar.append(
        element(
          "title",
          {},
          `${month(r.month)}: ${r.units_used} kWh · ${money(r.total_cost)} บาท`,
        ),
      );
      svg.append(bar);
      if (combined)
        segment.push({
          x,
          y: base - (Number(r.total_cost) / costMax) * (base - top),
          r,
        });
    });
    if (segment.length) segments.push(segment);
    if (combined)
      segments.forEach((points) => {
        svg.append(
          element("polyline", {
            points: points.map((p) => `${p.x},${p.y}`).join(" "),
            fill: "none",
            stroke: "#28a389",
            "stroke-width": 2.5,
          }),
        );
        points.forEach((p) => {
          const dot = element("circle", {
            cx: p.x,
            cy: p.y,
            r: 4,
            fill: "#28a389",
            tabindex: 0,
          });
          dot.append(
            element(
              "title",
              {},
              `${month(p.r.month)}: ${money(p.r.total_cost)} บาท`,
            ),
          );
          svg.append(dot);
        });
      });
    host.replaceChildren(svg);
  }
  function render() {
    const latest = model?.latest;
    text("latestCost", latest ? `${money(latest.total_cost)} บาท` : "–");
    text("latestUnits", latest ? `${money(latest.units_used)} kWh` : "–");
    change("costChange", latest?.cost_change_percent);
    change("unitsChange", latest?.units_change_percent);
    for (const name of ["highest", "lowest"]) {
      text(name + "Month", month(model?.[name]?.month));
      text(
        name + "Units",
        model?.[name] ? `${money(model[name].units_used)} kWh` : "–",
      );
    }
    text("thisMonthCost", latest ? `${money(latest.total_cost)} บาท` : "–");
    text("thisMonthLabel", month(latest?.month));
    text(
      "previousCost",
      latest?.previous_total_cost !== null &&
        latest?.previous_total_cost !== undefined
        ? `${money(latest.previous_total_cost)} บาท`
        : "–",
    );
    text("previousMonthLabel", month(latest?.previous_month));
    const percent = latest?.cost_change_percent;
    change("comparisonPercent", percent);
    text(
      "comparisonDescription",
      percent === null || percent === undefined
        ? "เปรียบเทียบไม่ได้เมื่อไม่มีบิลเดือนก่อนหรือยอดเดิมเป็นศูนย์"
        : Number(percent) > 0
          ? "ค่าใช้จ่ายเพิ่มขึ้นจากเดือนก่อน"
          : Number(percent) < 0
            ? "ค่าใช้จ่ายลดลงจากเดือนก่อน"
            : "ค่าใช้จ่ายเท่าเดิม",
    );
    const donut = $("costDonut"),
      legend = $("costLegend");
    legend.replaceChildren();
    text("donutTotal", latest ? money(latest.total_cost) : "–");
    const parts = model?.cost_breakdown || [],
      energy = parts.find((p) => p.key === "energy_cost");
    const split =
      energy?.percent === null || !energy ? 0 : Number(energy.percent);
    donut.style.background =
      latest && Number(latest.total_cost) > 0
        ? `conic-gradient(#1685ff 0 ${split}%,#a976ee ${split}% 100%)`
        : "#edf2f8";
    donut.setAttribute(
      "aria-label",
      latest
        ? `ค่าไฟ ${money(latest.energy_cost)} บาท ค่าบริการ ${money(latest.service_charge)} บาท`
        : "ไม่มีบิลสำหรับแสดงสัดส่วน",
    );
    parts.forEach((part) => {
      const line = document.createElement("span"),
        icon = document.createElement("i"),
        value = document.createElement("strong");
      icon.className = part.key === "energy_cost" ? "blue" : "purple";
      value.textContent = part.percent === null ? "–" : `${part.percent}%`;
      line.append(
        icon,
        document.createTextNode(
          part.key === "energy_cost" ? "ค่าไฟ" : "ค่าบริการ",
        ),
        value,
      );
      legend.append(line);
    });
    text(
      "breakdownNote",
      latest
        ? `บิล ${month(latest.month)} · ค่าไฟและค่าบริการเท่านั้น${Number(latest.total_cost) === 0 ? " · ยอดรวมเป็นศูนย์จึงไม่แสดงเปอร์เซ็นต์" : ""}`
        : "ยังไม่มีบิลในช่วงนี้",
    );
    text("applianceMonth", month(model?.appliance_month));
    const bars = $("applianceBars");
    bars.replaceChildren();
    const rows = model?.appliances || [],
      max = Math.max(1, ...rows.map((row) => Number(row.estimated_kwh || 0)));
    rows.forEach((record) => {
      const row = document.createElement("div");
      row.className = "appliance-row";
      const label = document.createElement("span");
      label.textContent = record.name;
      label.title = `${record.quantity} เครื่อง · ${record.source}`;
      const track = document.createElement("div");
      track.className = "appliance-track";
      const fill = document.createElement("div");
      fill.className = "appliance-fill";
      fill.style.width =
        record.estimated_kwh === null
          ? "0"
          : `${(Number(record.estimated_kwh) / max) * 100}%`;
      track.append(fill);
      const value = document.createElement("strong");
      value.textContent =
        record.estimated_kwh === null
          ? "ข้อมูลไม่ครบ"
          : `${money(record.estimated_kwh)} kWh`;
      row.append(label, track, value);
      bars.append(row);
    });
    if (!rows.length)
      empty(bars, "ยังไม่มีการใช้งานเครื่องใช้ในเดือนสิ้นสุดที่เลือก");
    const coverage = model?.appliance_summary;
    text(
      "applianceCoverage",
      coverage
        ? `ประมาณได้ ${coverage.estimated_items} จาก ${coverage.items} รายการ · รวม ${coverage.estimated_kwh === null ? "–" : money(coverage.estimated_kwh)} kWh${coverage.meter_kwh === null ? " · ยังไม่มีบิลเดือนนี้" : ` · มิเตอร์ ${money(coverage.meter_kwh)} kWh`}`
        : "",
    );
    chart("trendChart", true);
    chart("detailChart");
  }
  const tabs = [...document.querySelectorAll("[role=tab]")];
  function setView(view) {
    if (view === "advice") {
      window.location.assign("/frontend/advice/advice.html");
      return;
    }
    tabs.forEach((tab) => {
      const active = tab.dataset.view === view;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      $(tab.getAttribute("aria-controls")).hidden = !active;
    });
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => {
      window.location.hash = tab.dataset.view;
      setView(tab.dataset.view);
    });
    tab.addEventListener("keydown", (event) => {
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      else if (event.key === "ArrowLeft")
        next = (index + tabs.length - 1) % tabs.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabs.length - 1;
      else return;
      event.preventDefault();
      tabs[next].focus();
      tabs[next].click();
    });
  });
  function fromHash() {
    const view = window.location.hash.slice(1);
    setView(["summary", "charts", "advice"].includes(view) ? view : "summary");
  }
  window.addEventListener("hashchange", fromHash);
  async function load() {
    if (!ready) return;
    controller?.abort();
    controller = new AbortController();
    const current = ++sequence;
    model = null;
    render();
    $("analysisStatus").hidden = false;
    text("analysisStatus", "กำลังโหลดข้อมูลวิเคราะห์...");
    $("analysisRetry").hidden = true;
    const params = new URLSearchParams({ months: $("period").value });
    if ($("endMonth").value) params.set("end_month", $("endMonth").value);
    try {
      const response = await fetch(`/api/analysis?${params}`, {
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
      if (!response.ok)
        throw new Error("โหลดข้อมูลวิเคราะห์ไม่สำเร็จ กรุณาลองใหม่");
      const result = await response.json();
      if (current !== sequence) return;
      model = result;
      $("endMonth").value = result.end_month;
      text(
        "rangeLabel",
        `${month(result.start_month)} – ${month(result.end_month)}`,
      );
      render();
      $("analysisStatus").hidden = result.has_data;
      text(
        "analysisStatus",
        "ยังไม่มีข้อมูลในช่วงที่เลือก ลองเปลี่ยนเดือนหรือเพิ่มข้อมูลค่าไฟและเครื่องใช้",
      );
    } catch (error) {
      if (error.name === "AbortError" || current !== sequence) return;
      text("analysisStatus", error.message);
      $("analysisRetry").hidden = false;
    }
  }
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
      if (!response.ok)
        throw new Error("ตรวจสอบการเข้าสู่ระบบไม่สำเร็จ กรุณาลองใหม่");
      const { user } = await response.json();
      if (user.role !== "user") {
        window.location.replace("/admin/dashboard");
        return;
      }
      text("analysisUser", user.full_name || "ผู้ใช้งาน");
      ready = true;
      await load();
    } catch (error) {
      text("analysisStatus", error.message);
      $("analysisRetry").hidden = false;
    }
  }
  $("period").addEventListener("change", load);
  $("endMonth").addEventListener("change", load);
  $("chartMetric").addEventListener("change", () => chart("detailChart"));
  $("analysisRetry").addEventListener("click", () =>
    ready ? load() : initialize(),
  );
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) load();
  });
  document
    .querySelectorAll("[aria-disabled=true]")
    .forEach((link) =>
      link.addEventListener("click", (event) => event.preventDefault()),
    );
  fromHash();
  render();
  initialize();
});
