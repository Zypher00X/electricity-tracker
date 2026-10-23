document.addEventListener('DOMContentLoaded', () => {
  const $ = id => document.getElementById(id);
  let state = {ready: false, pending: false, remaining: null}, busy = false, blockedUntil = 0, timer;
  function lock() {
    const disabled = !state.ready || state.pending || busy || Date.now() < blockedUntil;
    $('generatePrompt').disabled = disabled;
    $('regeneratePrompt').disabled = disabled;
    $('copyPrompt').disabled = busy || !$('exportPromptText').value;
    const exhausted = state.remaining === 0;
    $('exportCard').classList.toggle('is-exhausted', exhausted);
    $('exportIntro').textContent = exhausted
      ? 'โควตาแชตครบแล้ว คุณยังสร้างพร้อมท์จากข้อมูลเดือนนี้ไปถาม AI ภายนอกได้ ไม่ใช้โควตาแชตเพิ่ม'
      : 'สร้างพร้อมท์จากข้อมูลเดือนที่เลือก ตรวจข้อความแล้วคัดลอกไปใช้ได้ โดยไม่ใช้โควตาแชตหรือเรียก Gemini';
  }
  function wait(seconds) {
    blockedUntil = Date.now() + seconds * 1000;
    clearTimeout(timer);
    $('exportRate').textContent = `สร้างครบ 5 ครั้งต่อนาทีแล้ว กรุณารอประมาณ ${seconds} วินาที`;
    timer = setTimeout(() => {blockedUntil = 0; $('exportRate').textContent = 'สร้างพร้อมท์ใหม่ได้ 5 ครั้งต่อนาทีต่อบัญชี'; lock();}, seconds * 1000 + 50);
  }
  window.addEventListener('advice:state', event => {state = event.detail; lock();});
  async function generate() {
    if ($('generatePrompt').disabled) return;
    busy = true;
    $('exportPromptText').value = '';
    $('promptMeta').textContent = '';
    $('promptStatus').textContent = 'กำลังคำนวณข้อมูลและสร้างพร้อมท์ โดยไม่เรียก AI...';
    if (!$('promptDialog').open) $('promptDialog').showModal();
    lock();
    try {
      const response = await fetch('/api/advice/export-prompt', {
        method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({month: $('adviceMonth').value || null})
      });
      if (response.status === 401) {window.location.replace('/login'); return;}
      const data = await response.json();
      if (!response.ok) {
        if (response.status === 429) wait(Math.max(1, Number(response.headers.get('Retry-After')) || 60));
        throw new Error(typeof data.detail === 'string' ? data.detail : 'สร้างพร้อมท์ไม่สำเร็จ กรุณาลองใหม่');
      }
      $('exportPromptText').value = data.prompt;
      $('promptMeta').textContent = `ข้อมูลเดือน ${data.month} · สร้างเมื่อ ${new Date(data.generated_at).toLocaleString('th-TH')}`;
      $('promptStatus').textContent = 'ตรวจข้อความก่อนคัดลอก หากแก้ข้อมูลในระบบแล้ว ให้กดสร้างใหม่';
      $('exportRate').textContent = `สร้างใหม่ได้อีก ${data.rate_limit.remaining} ครั้งในช่วงนาทีนี้ · การคัดลอกข้อความเดิมไม่เรียก Backend`;
      if (data.rate_limit.remaining === 0) wait(Math.max(1, data.rate_limit.retry_after));
    } catch (error) {
      $('promptStatus').textContent = error.message + ' · ไม่ได้ใช้โควตาแชต';
    } finally {busy = false; lock();}
  }
  $('generatePrompt').addEventListener('click', generate);
  $('regeneratePrompt').addEventListener('click', generate);
  $('closePrompt').addEventListener('click', () => $('promptDialog').close());
  $('copyPrompt').addEventListener('click', async () => {
    if (!$('exportPromptText').value || busy) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText($('exportPromptText').value);
      $('promptStatus').textContent = 'คัดลอกแล้ว นำไปวางใน AI ที่คุณเลือกได้เลย';
    } catch {
      $('exportPromptText').focus(); $('exportPromptText').select();
      $('promptStatus').textContent = 'เลือกข้อความไว้แล้ว กรุณากด Ctrl+C หรือใช้เมนูคัดลอกของอุปกรณ์';
    }
  });
  lock();
});
