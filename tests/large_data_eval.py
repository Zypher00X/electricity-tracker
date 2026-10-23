"""Explicit DeepEval run over synthetic 24-device / 24-bill data only."""
import json
import os
import sys
from pathlib import Path
from advice_eval import ContractMetric,EnergyQualityMetric
from deepeval.test_case import LLMTestCase
from app.advice.provider import Gemini,PROMPT_VERSION
from app.advice.context import digest
from app.advice.knowledge import relevant
from large_data_fixtures import large_context

if __name__=='__main__':
    context,owner=large_context();base=context.get(owner,'2026-05')['facts']
    mismatch,other=large_context(mismatch=True)
    cases=[('overview','ช่วยวิเคราะห์ภาพรวมค่าไฟและจุดที่ควรเริ่มประหยัด',base),
        ('budget','อยากลดค่าไฟให้ถึงงบ ควรทำอย่างไร?',base),
        ('plan','ช่วยวางแผนประหยัดไฟที่เริ่มทำได้ในเจ็ดวัน',base),
        ('mismatch','ช่วยวิเคราะห์ค่าไฟ โดยเริ่มจากตรวจความสอดคล้องของประมาณการเครื่องใช้กับมิเตอร์ก่อน แล้วค่อยเสนอแนวทางประหยัด',mismatch.get(other,'2026-05')['facts']),
        ('unknown','เครื่องพิมพ์และเครื่องเย็บผ้าที่ไม่ทราบกำลังไฟ ควรคิดเป็นศูนย์ไหม และมีข้อมูลเครื่องใช้ทั้งหมดหรือยัง',base)]
    provider=Gemini();out=Path('tmp/eval/large-data');out.mkdir(parents=True,exist_ok=True);results=[]
    for name,question,facts in cases:
        signature=digest([question,facts,PROMPT_VERSION,provider.model]);target=out/(name+'.json')
        saved=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
        if saved.get('signature')==signature:answer,usage=saved['answer'],saved['usage']
        else:
            answer,usage=provider.generate(question,facts,[],relevant(name,[r['category'] for r in facts['devices']]))
            target.write_text(json.dumps({'signature':signature,'answer':answer,'usage':usage},ensure_ascii=False,indent=2),encoding='utf-8')
        case=LLMTestCase(input=question,actual_output=json.dumps(answer,ensure_ascii=False),retrieval_context=[json.dumps(facts,ensure_ascii=False)])
        contract=ContractMetric(facts);contract.measure(case)
        metric=EnergyQualityMetric(facts,os.getenv('ADVICE_JUDGE_MODEL','gemini-3.6-flash'));metric.measure(case)
        result={'case':name,'signature':signature,'answer':answer,'usage':usage,'contract_pass':contract.is_successful(),'quality_pass':metric.is_successful(),'quality_score':metric.score,'judge':metric.verdict}
        target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');results.append(result)
        print(json.dumps({k:result[k] for k in ('case','contract_pass','quality_pass','quality_score')}),flush=True)
    summary={'framework':'DeepEval custom metrics','synthetic_only':True,'model':provider.model,'judge_model':os.getenv('ADVICE_JUDGE_MODEL','gemini-3.6-flash'),
        'prompt_version':PROMPT_VERSION,'passed':sum(r['contract_pass'] and r['quality_pass'] for r in results),'total':len(results),'results':results}
    (out/'results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    sys.exit(0 if summary['passed']==summary['total'] else 1)
