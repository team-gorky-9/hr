"""Structural same_as validation shared by loading, storage and assessment."""


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
