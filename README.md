# PowerTrack

ระบบบันทึกและวิเคราะห์ค่าไฟ พร้อมข้อมูลเครื่องใช้ไฟฟ้า และคำแนะนำจาก Gemini ใช้ FastAPI, Google Sheets และ Redis

- [วิธี deploy บน Render](docs/render-deploy.md)
- [ผลตรวจความพร้อมสำหรับ Render](docs/render-readiness.md)
- [ผลตรวจ DevSecOps ก่อนหน้า](docs/devsecops-predeploy.md)

สำหรับ Render ใช้ `Dockerfile.render` และ `render.yaml` ส่วน `compose.yaml` เป็นการพัฒนาบนเครื่อง ห้ามนำ `.env` หรือ service-account key ขึ้น GitHub

ทดสอบ Python ด้วย `python -m pytest -q` หลังติดตั้ง runtime จาก `Back__end/requirements.txt` และเครื่องมือใน `tests/requirements-dev.txt` แยกกัน
