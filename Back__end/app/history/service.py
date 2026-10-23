from decimal import Decimal, ROUND_HALF_UP
from .schemas import HistoryRecord

MONTHS = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
          'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
FULL_MONTHS = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
               'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']


def normalize(value):
    value = value.translate(str.maketrans('๐๑๒๓๔๕๖๗๘๙', '0123456789')).lower()
    return ''.join(character for character in value if not character.isspace() and character not in './-')


def history(storage, user_id, query='', year=None, page=1, page_size=6):
    # Ownership filtering happens before comparisons, search and all metadata.
    records = storage.list_records(user_id)
    by_month = {record.billing_month: record for record in records}
    years = sorted({int(record.billing_month[:4]) for record in records}, reverse=True)
    matches = []
    needle = normalize(query)
    for record in records:
        record_year, month = map(int, record.billing_month.split('-'))
        if year is not None and record_year != year:
            continue
        labels = [record.billing_month, f'{month:02d}/{record_year}',
                  f'{month:02d}/{record_year + 543}',
                  f'{MONTHS[month-1]} {record_year+543}', f'{FULL_MONTHS[month-1]} {record_year+543}',
                  f'{MONTHS[month-1]} {record_year}', f'{FULL_MONTHS[month-1]} {record_year}']
        if needle and not any(needle in normalize(label) for label in labels):
            continue
        matches.append(record)
    total = len(matches)
    total_pages = (total + page_size - 1) // page_size
    page = min(page, max(1, total_pages))
    result = []
    for record in matches[(page-1)*page_size:page*page_size]:
        record_year, month = map(int, record.billing_month.split('-'))
        previous_month = f'{record_year-1:04d}-12' if month == 1 else f'{record_year:04d}-{month-1:02d}'
        previous = by_month.get(previous_month)
        change = None
        if previous is not None and previous.total_cost != 0:
            change = ((record.total_cost - previous.total_cost) / previous.total_cost * Decimal(100)).quantize(
                Decimal('0.1'), rounding=ROUND_HALF_UP)
        result.append(HistoryRecord(**record.model_dump(), change_percent=change))
    return dict(records=result, total=total, page=page, page_size=page_size,
                total_pages=total_pages, available_years=years)
