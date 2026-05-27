from datetime import datetime

from app.models.user import User

COLLEGE_CODE_MAP = {
    'sathyabama institute of science and technology': 'SIST',
}


def get_college_code(college_name):
    if not college_name:
        return 'SIST'
    key = college_name.lower().strip()
    if key in COLLEGE_CODE_MAP:
        return COLLEGE_CODE_MAP[key]
    words = college_name.split()
    if len(words) >= 2:
        return ''.join(w[0].upper() for w in words)
    return college_name[:4].upper()


def generate_participant_id(college_code=None, year=None):
    if college_code is None:
        college_code = 'SIST'
    if year is None:
        year = datetime.utcnow().year
    count = User.query.count()
    serial = str(count + 1).zfill(3)
    pid = f'{college_code}-{year}-{serial}'
    while User.query.filter_by(participant_id=pid).first():
        count += 1
        serial = str(count + 1).zfill(3)
        pid = f'{college_code}-{year}-{serial}'
    return pid
