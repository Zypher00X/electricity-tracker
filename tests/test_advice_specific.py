import pytest
from app.advice.schemas import ModelAnswer
from test_advice import advice, payload
from test_appliances import appliances

def test_temperature_exception_does_not_allow_fabricated_numbers():
    data = dict(in_scope=True, summary='เริ่มที่ 26–27 องศาเซลเซียส พร้อมพัดลมหากสบาย', actions=[dict(title='ตรวจความสบาย', instruction='ปรับตามสุขภาพและสภาพห้อง', reason='ไม่รับประกันยอดประหยัด', scenario_id=None)], assumptions=[], missing_data=[])
    ModelAnswer.model_validate(data).check_grounding({'scenarios': []})
    ModelAnswer.model_validate(data | {'summary': 'ไม่สามารถรับประกันยอดประหยัดได้'}).check_grounding({'scenarios': []})
    ModelAnswer.model_validate(data | {'summary': 'นี่ไม่ใช่การรับประกันยอดประหยัด'}).check_grounding({'scenarios': []})
    with pytest.raises(ValueError):
        ModelAnswer.model_validate(data | {'summary': 'ไม่รับประกันอย่างอื่น แต่รับประกันยอดประหยัด'}).check_grounding({'scenarios': []})
    for bad in ('ประหยัด 500 บาท', 'ตั้งไว้ 18 องศา', 'ลดได้ ๕๐ เปอร์เซ็นต์'):
        with pytest.raises(ValueError): ModelAnswer.model_validate(data | {'summary': bad}).check_grounding({'scenarios': []})

def test_followup_retains_action_details_and_month_isolation(advice):
    client, service, provider, *_ = advice
    first = payload()
    response = client.post('/api/advice/chat', json=first)
    assert response.status_code == 200
    recorded = response.json()['context']['facts']['devices'][0]
    assert float(recorded['average_power_w']) == 200 and float(recorded['hours_per_day']) == 8 and recorded['days_used'] == 20
    follow = payload(topic='custom', question='ขอข้อแรกละเอียดขึ้น', conversation_id=first['conversation_id'])
    assert client.post('/api/advice/chat', json=follow).status_code == 200
    history = provider.calls[-1][2]
    assert 'ตั้งพักเมื่อหยุดใช้งาน' in history[0]['answer']
    assert 'ตั้งพักเมื่อหยุดใช้งาน' in history[0]['actions'][0]['instruction']
    assert len(history) <= 4 and len(history[0]['answer']) <= 1800
    other = payload(topic='custom', question='ขอข้อแรกละเอียดขึ้น', month='2026-09', conversation_id=first['conversation_id'])
    calls = len(provider.calls)
    assert client.post('/api/advice/chat', json=other).json()['source'] == 'scope'
    assert len(provider.calls) == calls  # No previous month's action context reaches the model.

def test_ambiguous_questions_without_real_history_ask_for_context(advice):
    client, service, provider, *_ = advice
    first = payload(topic='custom', question='อันนั้นควรปรับยังไง')
    for _ in range(2):
        result = client.post('/api/advice/chat', json=first | {'request_id': str(__import__('uuid').uuid4())}).json()
        assert result['source'] in ('scope', 'cache')
        assert 'กรุณาระบุชื่อเครื่องใช้' in result['answer']['summary']
    assert len(provider.calls) == 0
