"""Profile validation and deterministic same_as aggregation."""
from collections import defaultdict

from app.schemas.competency_details import CompetencyDetails, GroupResult, ProfileCounters


def validate_groups(competencies) -> None:
    groups = {}
    for competency in competencies:
        for row in competency.indicators:
            key = getattr(row, 'same_as', None)
            if key is None:
                continue
            if not key.strip() or row.excluded_from_scoring:
                raise ValueError(f'same_as {key!r}: excluded or empty group')
            identity = (competency.key, row.check_stage)
            if key in groups and groups[key] != identity:
                raise ValueError(f'same_as {key}: members must share competency and check_stage')
            groups[key] = identity


def aggregate_competency(indicators, statuses: dict[str, str]) -> CompetencyDetails:
    result = CompetencyDetails()
    units = defaultdict(list)
    for row in indicators:
        if row.excluded_from_scoring:
            result.excluded += 1
        else:
            # Prefix prevents a row key from colliding with a group key.
            group = getattr(row, 'same_as', None)
            units[('group', group) if group else ('row', row.key)].append(row)
    for (_, key), rows in units.items():
        if rows[0].check_stage == 'interview':
            result.on_interview += 1
            continue
        values = {statuses.get(row.key, 'no_info') for row in rows}
        if not values <= {'confirmed', 'contradicted', 'no_info'}:
            raise ValueError('unsupported indicator status')
        status = 'contradicted' if 'contradicted' in values else ('confirmed' if 'confirmed' in values else 'no_info')
        mandatory = any(row.is_mandatory for row in rows)
        counter = result.mandatory if mandatory else result.desired
        counter.total += 1
        setattr(counter, status, getattr(counter, status) + 1)
        result.groups.append(GroupResult(key=key, members=[r.key for r in rows], is_mandatory=mandatory,
                                         status=status, manual_review={'confirmed', 'contradicted'} <= values))
    return result


def aggregate_profile(details: list[CompetencyDetails | None]) -> ProfileCounters | None:
    if any(item is None for item in details):
        return None
    result = ProfileCounters()
    for item in details:
        for bucket in ('mandatory', 'desired'):
            source, target = getattr(item, bucket), getattr(result, bucket)
            for field in ('confirmed', 'contradicted', 'no_info', 'total'):
                setattr(target, field, getattr(target, field) + getattr(source, field))
        result.on_interview += item.on_interview
        result.excluded += item.excluded
        result.manual_review_groups += sum(g.manual_review for g in item.groups)
    return result
