"""Isolated load server: Sheets may be real, Gemini is always a deterministic stub."""
from settings_runtime import app, mode
from app.advice import routes
from app.advice.context import Context
from app.advice.service import AdviceService
from app.electricity.service import feature_redis
from app.electricity import routes as electricity
from app.appliances import routes as appliances
from app.settings import routes as settings


class StubGemini:
    model = 'load-test-stub-not-gemini'
    def __init__(self): self.calls = 0
    def generate(self, question, facts, history, guidance):
        self.calls += 1
        return {'in_scope': True, 'summary': 'เริ่มจากเวลาที่เปิดเครื่องใช้ทิ้งไว้ แล้วเทียบผลกับมิเตอร์จริง',
            'actions': [{'title': 'ปิดเมื่อไม่ได้ใช้', 'instruction': 'ตั้งพักคอมพิวเตอร์และปิดหลังเลิกงาน', 'reason': 'ลดช่วงที่ไม่มีการใช้งานจริง', 'scenario_id': None}],
            'assumptions': ['การใช้เครื่องใช้เป็นค่าประมาณ'], 'missing_data': facts['missing_data']}, {}


provider = StubGemini()
service = AdviceService(Context(electricity.service, appliances.service, settings.service), feature_redis, 'test:advice:runtime', provider)
app.dependency_overrides[routes.get_service] = lambda: service


@app.get('/_test/advice')
def info(): return {'isolated': True, 'mode': mode, 'provider': provider.model, 'provider_calls': provider.calls}
