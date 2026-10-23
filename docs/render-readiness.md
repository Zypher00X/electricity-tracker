# ผลเตรียมขึ้น GitHub และ Render — 23 ตุลาคม 2026

## สิ่งที่แก้และเหตุผล

- เพิ่ม `Dockerfile.render` ซึ่ง default stage รันแอปจริง แยกจาก test stage เพื่อป้องกัน deploy แล้วไปรัน pytest ใช้ Python 3.12 Alpine แบบ pin digest, hash-locked dependencies และติดตั้งเฉพาะ binary wheels ไม่เพิ่ม compiler ใน runtime
- เปลี่ยนฐานของ image Render จาก Debian เป็น Alpine 3.24.3 และอัปเดตแพ็กเกจ เพื่อนำแพ็กเกจ OS ที่มี HIGH เดิมออก ทดสอบ musl wheels และ regression ก่อนใช้ ไม่ได้เปลี่ยน Dockerfile development เดิมให้เป็น Alpine
- runtime ไม่มี pip, รัน UID10001/GID1000 เพื่ออ่าน Render Secret Files โดยไม่ต้องใช้ root
- เพิ่ม entrypoint อ่าน PORT และ WEB_CONCURRENCY โดยใช้หนึ่ง workerเริ่มต้น ไม่เปิด reload และไม่เชื่อ forwarded headers จากแหล่งที่ไม่ยืนยัน
- เพิ่ม `render.yaml` สำหรับ Free Web + Free Key Value ใน Singapore, health `/health`, Redis private connection string, noeviction และปิด external Redis access ไม่มี secrets จริงใน YAML
- ทำ Redis client factory ให้ auth และทุก feature ใช้การตั้งค่า URL เดียวกัน รองรับ redis/rediss โดยยังรักษา legacy host/port/password เดิม การเชื่อมแบบไม่มีรหัสผ่านต้อง opt-in ชัดเจนเฉพาะ private network
- JWT ใน Blueprint ให้กรอกเองอย่างน้อย 64 ตัวอักษร ไม่ใช้ generateValue ที่อาจสั้นกว่าข้อกำหนดแอป
- แก้ gitignore ที่เคยปิด JSON ทุกไฟล์เป็นปิด credentials เฉพาะ และตัด installer, private keys, cache, test artifacts ออกจากชุดที่จะ push
- เพิ่ม pytest.ini จำกัด discovery ใน tests เพื่อไม่เก็บชุดทดสอบซ้ำจากโฟลเดอร์ export ชั่วคราว
- พบ installer Docker Desktop 614 MB ในประวัติ Git เดิม ผู้ใช้เลือกให้เตรียม repository ใหม่แยกโฟลเดอร์ `github-ready` ไม่ rewrite ประวัติเดิม ไม่ลบไฟล์เดิม ไม่ push อัตโนมัติ

## ผลทดสอบ

| การตรวจ | ผล |
|---|---|
| Python บนเครื่อง | 202 passed |
| Python บน final Alpine test image | 202 passed |
| JavaScript UI regression | 17 passed |
| Runtime จริงใช้ PORT=12345 + production flags | ผ่าน health, Host guard, HSTS, static frontend, docs disabled |
| Redis private URL ไม่มี password | auth client และ feature client ping ผ่าน; configuration tests ปฏิเสธถ้าไม่ opt-in |
| Legacy Redis และ TLS URL | configuration tests ผ่าน; TLS client ใช้ SSLConnection |
| Secret file root:1000 mode640 | non-root runtime อ่านได้ |
| HTTP adversarial/ownership/session/CSRF-origin checks | 70 passed |
| Render YAML | ผ่าน JSON Schema ที่ดาวน์โหลดจาก Render ทางการ |
| Bandit / Ruff semantic | ไม่พบ findings / ผ่าน |
| Gitleaks บน repository ใหม่ทั้งหมด | ไม่พบ secrets |
| Trivy image Render | OS 0 และ Python 0 vulnerabilities ในฐานข้อมูล ณ เวลาสแกน ไม่ซ่อนหรือ ignore unfixed |

การทดสอบ k6 สำหรับขอบเขตงาน 8 บัญชีพร้อมกันบน fixture 1 CPU/512MB: 476 requests, 934 checks ผ่านทั้งหมด, ไม่มี HTTP failure, p95 55.74ms ช่วง 30 วินาที source reads ของ bills/appliances/settings เพิ่มเพียงอย่างละหนึ่งครั้งตามรอบ cache ไม่มีการเรียก provider ระหว่างอ่าน ข้อมูลจำลองมี 480 แถวต่อชุดบิล/เครื่องใช้/การใช้รายเดือน

การทดสอบเกินขอบเขตถึง 100 VUs บนทรัพยากรเดียวกัน: 3,481 requests มี 503 จำนวน 6 คำขอ (0.17%), p95 2.2s จึงไม่ผ่านเงื่อนไข zero-error ไม่อ้างว่ารองรับ 100 ผู้ใช้บนขนาดนี้ ต้องเพิ่มทรัพยากรหรือวิเคราะห์คอขวดเพิ่มเติมหากขยายขอบเขต โครงการ 8 คนผ่านตามข้างต้น การทดสอบโหลดใช้ synthetic repositories และ provider stub ไม่ใช่ benchmark ของ Render Free จริงหรือ Sheets/Gemini จริง

การเปลี่ยนรอบนี้ไม่เปลี่ยนการคำนวณหรือ prompt AI ไม่เรียกใช้ Gemini จริงซ้ำเพื่อตรวจคุณภาพใหม่ เนื่องจากเปลี่ยน deployment และ Redis configuration เท่านั้น Regression ของ advice เดิมอยู่ในชุด 202 ข้อ

## ขอบเขตความพร้อม

พร้อมนำ repository สะอาดไป commit/push ด้วยตนเอง แล้วตั้งค่าตาม render-deploy.md ยังต้องกรอก secrets, URL จริง, อัปโหลด Secret File และตั้ง Google OAuth บน Render ก่อนระบบออนไลน์ ยังไม่มีการ deploy จริงในรอบนี้

ผล OS 0 นี้ใช้กับ `powertrack:render` จาก Dockerfile.render เท่านั้น รายงาน HIGH ของ Debian image เดิมยังเป็นข้อเท็จจริงของ image เดิม ไม่ได้อ้างว่า image เดิมถูกแพตช์ครบ ผลสแกนเป็นสถานะ ณ วันที่ทดสอบ ไม่รับประกันช่องโหว่ใหม่ในอนาคต

คงข้อจำกัด Free service idle และ Free Redis ไม่ persistent รวมถึง IP limiter อาจรวมผู้ใช้หลัง proxy ไว้ตามคู่มือ รายงานละเอียดและไฟล์ JSON ของการทดสอบเก็บใน workspace เดิม `tmp/security/render/` และ `tmp/security/trivy-render.json` ไม่ต้อง push artifacts ที่อาจมี token ของบัญชีจำลอง
