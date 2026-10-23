"""Ensure the LLM rubric rejects the original vague temperature failure."""
import json
import os
from pathlib import Path
from advice_eval import EnergyQualityMetric
from deepeval.test_case import LLMTestCase
from large_data_fixtures import large_context

if __name__ == '__main__':
    context, owner = large_context()
    facts = context.get(owner, '2026-05')['facts']
    answer = dict(in_scope=True, summary='ตั้งอุณหภูมิให้เหมาะสม ไม่ต่ำเกินไป', actions=[dict(title='เปิดพัดลม', instruction='เปิดพัดลมและปิดประตูหน้าต่าง', reason='ช่วยกระจายความเย็น', scenario_id=None)], assumptions=[], missing_data=[])
    metric = EnergyQualityMetric(facts, os.getenv('ADVICE_JUDGE_MODEL', 'gemini-3.5-flash-lite'))
    metric.measure(LLMTestCase(input='ควรเปิดแอร์กี่องศาถึงจะประหยัดไฟ', actual_output=json.dumps(answer, ensure_ascii=False)))
    result = dict(expected_rejection=True, rejected=not metric.is_successful(), judge_model=metric.model, judge=metric.verdict)
    Path('tmp/eval/advice-specific/negative-control.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    assert result['rejected']
