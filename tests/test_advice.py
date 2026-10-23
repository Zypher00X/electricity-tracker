import copy
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4
import pytest
from conftest import login
from test_appliances import appliances, post, BASE
from test_settings import MemorySettings
from app.settings.service import Service as SettingsService
from app.advice.context import Context
from app.advice.schemas import ChatInput, ModelAnswer
from app.advice.service import AdviceService, TOPICS
from app.advice.provider import ProviderUnavailable
from app.advice import routes


class FixtureProvider:
    model = 'fixture-model'
    def __init__(self): self.calls = []
    def generate(self, question, facts, history, guidance):
        self.calls.append(copy.deepcopy((question, facts, history, guidance)))
        return {'in_scope': True, 'summary': 'เริ่มจากเครื่องใช้ที่เปิดทิ้งไว้ และตรวจผลกับมิเตอร์จริง',
            'actions': [{'title': 'ลดเวลาที่ไม่จำเป็น', 'instruction': 'ปิดคอมพิวเตอร์หลังเลิกงานและตั้งพักเมื่อหยุดใช้งาน',
                'reason': 'ลดการเปิดทิ้งไว้โดยไม่กระทบงาน', 'scenario_id': None}],
            'assumptions': ['ผลจริงขึ้นกับพฤติกรรมและอากาศ'], 'missing_data': []}, {'promptTokenCount': 100, 'candidatesTokenCount': 80}


@pytest.fixture
def advice(appliances, monkeypatch):
    client, appliance_service, appliance_repo, cache = appliances
    # Electricity is already overridden by the shared system fixture.
    from app.electricity import routes as electricity
    from app.settings import routes as settings
    settings_repo = MemorySettings()
    settings_service = SettingsService(settings_repo, cache, 'test:settings:advice')
    monkeypatch.setattr(settings, 'service', settings_service)
    provider = FixtureProvider()
    service = AdviceService(Context(electricity.service, appliance_service, settings_service), cache, 'test:advice', provider)
    client.app.include_router(routes.router)
    client.app.dependency_overrides[routes.get_service] = lambda: service
    login(client)
    client.post('/api/electricity', json={'billing_month': '2026-10', 'previous_meter': 0, 'current_meter': 100, 'unit_price': '8', 'service_charge': '50'})
    post(client)
    settings_service.save('user-a', __import__('app.settings.schemas', fromlist=['SettingsSave']).SettingsSave(expected_updated_at=None, residence_type='house', occupants=2, monthly_budget='700'))
    return client, service, provider, cache, appliance_repo, settings_repo


def payload(**kwargs):
    return dict(question=TOPICS['overview'], topic='overview', month='2026-10', request_id=str(uuid4()), conversation_id=str(uuid4())) | kwargs


def test_calculated_context_and_minimal_prompt(advice):
    client, service, provider, *_ = advice
    result = client.post('/api/advice/chat', json=payload())
    assert result.status_code == 200, result.text
    facts = result.json()['context']['facts']
    assert Decimal(facts['bill']['total_cost']) == 850
    assert Decimal(facts['budget']['gap_baht']) == 150
    assert Decimal(facts['budget']['target_kwh_reduction']) == Decimal('18.75')
    assert Decimal(facts['budget']['reduction_percent']) == Decimal('17.65')
    assert Decimal(facts['devices'][0]['estimated_kwh']) == 64
    assert Decimal(facts['scenarios'][0]['saved_kwh']) == Decimal('6.40')
    assert Decimal(facts['scenarios'][0]['estimated_saved_baht']) == Decimal('51.20')
    raw = json.dumps(provider.calls, ensure_ascii=False)
    for secret in ('user-a', '@example', 'password', 'phone', 'record_id', 'usage_id'):
        assert secret not in raw
    assert result.headers['cache-control'] == 'no-store'


def test_exact_cache_invalidation_idempotence_and_quota(advice):
    client, service, provider, *_ = advice
    body = payload(); first = client.post('/api/advice/chat', json=body).json()
    replay = client.post('/api/advice/chat', json=body).json()
    assert replay['replayed'] and replay['quota']['remaining'] == 4 and len(provider.calls) == 1
    assert client.post('/api/advice/chat', json=body | {'question': 'different', 'topic': 'custom'}).status_code == 409
    second = client.post('/api/advice/chat', json=payload()).json()
    assert second['source'] == 'cache' and second['quota']['remaining'] == 3 and len(provider.calls) == 1
    client.post('/api/electricity', json={'billing_month': '2026-09', 'previous_meter': 0, 'current_meter': 50, 'unit_price': '8', 'service_charge': '50'})
    third = client.post('/api/advice/chat', json=payload()).json()
    assert third['source'] == 'gemini' and len(provider.calls) == 2
    for _ in range(2): assert client.post('/api/advice/chat', json=payload()).status_code == 200
    over = client.post('/api/advice/chat', json=payload())
    assert over.status_code == 429 and 0 < int(over.headers['retry-after']) <= 3600


def test_empty_other_account_no_llm_and_no_data_leak(advice):
    client, service, provider, *_ = advice
    client.post('/api/advice/chat', json=payload())
    login(client, 'user-b')
    context = client.get('/api/advice/context', params={'month': '2026-10'}).json()
    assert context['facts']['bill'] is None and context['facts']['devices'] == []
    result = client.post('/api/advice/chat', json=payload()).json()
    assert result['source'] == 'insufficient_data' and result['quota']['remaining'] == 4
    assert len(provider.calls) == 1


def test_selected_month_never_borrows_previous_bill(advice):
    client, *_ = advice
    facts = client.get('/api/advice/context', params={'month': '2026-11'}).json()['facts']
    assert facts['bill'] is None and facts['devices'] == []
    assert facts['budget']['gap_baht'] is None


def test_out_of_scope_does_not_call_provider_but_counts(advice):
    client, service, provider, *_ = advice
    response = client.post('/api/advice/chat', json=payload(topic='custom', question='เขียนนิยายเกี่ยวกับแมว'))
    assert response.status_code == 200 and response.json()['source'] == 'scope'
    assert response.json()['quota']['remaining'] == 4 and provider.calls == []


def test_auth_origin_and_owner_tampering(advice):
    client, *_ = advice
    assert client.post('/api/advice/chat', json=payload(user_id='user-b')).status_code == 422
    assert client.post('/api/advice/chat', json=payload(), headers={'Origin': 'https://evil.test'}).status_code == 403
    assert client.post('/api/advice/chat', json=payload(month='0000-01')).status_code == 422
    assert client.get('/api/advice/context?month=0001-01').status_code == 422
    assert client.post('/api/advice/chat', json=payload(question='')).status_code == 422
    assert client.post('/api/advice/chat', json=payload(question='arbitrary topic override')).status_code == 422
    client.post('/api/auth/logout')
    assert client.get('/api/advice/context').status_code == 401
    assert client.post('/api/advice/chat', json=payload()).status_code == 401
    login(client, 'admin'); assert client.get('/api/advice/context').status_code == 403


def test_atomic_rolling_quota_and_two_account_independence(advice):
    _, service, *_ = advice
    with ThreadPoolExecutor(max_workers=20) as pool:
        outcomes = list(pool.map(lambda _: service.quota('burst', True, str(uuid4())), range(20)))
    assert sum(result['admitted'] for result in outcomes) == 5
    assert service.quota('other')['remaining'] == 5
    key = service.owner_key('burst') + ':quota'
    # Expire one rolling-window entry, not a fixed top-of-hour reset.
    member = service.cache.zrange(key, 0, 0)[0]
    service.cache.zadd(key, {member: 0})
    assert service.quota('burst', True, str(uuid4()))['admitted']


def test_provider_failure_cooldown_and_no_blind_retry(advice, monkeypatch):
    client, service, provider, *_ = advice
    calls = []
    def fail(*args): calls.append(1); raise ProviderUnavailable(429)
    monkeypatch.setattr(provider, 'generate', fail)
    body = payload()
    assert client.post('/api/advice/chat', json=body).status_code == 503
    assert client.post('/api/advice/chat', json=body).status_code == 503
    assert client.post('/api/advice/chat', json=payload()).status_code == 503
    assert len(calls) == 1 and service.quota('user-a')['remaining'] == 3


def test_concurrent_duplicate_only_one_generation(advice):
    _, service, provider, *_ = advice
    data = ChatInput(**payload())
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: service.respond('user-a', data), range(8)))
    assert len(provider.calls) == 1 and sum(result['replayed'] for result in results) == 7
    assert service.quota('user-a')['remaining'] == 4


def test_bad_numeric_claims_or_scenario_rejected(advice):
    _, service, provider, *_ = advice
    answer, _ = provider.generate('', {}, [], [])
    facts = service.get_context('user-a', '2026-10')['facts']
    with pytest.raises(ValueError): ModelAnswer(**(answer | {'summary': 'รับประกันลดได้ 500 บาท'})).check_grounding(facts)
    bad = copy.deepcopy(answer); bad['actions'][0]['scenario_id'] = 'made-up'
    with pytest.raises(ValueError): ModelAnswer(**bad).check_grounding(facts)


def test_custom_chat_context_is_owner_scoped_and_bounded(advice):
    client, service, provider, *_ = advice
    conversation_id = str(uuid4())
    for _ in range(3):
        assert client.post('/api/advice/chat', json=payload(topic='custom', question='ช่วยประหยัดไฟอย่างไร', conversation_id=conversation_id)).status_code == 200
    assert len(provider.calls[-1][2]) == 2
    login(client, 'user-b')
    result = client.post('/api/advice/chat', json=payload(conversation_id=conversation_id)).json()
    assert result['context']['facts']['devices'] == []


def test_zero_budget_optional_values_and_fixed_charge_feasibility(advice):
    client, service, *_ = advice
    from app.settings.schemas import SettingsSave
    current = service.context.settings.get('user-a')
    service.context.settings.save('user-a', SettingsSave(expected_updated_at=current.updated_at, monthly_budget='0', default_service_charge='0'))
    facts = service.get_context('user-a', '2026-10')['facts']
    assert facts['budget']['monthly_budget'] == '0'
    assert facts['budget']['feasible_under_recorded_rate'] is False
    assert Decimal(facts['budget']['fixed_charge']) == 50
    assert facts['household']['occupants'] is None


def test_foreign_master_does_not_create_savings_scenario(advice):
    client, service, provider, cache, repo, *_ = advice
    repo.data[0]['rows'][0]['user_id'] = 'user-b'
    cache.delete(service.context.appliances.cache_key)
    facts = service.get_context('user-a', '2026-10')['facts']
    assert facts['devices'] == [] and facts['scenarios'] == []


def test_settings_change_invalidate_answer_and_context_read_reuses_sources(advice):
    client, service, provider, cache, repo, settings_repo = advice
    first = client.post('/api/advice/chat', json=payload()).json()
    load_counts = (repo.loads, settings_repo.loads)
    for _ in range(5): service.get_context('user-a', '2026-10')
    assert (repo.loads, settings_repo.loads) == load_counts
    from app.settings.schemas import SettingsSave
    old = service.context.settings.get('user-a')
    service.context.settings.save('user-a', SettingsSave(expected_updated_at=old.updated_at, monthly_budget='900'))
    second = client.post('/api/advice/chat', json=payload()).json()
    assert second['source'] == 'gemini' and len(provider.calls) == 2
    assert second['context']['version'] != first['context']['version']
    assert Decimal(second['context']['facts']['budget']['gap_baht']) == 0
