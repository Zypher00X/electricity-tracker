# Deploy PowerTrack บน Render สำหรับงานมหาวิทยาลัย

ใช้ `Dockerfile.render` และ `render.yaml` ที่ root ของ repository โดย FastAPI เสิร์ฟหน้าเว็บและ API ในโดเมนเดียวกัน ไม่ต้องแยก Static Site และไม่ใช้ Docker Compose บน Render

## ก่อน push GitHub

สำหรับรอบนี้ใช้ repository ใหม่ที่ `C:\electricity_tracker\github-ready` ซึ่งไม่มีประวัติ installer ขนาดใหญ่ ส่วน `C:\electricity_tracker` เดิมเก็บไว้ครบ อย่า push จากโฟลเดอร์เดิม ควรสร้าง GitHub repository เปล่าใหม่แล้วเชื่อม remote จาก `github-ready` ไม่ต้อง force push ทับ repository เดิม

```powershell
cd C:\electricity_tracker\github-ready
git status --short
git add .
git diff --cached --stat
git commit -m "Prepare PowerTrack for Render"
git remote add origin https://github.com/ชื่อบัญชี/ชื่อ-repository-ใหม่.git
git push -u origin main
```

ผมเตรียม `git init -b main` ไว้ให้แล้ว ยังไม่ stage, commit หรือเพิ่ม remote ให้ เปลี่ยน URL ในตัวอย่างเป็น repository ของคุณก่อนใช้

1. ตรวจ `git status --short` และ diff ก่อน commit ให้รวมไฟล์ใหม่ของระบบทุกหมวด รวมถึง `deploy/`, `tests/`, `Back__end/requirements.lock`, `Dockerfile.render`, `render.yaml`, `pytest.ini` และคู่มือนี้
2. ห้าม commit `.env`, `.env.production`, Google service-account key, Gemini key, Redis URL จริง หรือ private key รายงานชั่วคราวอยู่ใน `tmp/` และไม่ต้อง push
3. `.gitignore` ไม่ปิดกั้น JSON ทุกไฟล์แล้ว เพื่อให้ schema ของระบบขึ้น GitHub ได้ แต่ยังปิดกั้น credentials และ private keys ตรวจเนื้อหา JSON ที่จะ commit ด้วย
4. Push ด้วยตนเอง จากนั้นตรวจบน GitHub ว่าไฟล์สำคัญขึ้นครบ ไม่ใช่แค่ commit ไฟล์ที่เคย tracked อยู่แล้ว

## สร้างบริการ

1. ใน Render เลือก New > Blueprint เชื่อม repository และ branch ของคุณ ใช้ `render.yaml`
2. จะสร้าง `powertrack-demo` (Docker Web Service Free) และ `powertrack-cache` (Key Value Free) ใน Singapore ชื่อบริการอาจไม่ใช่ชื่อ subdomain สุดท้าย หากมีชื่อซ้ำให้เลือกชื่อใหม่ และแก้ชื่ออ้างอิง Redis ใน YAML ให้ตรงกัน
3. เลือกแผนฟรีและตรวจรายการค่าใช้จ่ายก่อนยืนยัน ไม่ต้องสร้าง Postgres ระบบยังใช้ Sheets เดิม
4. ตั้งค่าตามตารางด้านล่าง หากยังไม่ทราบ URL จริงของ Web Service ให้รอ Render จัดสรร URL แล้วแก้ PUBLIC_ORIGIN และ OAuth callback ก่อน redeploy การ deploy ครั้งแรกอาจไม่สำเร็จจนกว่าจะตั้งครบ
5. เพิ่ม Secret File ในหน้า Environment ชื่อ `google-service-account.json` โดยวางเนื้อหา key เดิมเฉพาะใน Render ห้ามใส่ใน repository ไฟล์จะอยู่ที่ `/etc/secrets/google-service-account.json` ผู้ใช้ container อยู่ group 1000 เพื่ออ่านไฟล์ตามข้อกำหนด Render
6. ตรวจ service account มีสิทธิ์ Editor ของ Spreadsheet เดิม ไม่ต้องแก้ชื่อหรือย้ายตาราง หากใช้ชื่อตารางต่างจากค่าเริ่มต้น ให้ย้ายค่า `GOOGLE_*_SHEET` จาก .env เดิมไป Environment ด้วย
7. ตั้ง Health Check Path เป็น `/health` (Blueprint เตรียมไว้แล้ว) ไม่เพิ่มการอ่าน Sheets ใน health check เพื่อไม่ใช้โควตาทุกครั้งที่ถูก probe
8. เมื่อค่าครบให้ Manual Deploy ไฟล์กำหนดปิด automatic commit deploy แต่การแก้ Blueprint ยังอาจทำให้ Render sync/redeploy ทรัพยากรที่เปลี่ยนได้

## Environment Variables

| ตัวแปร | ค่า |
|---|---|
| `APP_ENV` | `production` |
| `PUBLIC_ORIGIN` | `https://<subdomain-จริง>.onrender.com` ไม่มี path |
| `COOKIE_SECURE` | `true` |
| `COOKIE_SAMESITE` | `lax` |
| `AUTH_COOKIE_NAME` | `__Host-powertrack_access_token` |
| `JWT_SECRET_KEY` | สุ่มใหม่อย่างน้อย 64 ตัวอักษร เก็บเฉพาะ Render |
| `REDIS_URL` | Blueprint อ้าง internal connection string ให้อัตโนมัติ |
| `REDIS_ALLOW_PASSWORDLESS_PRIVATE` | `true` เฉพาะ internal URL ใน private network ของ Render |
| `GOOGLE_CREDENTIALS_PATH` | `/etc/secrets/google-service-account.json` |
| `GOOGLE_SPREADSHEET_ID` | ID Spreadsheet เดิม |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | จาก OAuth client ของระบบ |
| `GOOGLE_OAUTH_REDIRECT_URI` | `https://<subdomain-จริง>.onrender.com/api/auth/google/callback` |
| `GEMINI_API_KEY` | key ของระบบ เก็บเป็น secret |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` ตามโมเดลที่ทดสอบไว้ |
| `WEB_CONCURRENCY` | `1` สำหรับเริ่มทดสอบ Free instance |

Render กำหนด `PORT` ให้เอง entrypoint อ่านค่านี้ ไม่ต้องกรอก Docker Command เพิ่ม สุ่ม JWT ได้ด้วย `python -c "import secrets; print(secrets.token_hex(48))"` บนเครื่องคุณ แล้วเก็บผลเป็น secret ไม่โพสต์ผลในแชต/รายงาน ห้ามใช้ Render `generateValue` กับ JWT โดยตรงเพราะค่าที่สร้างอาจสั้นกว่า 64 ตัวอักษรที่แอปกำหนด

Redis ใช้ `noeviction` เพื่อไม่ไล่ session หรือโควตาทิ้งเมื่อหน่วยความจำเต็ม ค่า `REDIS_ALLOW_PASSWORDLESS_PRIVATE` เป็นการอนุญาตโดยชัดแจ้ง ใช้เฉพาะ Redis private ที่ควบคุมได้ ไม่ใช้กับ public endpoint ปิด external Redis access (`ipAllowList: []`) หากเปิด internal authentication ใน Render ให้ตรวจ connection string ใหม่และสามารถปิด opt-in ได้ ระบบเดิมที่ใช้ host/port/password ยังทำงานเหมือนเดิม `rediss://` รองรับ TLS พร้อมตรวจ certificate

## Google OAuth

ใน Google Cloud Console ของ OAuth client เพิ่ม Authorized redirect URI ตรงกับ URL callback ข้างต้น และเพิ่ม origin ของเว็บหาก client กำหนดไว้ ถ้า consent screen อยู่ Testing ให้เพิ่มอีเมลเพื่อนและอาจารย์เป็น Test users ตามการตั้งค่า OAuth ของโครงการ อย่าลบ localhost callback หากยังใช้พัฒนาบนเครื่อง

## Proxy และ rate limit

entrypoint ไม่เชื่อ `X-Forwarded-For` จากภายนอก และไม่ตั้ง trusted proxies เป็น `*` การตรวจ origin ใช้ PUBLIC_ORIGIN จึงทำงานหลัง HTTPS termination ได้ Secure cookie ยังคงถูกส่งเฉพาะ HTTPS ใน browser

การจำกัด login/register ตาม IP อาจนับรวมผู้ใช้หลัง proxy เดียวกัน แต่ quota AI แยกตามบัญชีเหมือนเดิม อย่าแก้โดยเชื่อ forwarded headers ทุกแหล่ง เตรียมบัญชีทดสอบไว้ก่อนนำเสนอ หรือทยอยสมัครตามช่วงเวลา rate limit หากต้องการระบุ IP ผู้ใช้จริงต้องตรวจ trusted proxy topology ของ Render ก่อนปรับแยกอีกครั้ง

## ตรวจหลัง deploy

1. เปิด `/health` ได้ 200 และหน้า login แสดงครบ ตรวจ log ไม่มี credentials หรือ 429 จาก Sheets
2. login สองบัญชี ตรวจแยกข้อมูลใน dashboard/history/appliances/analysis/settings/advice/reports
3. เพิ่ม แก้ไข ลบค่าไฟ และเพิ่ม/แก้ไข/ยกเลิกเครื่องใช้ ตรวจ Sheets และผลหน้าอื่นหลัง refresh
4. ตรวจ cookie มี Secure/HttpOnly/SameSite และไม่มีข้อมูลส่วนบุคคลค้างหลัง logout
5. ทดสอบ Google login และ AI จริงหนึ่งถึงสองครั้ง ตรวจโควตาแยกบัญชี ไม่รัน load test หนักใส่ Gemini/Sheets จริง
6. ทดสอบเว็บกลับจาก idle และทดสอบ Redis restart ในช่วงที่ยอมให้ session หายได้ก่อนวันนำเสนอ

Free web พักหลังไม่มีการใช้งาน 15 นาทีและคนแรกอาจรอประมาณหนึ่งนาที ส่วน Free Key Value ไม่เก็บข้อมูลถาวรเมื่อ restart จึงอาจต้อง login ใหม่และโควตา/แคชเริ่มใหม่ ข้อมูลหลักที่บันทึกใน Sheets ไม่หาย เปิดเว็บก่อนนำเสนอและสำรอง Sheets ก่อนการทดสอบแก้ไขข้อมูล

## ทดสอบซ้ำบนเครื่อง

ใช้ `python -m pytest -q` และ `node --test tests/*_ui.test.cjs` สำหรับ regression สำหรับ image ใช้ `docker build -f Dockerfile.render -t powertrack:render .` ค่าเริ่มต้นรันแอป ไม่ใช่ pytest; ใช้ `--target test -t powertrack:render-test` เมื่อต้องการ image ทดสอบ แล้ว `docker run --rm --read-only --tmpfs /tmp:mode=1777 powertrack:render-test`

รายงานการเตรียมรอบนี้อยู่ใน `docs/render-readiness.md` ยังไม่มีการ push หรือ deploy อัตโนมัติ

อ้างอิง: [Render Docker secrets](https://render.com/docs/docker-secrets), [Blueprint specification](https://render.com/docs/blueprint-spec), [Key Value](https://render.com/docs/key-value), [Free services](https://render.com/docs/free)
