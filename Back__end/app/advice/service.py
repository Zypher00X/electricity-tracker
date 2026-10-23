import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import HTTPException
from app.electricity.service import ElectricityService, StorageUnavailable
from .context import digest
from .knowledge import VERSION, relevant
from .provider import Gemini, ProviderUnavailable, PROMPT_VERSION

logger = logging.getLogger(__name__)
TOPICS = {
    'overview': 'ช่วยวิเคราะห์ภาพรวมค่าไฟและจุดที่ควรเริ่มประหยัด',
    'devices': 'เครื่องใช้ไฟฟ้าไหนใช้ไฟมากที่สุด และควรปรับอย่างไร?',
    'budget': 'อยากลดค่าไฟให้ถึงงบ ควรทำอย่างไร?',
    'plan': 'ช่วยวางแผนประหยัดไฟที่เริ่มทำได้ในเจ็ดวัน',
}
QUOTA = '''
local t=redis.call('TIME'); local now=tonumber(t[1])+tonumber(t[2])/1000000
redis.call('ZREMRANGEBYSCORE',KEYS[1],'-inf',now-3600)
local count=redis.call('ZCARD',KEYS[1]); local admitted=0
if ARGV[1]=='1' and count<5 then
 redis.call('ZADD',KEYS[1],now,ARGV[2]);redis.call('EXPIRE',KEYS[1],3601);count=count+1;admitted=1
end
local wait=0
if count>=5 then local first=redis.call('ZRANGE',KEYS[1],0,0,'WITHSCORES');wait=math.max(1,math.ceil(tonumber(first[2])+3600-now)) end
return {admitted,math.max(0,5-count),wait}
'''
PERMIT = '''
local t=redis.call('TIME');local now=tonumber(t[1]);
redis.call('ZREMRANGEBYSCORE',KEYS[1],'-inf',now-45)
local minute=KEYS[1]..':minute:'..math.floor(now/60);local day=KEYS[1]..':day:'..math.floor(now/86400)
if redis.call('ZCARD',KEYS[1])>=2 or tonumber(redis.call('GET',minute) or '0')>=tonumber(ARGV[2]) or tonumber(redis.call('GET',day) or '0')>=tonumber(ARGV[3]) then return 0 end
redis.call('ZADD',KEYS[1],now,ARGV[1]);redis.call('EXPIRE',KEYS[1],60)
redis.call('INCR',minute);redis.call('EXPIRE',minute,120);redis.call('INCR',day);redis.call('EXPIRE',day,86401)
return 1
'''


def normal(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text).strip().lower())


def in_scope(question):
    return any(word in question.lower() for word in (
        'ไฟ', 'แอร์', 'ตู้เย็น', 'เครื่องใช้', 'ประหยัด', 'มิเตอร์', 'วัตต์', 'หน่วย', 'งบ', 'พัดลม',
        'คอม', 'บ้าน', 'หอพัก', 'ห้อง', 'ลดเวลา', 'เปิด', 'ปิด', 'ที่แนะนำ', 'อันไหน', 'ทำอย่างไร', 'เพราะอะไร',
        'energy', 'electric', 'kwh', 'watt', 'air condition', 'refrigerator', 'budget'))


def is_followup(question):
    return len(question) <= 100 and any(word in question for word in ('แล้ว', 'ต่อ', 'ทำไม', 'อย่างไร', 'แบบไหน', 'ได้ไหม', 'ละเอียด', 'ข้อแรก', 'ข้อนี้', 'กี่องศา', 'เท่าไหร่', 'อันนั้น', 'ยังไง'))


def scope_answer(question):
    if is_followup(question):
        return local_answer('ยังไม่มีบริบทที่ชัดเจนว่าหมายถึงเครื่องใช้หรือขั้นตอนใด กรุณาระบุชื่อเครื่องใช้หรือคำแนะนำที่ต้องการขยาย เพื่อให้ช่วยเรื่องการประหยัดไฟได้ตรงจุด')
    return local_answer('ผมช่วยเรื่องค่าไฟ การใช้เครื่องใช้ไฟฟ้า และแผนประหยัดไฟได้ครับ ลองถามเกี่ยวกับการใช้ไฟหรือเป้าหมายงบของคุณ')


def local_answer(message, missing=None):
    return {'in_scope': False, 'summary': message, 'actions': [], 'assumptions': [], 'missing_data': missing or []}


class AdviceService:
    def __init__(self, context, cache, namespace, provider=None):
        self.context, self.cache, self.prefix = context, cache, namespace
        self.provider = provider or Gemini()

    def owner_key(self, owner): return self.prefix + ':u:' + digest(owner)[:24]

    def quota(self, owner, consume=False, member=''):
        result = self.cache.eval(QUOTA, 1, self.owner_key(owner) + ':quota', '1' if consume else '0', member)
        return {'admitted': bool(result[0]), 'remaining': int(result[1]), 'retry_after': int(result[2]), 'limit': 5, 'window_seconds': 3600}

    def get_context(self, owner, month=None):
        try:
            return self.context.get(owner, month) | {'quota': self.quota(owner)}
        except StorageUnavailable: raise
        except Exception as exc:
            logger.warning('Advice context unavailable: %s', type(exc).__name__)
            raise StorageUnavailable() from None

    def respond(self, owner, data):
        if data.topic != 'custom' and normal(data.question) != normal(TOPICS[data.topic]):
            raise HTTPException(422, 'คำถามไม่ตรงกับหัวข้อที่เลือก')
        key = self.owner_key(owner)
        identity = key + ':request:' + str(data.request_id)
        fingerprint = digest(data.model_dump(mode='json', exclude={'request_id'}))
        try:
            # Per-account renewable lock also coalesces identical concurrent requests.
            with ElectricityService(None, self.cache, key).sheet_lock() as guard:
                old = self.cache.get(identity)
                if old:
                    old = json.loads(old)
                    if old['fingerprint'] != fingerprint: raise HTTPException(409, 'รหัสคำขอนี้ถูกใช้กับคำถามอื่นแล้ว')
                    if old['status'] == 'done':
                        return old['response'] | {'quota': self.quota(owner), 'replayed': True}
                    raise HTTPException(503, 'คำขอก่อนหน้าไม่สำเร็จหรือยังประมวลผลอยู่ กรุณาตรวจข้อมูลก่อนส่งคำถามใหม่', headers={'Retry-After': '10'})
                quota = self.quota(owner, True, str(data.request_id))
                if not quota['admitted']:
                    raise HTTPException(429, 'ครบห้าคำถามในช่วงหนึ่งชั่วโมงแล้ว กรุณารอให้โควตาว่าง', headers={'Retry-After': str(quota['retry_after'])})
                self.cache.set(identity, json.dumps({'fingerprint': fingerprint, 'status': 'pending'}), ex=3600)
                try:
                    snapshot = self.context.get(owner, data.month)
                    facts = snapshot['facts']
                    conversation = key + ':chat:' + str(data.conversation_id)
                    stored_history = json.loads(self.cache.get(conversation) or '[]') if data.topic == 'custom' else []
                    history = [{'question': row['question'], 'answer': row['answer'], 'actions': row.get('actions', [])} for row in stored_history
                        if row.get('in_scope', True) and row.get('version') == snapshot['version'] and row.get('month') == facts['month']
                        and row.get('saved_at', 0) > datetime.now(timezone.utc).timestamp() - 3600][-4:]
                    guidance = relevant(data.topic, [row['category'] for row in facts['devices']], data.question)
                    answer_key = key + ':answer:v2:' + digest([snapshot['version'], facts, normal(data.question), data.topic,
                        history, self.provider.model, PROMPT_VERSION, VERSION])
                    cached = self.cache.get(answer_key)
                    usage = {}
                    candidate = None
                    if cached:
                        envelope = json.loads(cached)
                        answer = envelope['answer']
                        candidate = envelope.get('candidate')
                        source = 'cache'
                    elif not in_scope(data.question) and not (history and is_followup(data.question)):
                        answer = scope_answer(data.question)
                        source = 'scope'
                    elif not facts['bill'] and not facts['devices']:
                        answer = local_answer('ยังไม่มีบิลหรือการใช้เครื่องใช้ไฟฟ้าในเดือนที่เลือก กรุณาเพิ่มข้อมูลก่อน เพื่อให้คำแนะนำอ้างอิงการใช้งานจริงของคุณได้', facts['missing_data'])
                        source = 'insufficient_data'
                    else:
                        if self.cache.exists(self.prefix + ':provider-cooldown'):
                            raise ProviderUnavailable(429)
                        permit_id = str(uuid4())
                        limit_minute = max(1, min(int(os.getenv('ADVICE_PROVIDER_RPM', '10')), 60))
                        limit_day = max(1, min(int(os.getenv('ADVICE_PROVIDER_DAILY_LIMIT', '100')), 10000))
                        if not self.cache.eval(PERMIT, 1, self.prefix + ':provider-active', permit_id, limit_minute, limit_day):
                            raise ProviderUnavailable(429)
                        try:
                            answer, usage = self.provider.generate(data.question, facts, history[-4:], guidance)
                        finally:
                            self.cache.zrem(self.prefix + ':provider-active', permit_id)
                        # A test provider must satisfy the same contract as Gemini.
                        from .schemas import ModelAnswer
                        answer = ModelAnswer.model_validate(answer).check_grounding(facts).model_dump()
                        source = 'gemini'
                    guard()
                    if not cached and source == 'gemini' and answer['in_scope']:
                        from app.reports.service import make_candidate
                        candidate = make_candidate(owner, data, snapshot, answer, self.provider.model, usage, history, guidance)
                    if candidate:
                        self.cache.set(key + ':report-candidate:' + candidate['report_id'], json.dumps(candidate, ensure_ascii=False), ex=86400)
                    if not cached: self.cache.set(answer_key, json.dumps({'answer': answer, 'candidate': candidate}, ensure_ascii=False), ex=3600)
                    response = {'answer': answer, 'context': snapshot, 'source': source, 'model': self.provider.model if source in ('gemini', 'cache') else None,
                        'usage': usage, 'quota': quota, 'replayed': False, 'generated_at': datetime.now(timezone.utc).isoformat(),
                        'knowledge_version': VERSION, 'prompt_version': PROMPT_VERSION}
                    response['report_candidate_id'] = candidate['report_id'] if candidate else None
                    if candidate:
                        response['generated_at'] = json.loads(candidate['analysis_json'])['generated_at']
                    self.cache.set(identity, json.dumps({'fingerprint': fingerprint, 'status': 'done', 'response': response}, ensure_ascii=False), ex=3600)
                    try:
                        history = json.loads(self.cache.get(conversation) or '[]')
                        now = datetime.now(timezone.utc).timestamp()
                        history = [row for row in history if row.get('saved_at', 0) > now - 3600
                            and row.get('version') == snapshot['version'] and row.get('month') == facts['month']]
                        history = (history + [{'question': data.question[:500], 'answer': (answer['summary'] + ' ' + ' '.join(a['title'] + ': ' + a['instruction'] + ' ' + a['reason'] for a in answer['actions']))[:1800], 'actions': answer['actions'], 'in_scope': answer['in_scope'],
                            'version': snapshot['version'], 'month': facts['month'], 'saved_at': now}])[-4:]
                        self.cache.set(conversation, json.dumps(history, ensure_ascii=False), ex=3600)
                    except Exception: logger.warning('Advice completed; temporary chat cache unavailable')
                    logger.info('Advice completed source=%s model=%s input_tokens=%s output_tokens=%s', source, self.provider.model, usage.get('promptTokenCount', 0), usage.get('candidatesTokenCount', 0))
                    return response
                except ProviderUnavailable as exc:
                    if exc.code == 429: self.cache.set(self.prefix + ':provider-cooldown', '1', ex=60)
                    raise HTTPException(503, 'บริการ AI ยังไม่พร้อมหรือถึงโควตาส่วนกลางแล้ว กรุณาลองภายหลัง', headers={'Retry-After': '60'}) from None
        except (HTTPException, StorageUnavailable): raise
        except Exception as exc:
            logger.warning('Advice unavailable: %s', type(exc).__name__)
            raise StorageUnavailable() from None
