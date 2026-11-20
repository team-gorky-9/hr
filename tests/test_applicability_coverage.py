from scripts.report_profile_applicability import summarize


def test_coverage_counts_records_and_keeps_unresolved_separate():
    rows = [dict(posting_title='Сметчик', external_history_count=2),
            dict(posting_title=None, external_history_count=0),
            dict(posting_title='Консультант отдела кадровой работы', external_history_count=0)]
    result = summarize(rows)
    assert result['application_records'] == 3
    assert result['counts'] == {'confirmed': 0, 'mismatch': 1, 'unresolved': 2}
    assert result['eligible_primary_records'] == 0
    assert result['external_history_records'] == 2
    assert result['missing_posting_records'] == 1
