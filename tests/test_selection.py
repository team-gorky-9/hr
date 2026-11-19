import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.db import repository as repo
from app.db.enums import ApplicationSource, FeedbackOutcome, ReserveStatus
from app.db.models import Application, Position
from tests.factories import make_candidate, position, vacancy


def test_new_application_starts_at_first_stage_with_event(session):
    candidate = make_candidate(session, "py-0100")
    application = repo.create_application(
        session, candidate_id=candidate.id, vacancy_id=vacancy(session).id, source=ApplicationSource.RESPONSE
    )
    assert application.current_stage_code == "new"
    history = repo.stage_history(session, application.id)
    assert [(e.from_stage_code, e.to_stage_code) for e in history] == [(None, "new")]


def test_full_path_to_rejection_is_recorded(session):
    candidate = make_candidate(session, "py-0101")
    application = repo.create_application(
        session, candidate_id=candidate.id, vacancy_id=vacancy(session).id, source=ApplicationSource.RESPONSE
    )
    for stage in ["screening", "phone_interview", "sent_to_department", "department_interview"]:
        repo.move_application(session, application.id, stage)
    repo.move_application(
        session, application.id, "rejected", rejection_reason_code="competencies", comment="мало опыта с async"
    )
    history = repo.stage_history(session, application.id)
    assert [e.to_stage_code for e in history] == [
        "new", "screening", "phone_interview", "sent_to_department", "department_interview", "rejected",
    ]
    assert history[-1].rejection_reason_code == "competencies"
    assert application.current_stage_code == "rejected"


def test_no_moves_after_final_stage(session):
    application = repo.create_application(
        session, candidate_id=make_candidate(session, "py-0102").id, vacancy_id=vacancy(session).id,
        source=ApplicationSource.RESPONSE,
    )
    repo.move_application(session, application.id, "withdrawn", rejection_reason_code="no_response")
    with pytest.raises(repo.StageTransitionError):
        repo.move_application(session, application.id, "screening")


@pytest.mark.parametrize(
    ("stage", "reason"),
    [("unknown_stage", None), ("new", None), ("screening", "competencies"), ("rejected", "no_such_reason")],
)
def test_invalid_transitions_are_refused(session, stage, reason):
    application = repo.create_application(
        session, candidate_id=make_candidate(session, "py-0103").id, vacancy_id=vacancy(session).id,
        source=ApplicationSource.RESPONSE,
    )
    with pytest.raises(repo.StageTransitionError):
        repo.move_application(session, application.id, stage, rejection_reason_code=reason)
    assert application.current_stage_code == "new"


def test_application_to_external_position_from_history(session):
    application = repo.create_application(
        session, candidate_id=make_candidate(session, "hr-0104").id, source=ApplicationSource.HISTORY,
        external_position_title="Консультант отдела кадровой работы", applied_at=date(2026, 8, 25),
    )
    assert application.vacancy_id is None


def test_application_needs_target(session):
    candidate = make_candidate(session, "py-0105")
    with pytest.raises(repo.RepositoryError):
        repo.create_application(session, candidate_id=candidate.id, source=ApplicationSource.MANUAL)
    # То же правило держит сама база, если вставлять в обход функций.
    session.add(Application(candidate_id=candidate.id, source=ApplicationSource.MANUAL, current_stage_code="new"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_one_application_per_vacancy(session):
    candidate = make_candidate(session, "py-0106")
    repo.create_application(session, candidate_id=candidate.id, vacancy_id=vacancy(session).id, source=ApplicationSource.RESPONSE)
    with pytest.raises(IntegrityError):
        repo.create_application(
            session, candidate_id=candidate.id, vacancy_id=vacancy(session).id, source=ApplicationSource.MANUAL
        )


def test_department_feedback_does_not_move_stage(session):
    application = repo.create_application(
        session, candidate_id=make_candidate(session, "py-0107").id, vacancy_id=vacancy(session).id,
        source=ApplicationSource.RESPONSE,
    )
    repo.move_application(session, application.id, "sent_to_department")
    feedback = repo.record_department_feedback(
        session, application.id, outcome=FeedbackOutcome.NOT_FIT, interview_held=True,
        confirmed_competencies=["ИТК"], gaps="нет опыта с обращениями граждан",
        rejection_reason_code="experience", keep_in_reserve=True,
    )
    assert feedback.confirmed_competencies == ["ИТК"]
    assert application.current_stage_code == "sent_to_department"


def test_reserve_has_no_duplicates_and_respects_expiry(session):
    candidate = make_candidate(session, "py-0108")
    pos = position(session)
    first = repo.add_to_reserve(session, candidate_id=candidate.id, position_id=pos.id, reason="хорош, но позже")
    again = repo.add_to_reserve(session, candidate_id=candidate.id, position_id=pos.id)
    assert first.id == again.id

    expired = repo.add_to_reserve(
        session, candidate_id=make_candidate(session, "py-0109", text="Другой").id, position_id=pos.id,
        valid_until=date.today() - timedelta(days=1),
    )
    withdrawn = repo.add_to_reserve(
        session, candidate_id=make_candidate(session, "py-0110", text="Третий").id, position_id=pos.id,
    )
    withdrawn.status = ReserveStatus.WITHDRAWN
    session.flush()

    found = repo.reserve_for_position(session, pos.id)
    assert [e.id for e in found] == [first.id]
    assert expired.id not in {e.id for e in found}


def test_reserve_needs_target(session):
    with pytest.raises(repo.RepositoryError):
        repo.add_to_reserve(session, candidate_id=make_candidate(session, "py-0111").id)


def test_unknown_id_gives_clear_error(session):
    with pytest.raises(repo.RepositoryError, match="кандидат"):
        repo.create_application(session, candidate_id=uuid.uuid4(), source=ApplicationSource.MANUAL,
                                external_position_title="Аналитик")
    with pytest.raises(repo.StageTransitionError, match="нет отклика"):
        repo.move_application(session, uuid.uuid4(), "screening")


def test_position_with_reserve_cannot_be_deleted(session):
    """`reserve_entries.position_id` объявлен SET NULL, но CHECK «должность или направление»
    не даёт обнулить его у записи без направления: удаление должности отклоняется (контракт, п. 4.5)."""
    pos = position(session)
    repo.add_to_reserve(session, candidate_id=make_candidate(session, "py-0112").id, position_id=pos.id)
    savepoint = session.begin_nested()
    with pytest.raises(IntegrityError, match="ck_reserve_entries_has_target"):
        session.execute(delete(Position).where(Position.id == pos.id))
    savepoint.rollback()
