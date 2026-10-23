document.addEventListener('DOMContentLoaded',()=>{
 const $=id=>document.getElementById(id),dialog=$('billDialog'),form=$('billEditForm');
 let record=null,deleting=false,busy=false,lastRequest=null;
 const fields=['billing_month','previous_meter','current_meter','unit_price','service_charge'];
 const labels={billing_month:'billMonth',previous_meter:'billPrevious',current_meter:'billCurrent',unit_price:'billPrice',service_charge:'billCharge'};
 const money=v=>Number(v).toLocaleString('th-TH',{maximumFractionDigits:2,minimumFractionDigits:2});
 function preview(){const previous=Number($('billPrevious').value),current=Number($('billCurrent').value),price=Number($('billPrice').value),charge=Number($('billCharge').value);
  $('billPreview').textContent=current>=previous?`${current-previous} หน่วย · ค่าไฟ ${money((current-previous)*price)} บาท · รวมประมาณ ${money((current-previous)*price+charge)} บาท (ยอดยืนยันคำนวณโดยระบบเมื่อบันทึก)`:'เลขมิเตอร์ปัจจุบันต้องไม่น้อยกว่าครั้งก่อน';}
 function lock(){dialog.querySelectorAll('input,button').forEach(n=>n.disabled=busy);dialog.setAttribute('aria-busy',String(busy));}
 function close(){if(busy)return;dialog.close();}
 function refresh(){window.dispatchEvent(new CustomEvent('history:changed'));}
 function open(value,remove){record=value;deleting=remove;lastRequest=null;$('billStatus').textContent='';$('billReload').hidden=true;form.hidden=remove;$('billDeleteInfo').hidden=!remove;$('billDialogTitle').textContent=remove?'ลบข้อมูลค่าไฟ':'แก้ไขข้อมูลค่าไฟ';$('billDeleteMonth').textContent=value.billing_month;$('billDeleteTotal').textContent=money(value.total_cost)+' บาท';$('billConfirm').textContent=remove?'ยืนยันลบข้อมูล':'บันทึกการแก้ไข';$('billConfirm').classList.toggle('danger',remove);fields.forEach(k=>$(labels[k]).value=value[k]);preview();dialog.showModal();}
 window.addEventListener('history:row',event=>{const {record,row}=event.detail,cell=document.createElement('td');cell.className='bill-actions';for(const [text,remove] of [['แก้ไข',false],['ลบ',true]]){const b=document.createElement('button');b.type='button';b.textContent=text;b.className=remove?'bill-action danger':'bill-action';b.setAttribute('aria-label',text+'ค่าไฟเดือน '+record.billing_month);b.addEventListener('click',()=>open(record,remove));cell.append(b);}row.append(cell);});
 async function submit(){if(busy||(!deleting&&!form.reportValidity()))return;
  if(!deleting&&Number($('billCurrent').value)<Number($('billPrevious').value)){$('billStatus').textContent='เลขมิเตอร์ปัจจุบันต้องไม่น้อยกว่าครั้งก่อน';return;}
  const data={expected_updated_at:record.updated_at};if(!deleting)for(const k of fields)data[k]=['previous_meter','current_meter'].includes(k)?Number($(labels[k]).value):$(labels[k]).value;
  const fingerprint=JSON.stringify(data);if(lastRequest?.fingerprint!==fingerprint)lastRequest={fingerprint,id:crypto.randomUUID()};data.request_id=lastRequest.id;
  busy=true;lock();$('billStatus').textContent=deleting?'กำลังลบข้อมูล...':'กำลังบันทึกการแก้ไข...';
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),45000);
  try{const r=await fetch('/api/history/'+encodeURIComponent(record.record_id),{method:deleting?'DELETE':'PUT',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),signal:controller.signal});
   if(r.status===401){window.location.replace('/login');return;}let d;try{d=await r.json();}catch{}if(!r.ok){if(r.status===409||r.status===404)$('billReload').hidden=false;throw new Error(typeof d?.detail==='string'?d.detail:'ทำรายการไม่สำเร็จ กรุณาลองใหม่หรือตรวจรายการล่าสุด');}
   busy=false;lock();dialog.close();$('historyMutationStatus').textContent=d.message;refresh();
  }catch(e){$('billStatus').textContent=e.name==='AbortError'?'การเชื่อมต่อใช้เวลานาน กรุณาลองคำขอเดิมอีกครั้งหรือโหลดรายการล่าสุด':e.message;$('billReload').hidden=false;}finally{clearTimeout(timeout);busy=false;lock();}}
 $('billCancel').addEventListener('click',close);$('billClose').addEventListener('click',close);$('billConfirm').addEventListener('click',submit);$('billReload').addEventListener('click',()=>{close();refresh();});dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});form.addEventListener('submit',event=>{event.preventDefault();submit();});fields.forEach(k=>$(labels[k]).addEventListener('input',preview));
});
