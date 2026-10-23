document.addEventListener("DOMContentLoaded", () => {
  const $ = (id) => document.getElementById(id),
    form = $("applianceForm");
  const categories = {
    air_conditioner: "แอร์",
    refrigerator: "ตู้เย็น",
    water_heater: "เครื่องทำน้ำอุ่น",
    computer: "คอมพิวเตอร์",
    fan: "พัดลม",
    lighting: "ไฟส่องสว่าง",
    washing_machine: "เครื่องซักผ้า",
    television: "โทรทัศน์",
    air_purifier: "เครื่องฟอกอากาศ",
    dehumidifier: "เครื่องลดความชื้น",
    humidifier: "เครื่องเพิ่มความชื้น",
    space_heater: "เครื่องทำความร้อน",
    freezer: "ตู้แช่ / ตู้แช่แข็ง",
    rice_cooker: "หม้อหุงข้าว",
    microwave: "ไมโครเวฟ",
    induction_cooker: "เตาไฟฟ้า / เตาแม่เหล็กไฟฟ้า",
    electric_oven: "เตาอบไฟฟ้า",
    air_fryer: "หม้อทอดไร้น้ำมัน",
    electric_kettle: "กาต้มน้ำ / กระติกน้ำร้อน",
    coffee_machine: "เครื่องชงกาแฟ",
    toaster: "เครื่องปิ้งขนมปัง",
    blender: "เครื่องปั่น / เครื่องคั้นน้ำ",
    dishwasher: "เครื่องล้างจาน",
    range_hood: "เครื่องดูดควัน",
    water_dispenser: "ตู้น้ำร้อน–น้ำเย็น",
    clothes_dryer: "เครื่องอบผ้า",
    iron: "เตารีด / เครื่องรีดไอน้ำ",
    vacuum_cleaner: "เครื่องดูดฝุ่น / หุ่นยนต์ดูดฝุ่น",
    hair_dryer: "ไดร์เป่าผม",
    hair_styler: "เครื่องหนีบ / ม้วนผม",
    monitor: "จอคอมพิวเตอร์",
    printer: "เครื่องพิมพ์ / สแกนเนอร์",
    router: "เราเตอร์ / อุปกรณ์เครือข่าย",
    game_console: "เครื่องเล่นเกม",
    audio_system: "เครื่องเสียง / ลำโพง",
    charger: "ที่ชาร์จมือถือ / แท็บเล็ต",
    water_pump: "ปั๊มน้ำ",
    aquarium: "อุปกรณ์ตู้ปลา",
    security_camera: "กล้องวงจรปิด",
    electric_vehicle_charger: "เครื่องชาร์จรถไฟฟ้า",
    other: "อื่น ๆ",
  };
  const groups = {
    "อากาศและความสะดวกสบาย": ['air_conditioner','fan','air_purifier','dehumidifier','humidifier','space_heater','water_heater'],
    "ห้องครัวและอาหาร": ['refrigerator','freezer','rice_cooker','microwave','induction_cooker','electric_oven','air_fryer','electric_kettle','coffee_machine','toaster','blender','dishwasher','range_hood','water_dispenser'],
    "ซักรีด ทำความสะอาด และดูแลตัวเอง": ['washing_machine','clothes_dryer','iron','vacuum_cleaner','hair_dryer','hair_styler'],
    "ทำงานและความบันเทิง": ['computer','monitor','printer','router','television','game_console','audio_system','charger'],
    "อุปกรณ์ภายในบ้านและอื่น ๆ": ['lighting','water_pump','aquarium','security_camera','electric_vehicle_charger','other'],
  };
  $("category").replaceChildren();
  Object.entries(groups).forEach(([label, types]) => {
    const group = document.createElement('optgroup');
    group.label = label;
    types.forEach(type => group.append(new Option(categories[type], type)));
    $("category").append(group);
  });
  const sources = {
    unknown: "ยังไม่ทราบ",
    measured: "วัดจากอุปกรณ์จริง",
    manufacturer: "ข้อมูลผู้ผลิต",
    energy_label: "ฉลากพลังงาน",
    user_estimate: "ประมาณด้วยตนเอง",
  };
  let records = [];
  let pending = false, authenticated = false, loadVersion = 0;
  const requestKeys = new Map();
  let editing = null;
  const now = new Date();
  $("billingMonth").value =
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const fields = [
    "applianceName",
    "category",
    "customCategory",
    "quantity",
    "brand",
    "model",
    "ratedPower",
    "averagePower",
    "hours",
    "days",
    "monthlyKwh",
    "source",
    "notes",
  ];
  const number = (id) => ($(id).value === "" ? null : Number($(id).value));
  const method = () => form.querySelector("input[name=method]:checked").value;
  const format = (value) =>
    value.toLocaleString("en-US", { maximumFractionDigits: 4 });
  function monthDays() {
    const [year, month] = $("billingMonth").value.split("-").map(Number);
    return new Date(year, month, 0).getDate();
  }
  function draft() {
    return {
      id: editing || crypto.randomUUID(),
      billing_month: $("billingMonth").value,
      appliance_name: $("applianceName").value.trim(),
      category: $("category").value,
      category_custom: $("category").value === 'other' ? $("customCategory").value.trim() : null,
      quantity: number("quantity"),
      brand: $("brand").value.trim(),
      model: $("model").value.trim(),
      rated_power_w: number("ratedPower"),
      average_power_w: number("averagePower"),
      hours_per_day: number("hours"),
      days_used: number("days"),
      monthly_kwh_per_unit: number("monthlyKwh"),
      estimation_method: method(),
      source: $("source").value,
      notes: $("notes").value.trim(),
    };
  }
  function estimate(record) {
    if (Object.hasOwn(record, "estimated_kwh")) return record.estimated_kwh === null ? null : Number(record.estimated_kwh);
    if (
      record.source === "unknown" ||
      !Number.isInteger(record.quantity) ||
      record.quantity < 1
    )
      return null;
    if (record.estimation_method === "monthly_kwh")
      return record.monthly_kwh_per_unit === null
        ? null
        : record.monthly_kwh_per_unit * record.quantity;
    if (
      record.average_power_w === null ||
      record.hours_per_day === null ||
      record.days_used === null
    )
      return null;
    return (
      (record.average_power_w / 1000) *
      record.hours_per_day *
      record.days_used *
      record.quantity
    );
  }
  function update() {
    const custom = $("category").value === 'other';
    $("customCategoryField").hidden = !custom;
    $("customCategory").disabled = !custom;
    $("customCategory").required = custom;
    const average = method() === "average_power";
    $("averageFields").hidden = !average;
    $("monthlyFields").hidden = average;
    ["averagePower", "hours", "days"].forEach(
      (id) => ($(id).disabled = !average),
    );
    $("monthlyKwh").disabled = average;
    const labelOption = $("source").querySelector("[value=energy_label]");
    labelOption.disabled = average;
    if (average && $("source").value === "energy_label")
      $("source").value = "unknown";
    $("cyclingHint").hidden = !["air_conditioner", "refrigerator", "freezer", "dehumidifier"].includes(
      $("category").value,
    );
    const days = monthDays();
    $("days").max = days;
    $("daysHint").textContent = Number.isFinite(days)
      ? `เดือนนี้มี ${days} วัน`
      : "เลือกเดือนที่ต้องการบันทึก";
    const value = estimate(draft());
    const valid = form.checkValidity() && $("billingMonth").checkValidity();
    $("previewKwh").textContent =
      value !== null && valid
        ? `${format(value)} kWh / เดือน`
        : "– kWh / เดือน";
    $("previewHint").textContent =
      value !== null && valid
        ? average
          ? "กำลังไฟเฉลี่ย ÷ 1,000 × ชั่วโมงต่อวัน × วันใช้งาน × จำนวนเครื่อง"
          : "หน่วยไฟต่อเครื่องในเดือนนี้ × จำนวนเครื่อง"
        : "กรอกค่าที่ใช้คำนวณและระบุแหล่งที่มา หากยังไม่ทราบจะเก็บเป็นข้อมูลไม่ครบ ไม่ใช่ 0 หน่วย";
  }
  function render() {
    const selected = records.filter(
        (r) => r.billing_month === $("billingMonth").value,
      ),
      list = $("applianceList");
    list.replaceChildren();
    $("emptyList").hidden = selected.length > 0;
    $("itemCount").textContent = `${selected.length} รายการ`;
    $("quantityTotal").textContent =
      `${selected.reduce((sum, r) => sum + r.quantity, 0)} เครื่อง`;
    const values = selected.map(estimate).filter((value) => value !== null);
    $("energyTotal").textContent = values.length
      ? `${format(values.reduce((a, b) => a + b, 0))} kWh`
      : "– kWh";
    $("estimateCoverage").textContent = selected.length
      ? `ประมาณได้ ${values.length} จาก ${selected.length} รายการ${values.length < selected.length ? " · ยังมีข้อมูลไม่ครบ" : ""}`
      : "เพิ่มข้อมูลเพื่อเริ่มประมาณการ";
    const [year, month] = $("billingMonth").value.split("-").map(Number);
    $("listMonth").textContent =
      Number.isFinite(year) && Number.isFinite(month)
        ? new Intl.DateTimeFormat("th-TH", {
            month: "long",
            year: "numeric",
          }).format(new Date(year, month - 1, 1))
        : "เลือกเดือนที่บันทึกการใช้งาน";
    selected.forEach((record) => {
      const card = document.createElement("article");
      card.className = "appliance-card";
      const title = document.createElement("div");
      title.className = "item-title";
      const info = document.createElement("div");
      const name = document.createElement("h3");
      name.textContent = record.appliance_name;
      const category = document.createElement("small");
      category.textContent = `${record.category === 'other' ? record.category_custom : categories[record.category]} · ${record.quantity} เครื่อง`;
      info.append(name, category);
      const energy = document.createElement("span");
      energy.className = "item-energy";
      const value = estimate(record);
      energy.textContent =
        value === null ? "ยังประมาณไม่ได้" : `${format(value)} kWh`;
      title.append(info, energy);
      const detail = document.createElement("p");
      detail.className = "item-detail";
      detail.textContent =
        record.estimation_method === "average_power"
          ? `${record.average_power_w ?? "–"} W เฉลี่ย · ${record.hours_per_day ?? "–"} ชม./วัน · ${record.days_used ?? "–"} วัน`
          : `${record.monthly_kwh_per_unit ?? "–"} kWh / เครื่อง / เดือน`;
      const source = document.createElement("p");
      source.className = "item-detail";
      source.textContent = `${sources[record.source]}${record.notes ? " · " + record.notes : ""}`;
      const actions = document.createElement("div");
      actions.className = "item-actions";
      const edit = document.createElement("button");
      edit.type = "button";
      edit.textContent = "แก้ไข";
      edit.setAttribute("aria-label", `แก้ไข ${record.appliance_name}`);
      edit.onclick = () => {
        editing = record.id;
        const map = {
          applianceName: "appliance_name",
          category: "category",
          customCategory: "category_custom",
          quantity: "quantity",
          brand: "brand",
          model: "model",
          ratedPower: "rated_power_w",
          averagePower: "average_power_w",
          hours: "hours_per_day",
          days: "days_used",
          monthlyKwh: "monthly_kwh_per_unit",
          source: "source",
          notes: "notes",
        };
        fields.forEach((id) => ($(id).value = record[map[id]] ?? ""));
        form.querySelector(
          `[name=method][value=${record.estimation_method}]`,
        ).checked = true;
        $("formTitle").textContent = "แก้ไขเครื่องใช้ไฟฟ้า";
        $("submitButton").textContent = "บันทึกการแก้ไข";
        $("formError").hidden = true;
        update();
        $("applianceName").focus();
      };
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "นำออก";
      remove.setAttribute(
        "aria-label",
        `นำ ${record.appliance_name} ในเดือนนี้`,
      );
      remove.textContent = 'ยกเลิกรายการ';
      remove.onclick = async () => {
        if (pending) return;
        if (!(await confirmCancellation(record))) return;
        if (pending) return;
        await mutate(`/api/appliances/${record.id}/cancel`, 'POST', {revision:record.revision});
      };
      actions.append(edit, remove);
      card.append(title, detail, source, actions);
      list.append(card);
    });
  }
  function reset() {
    editing = null;
    form.reset();
    $("formTitle").textContent = "เพิ่มเครื่องใช้ไฟฟ้า";
    $("submitButton").textContent = "＋ บันทึกเครื่องใช้และการใช้งาน";
    $("formError").hidden = true;
    update();
  }
  form.addEventListener("input", update);
  form.addEventListener("change", update);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if(pending || !authenticated || !$('billingMonth').reportValidity() || !form.reportValidity()) return;
    const record=draft();
    if(!record.appliance_name || (record.category==='other' && !record.category_custom)) {
      $('formError').hidden=false;$('formError').textContent='กรุณาระบุชื่อและประเภทเครื่องใช้';return;
    }
    delete record.id;
    if(record.estimation_method==='monthly_kwh') record.average_power_w=record.hours_per_day=record.days_used=null;
    else record.monthly_kwh_per_unit=null;
    if(editing) record.revision=records.find(r=>r.id===editing).revision;
    await mutate(editing ? `/api/appliances/${editing}` : '/api/appliances', editing ? 'PUT' : 'POST', record);
  });
  function feedback(text) {$('feedback').hidden=false;$('feedback').textContent=text;}
  function confirmCancellation(record) {
    const dialog = $('cancelDialog');
    if (dialog.open) return Promise.resolve(false);
    $('cancelApplianceName').textContent = record.appliance_name;
    const [year, month] = record.billing_month.split('-').map(Number);
    $('cancelApplianceMonth').textContent = new Intl.DateTimeFormat('th-TH', {month:'long', year:'numeric'})
      .format(new Date(year, month - 1, 1));
    dialog.returnValue = 'back';
    return new Promise(resolve => {
      dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), {once:true});
      dialog.showModal();
    });
  }
  function lock(value) {
    pending=value;
    document.querySelectorAll('form input,form select,form textarea,form button,#billingMonth,.item-actions button').forEach(element=>element.disabled=value);
    if(!value)update();
  }
  async function loadRecords() {
    const version=++loadVersion;
    $('applianceList').replaceChildren();$('emptyList').hidden=true;
    feedback('กำลังโหลดข้อมูลเครื่องใช้ไฟฟ้า...');
    const response=await fetch(`/api/appliances?billing_month=${encodeURIComponent($('billingMonth').value)}`,{credentials:'same-origin',cache:'no-store'});
    if(response.status===401){window.location.replace('/login');throw new Error('กรุณาเข้าสู่ระบบ');}
    if(!response.ok)throw new Error('โหลดรายการไม่สำเร็จ กรุณากดลองใหม่');
    const result=await response.json();if(version!==loadVersion)return;
    records=result.records;render();$('feedback').hidden=true;
  }
  async function mutate(url,method,payload) {
    lock(true);$('formError').hidden=true;feedback('กำลังบันทึกข้อมูล...');
    const fingerprint=JSON.stringify([url,method,payload]);
    if(!requestKeys.has(fingerprint))requestKeys.set(fingerprint,crypto.randomUUID());
    try {
      const response=await fetch(url,{method,credentials:'same-origin',headers:{'Content-Type':'application/json','Idempotency-Key':requestKeys.get(fingerprint)},body:JSON.stringify(payload)});
      const result=await response.json();
      if(response.status===401){window.location.replace('/login');return;}
      if(!response.ok)throw new Error(typeof result.detail==='string' ? result.detail : 'กรุณาตรวจข้อมูลที่กรอก');
      // Confirmed success: a deliberate identical addition is a new operation.
      requestKeys.delete(fingerprint);reset();
      try {await loadRecords();feedback(result.message);}catch(error){feedback('บันทึกสำเร็จ แต่โหลดรายการไม่สำเร็จ กรุณากดลองใหม่');}
    } catch(error) {
      $('formError').hidden=false;$('formError').textContent=error.message+' หากการเชื่อมต่อขัดข้อง กรุณาตรวจรายการก่อนลองซ้ำ';
      try{await loadRecords();}catch(_){}
    } finally {lock(false);}
  }
  async function initialize() {
    lock(true);feedback('กำลังโหลดข้อมูล...');
    try {
      const response=await fetch('/api/auth/me',{credentials:'same-origin',cache:'no-store'});
      if(response.status===401 || response.status===403){window.location.replace('/login');return;}
      if(!response.ok)throw new Error('ตรวจสอบการเข้าสู่ระบบไม่สำเร็จ');
      const {user}=await response.json();if(user.role!=='user'){window.location.replace('/admin/dashboard');return;}
      document.querySelector('.sidebar-user strong').textContent=user.full_name || 'ผู้ใช้งาน';
      authenticated=true;await loadRecords();
    }catch(error){feedback(error.message+' กรุณากดลองใหม่');}finally{lock(!authenticated);}
  }
  const retry=document.createElement('button');retry.type='button';retry.className='secondary';retry.textContent='โหลดรายการใหม่';
  retry.onclick=()=>{if(pending && authenticated)return; if(!authenticated){initialize();return;}loadRecords().catch(error=>feedback(error.message));};
  $('listMonth').after(retry);
  $("resetButton").onclick = reset;
  $("billingMonth").onchange = () => {
    reset();
    loadRecords().catch(error=>feedback(error.message));
  };
  document
    .querySelectorAll("[aria-disabled=true]")
    .forEach((link) => (link.onclick = (event) => event.preventDefault()));
  update();
  render();
  initialize();
});
