from decimal import Decimal
from large_data_fixtures import large_context
from app.dashboard.service import dashboard
from app.history.service import history
from app.analysis.service import AnalysisService
from app.advice.export_prompt import render_body

def test_full_24_row_dataset_all_summary_paths_agree():
    ctx,owner=large_context();f=ctx.get(owner,'2026-05')['facts']
    assert f['device_totals']['items']==24 and f['device_totals']['estimated_items']==22 and f['device_totals']['unknown_items']==2
    assert Decimal(f['device_totals']['estimated_kwh'])==Decimal('247.55') and f['device_totals']['meter_kwh']==285
    assert len(f['devices'])==20 and len(f['scenarios'])==3
    assert Decimal(f['budget']['gap_baht'])==330 and Decimal(f['budget']['target_kwh_reduction'])==Decimal('41.25')
    assert Decimal(f['budget']['reduction_percent'])==Decimal('14.16')
    assert any('ยี่สิบ' in text for text in f['missing_data'])
    page1=history(ctx.electricity,owner,page=1);page4=history(ctx.electricity,owner,page=4)
    assert page1['total']==24 and page4['total_pages']==4 and len(page4['records'])==6
    assert dashboard(ctx.electricity,owner,'2026-05')['units_used']==285
    for n in (3,6,12):
        a=AnalysisService(ctx.electricity,ctx.appliances).get(owner,n,'2026-05')
        assert len(a['series'])==n and len(a['appliances'])==24
        assert a['appliance_summary']['unknown_items']==2
    prompt=render_body(f)
    assert '247.55' in prompt and '285' in prompt and '24' in prompt and '20' in prompt

def test_large_mismatch_and_missing_month_remain_explicit():
    ctx,owner=large_context(mismatch=True);f=ctx.get(owner,'2026-05')['facts']
    assert Decimal(f['device_totals']['difference_kwh'])==Decimal('147.55')
    missing=ctx.get(owner,'2026-06')['facts']
    assert missing['bill'] is None and missing['devices']==[] and missing['device_totals']['items']==0
