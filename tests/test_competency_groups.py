from types import SimpleNamespace as Row

import pytest

from app.assessment.counters import aggregate_competency, aggregate_profile, validate_groups


def indicator(key, **kwargs):
    return Row(key=key, same_as=kwargs.get('same_as'),
               check_stage=kwargs.get('check_stage', 'screening'),
               is_mandatory=kwargs.get('is_mandatory', True),
               excluded_from_scoring=kwargs.get('excluded_from_scoring', False))


def test_conflict_is_one_mandatory_unit_with_manual_review():
    rows = [indicator('a', same_as='group', is_mandatory=False), indicator('b', same_as='group')]
    result = aggregate_competency(rows, {'a': 'confirmed', 'b': 'contradicted'})
    assert result.mandatory.total == 1
    assert result.mandatory.contradicted == 1
    assert result.desired.total == 0
    assert result.groups[0].manual_review is True


def test_interview_duplicates_and_excluded_do_not_enter_screening():
    rows = [indicator('a', same_as='group', check_stage='interview'),
            indicator('b', same_as='group', check_stage='interview'),
            indicator('c', excluded_from_scoring=True)]
    result = aggregate_competency(rows, {})
    assert result.mandatory.total == result.desired.total == 0
    assert result.on_interview == 1
    assert result.excluded == 1


@pytest.mark.parametrize('second', [dict(check_stage='interview'), dict(excluded_from_scoring=True)])
def test_invalid_group_is_configuration_error(second):
    rows = [indicator('a', same_as='group'), indicator('b', same_as='group', **second)]
    with pytest.raises(ValueError, match='same_as'):
        validate_groups([Row(key='c', indicators=rows)])


def test_cross_competency_group_is_rejected():
    with pytest.raises(ValueError, match='same_as'):
        validate_groups([Row(key='c1', indicators=[indicator('a', same_as='g')]),
                         Row(key='c2', indicators=[indicator('b', same_as='g')])])


def test_profile_totals_sum_units_without_turning_legacy_into_zero():
    first = aggregate_competency([indicator('a', same_as='g'), indicator('b', same_as='g')],
                                {'a': 'confirmed'})
    second = aggregate_competency([indicator('c', is_mandatory=False)], {})
    total = aggregate_profile([first, second])
    assert total.mandatory.confirmed == total.mandatory.total == 1
    assert total.desired.no_info == total.desired.total == 1
    assert aggregate_profile([first, None]) is None
