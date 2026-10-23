import json
import logging
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import HTTPException
from gspread.exceptions import APIError
from app.electricity.service import ElectricityService, StorageUnavailable
from app.advice.context import digest
from app.advice.provider import PROMPT_VERSION
from app.advice.knowledge import VERSION

logger = logging.getLogger(__name__)


def make_candidate(owner, data, snapshot, answer, model, usage, history, guidance):
    # These are the exact sanitized inputs used for this generation, not later settings.
    inputs = {'question': data.question, 'topic': data.topic, 'context': snapshot,
              'history': history, 'guidance': guidance, 'knowledge_version': VERSION}
    return {'report_id': str(uuid4()), 'user_id': owner, 'billing_month': snapshot['facts']['month'],
        'input_hash': digest(inputs), 'input_snapshot_json': json.dumps(inputs, ensure_ascii=False, separators=(',', ':')),
        'analysis_json': json.dumps({'answer': answer, 'usage': usage,
            'generated_at': datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, separators=(',', ':')),
        'provider': 'gemini', 'model': model, 'prompt_version': PROMPT_VERSION,
        'calculation_version': 'energy-context-1', 'created_at': ''}


class Service(ElectricityService):
    def load(self):
        if self.cache.exists(self.prefix+':cooldown'): raise StorageUnavailable()
        try: return self.repository.load()
        except APIError as exc:
            if exc.code == 429: self.cache.set(self.prefix+':cooldown', '1', ex=10)
            raise

    def rows(self):
        raw = self.cache.get(self.cache_key)
        if raw is not None: return json.loads(raw)
        with self.sheet_lock() as guard:
            raw = self.cache.get(self.cache_key)
            if raw is not None: return json.loads(raw)
            rows, _ = self.load()
            guard(); self.store(rows)
            return rows

    def store(self, rows):
        self.cache.set(self.cache_key, json.dumps(rows, ensure_ascii=False), ex=30)

    @staticmethod
    def summary(row):
        inputs, analysis = json.loads(row['input_snapshot_json']), json.loads(row['analysis_json'])
        return {k: row[k] for k in ('report_id', 'billing_month', 'created_at', 'model')} | {
            'question': inputs['question'], 'summary': analysis['answer']['summary'], 'generated_at': analysis['generated_at']}

    def list(self, owner, month, page, size):
        rows = sorted((r for r in self.rows() if r['user_id'] == owner and (not month or r['billing_month'] == month)),
                      key=lambda r: (r['created_at'], r['report_id']), reverse=True)
        return {'items': [self.summary(r) for r in rows[(page-1)*size:page*size]], 'total': len(rows), 'page': page, 'page_size': size}

    def detail(self, owner, report_id):
        row = next((r for r in self.rows() if r['user_id'] == owner and r['report_id'] == report_id), None)
        if row is None: raise HTTPException(404, 'ไม่พบรายงานนี้')
        return self.summary(row) | {'input_snapshot': json.loads(row['input_snapshot_json']),
            'analysis': json.loads(row['analysis_json']), 'input_hash': row['input_hash'],
            'provider': row['provider'], 'prompt_version': row['prompt_version'], 'calculation_version': row['calculation_version']}

    def save(self, owner, report_id, advice):
        # Fast retry path avoids a Sheets read/write per click under concurrency.
        existing = next((r for r in self.rows() if r['user_id'] == owner and r['report_id'] == report_id), None)
        if existing: return self.summary(existing) | {'already_saved': True}
        raw = self.cache.get(advice.owner_key(owner)+':report-candidate:'+report_id)
        if not raw: raise HTTPException(404, 'คำตอบนี้หมดอายุสำหรับการบันทึกแล้ว หรือไม่ใช่ของบัญชีนี้ กรุณาถามใหม่')
        candidate = json.loads(raw)
        if candidate['user_id'] != owner or candidate['report_id'] != report_id: raise HTTPException(404, 'ไม่พบคำตอบนี้')
        if any(len(str(v).encode('utf-16-le'))//2 > 49000 for v in candidate.values()):
            raise HTTPException(422, 'ข้อมูลรายงานยาวเกินขนาดที่จัดเก็บได้')
        with self.sheet_lock() as guard:
            # Always refresh before mutation: recovers ambiguous writes and cross-worker retries.
            rows, next_row = self.load()
            old = next((r for r in rows if r['report_id'] == report_id), None)
            if old:
                if old['user_id'] != owner: raise HTTPException(404, 'ไม่พบคำตอบนี้')
                self.store(rows)
                return self.summary(old) | {'already_saved': True}
            candidate['created_at'] = datetime.now(timezone.utc).isoformat()
            guard(); self.cache.delete(self.cache_key)
            self.repository.insert(candidate, next_row, guard)
            try: guard(); self.store(rows+[candidate])
            except Exception: logger.warning('Report persisted; cache refresh failed')
            return self.summary(candidate) | {'already_saved': False}
