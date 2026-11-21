"""Versioned tasks, immutable student attempts and mentor reviews."""
from typing import Literal
from uuid import UUID

from pydantic import Field, HttpUrl, StrictBool, model_validator

from .api import ActorDep, PREFIX
from .core import active, check_revision, fail, mentor_available, now, organizer, read_placement, require
from .schemas import Input, Nonempty, Reason


class Criterion(Input):
    key: Nonempty
    text: Nonempty
    required: StrictBool


class TaskIn(Input):
    title: Nonempty
    description: Nonempty
    criteria: list[Criterion] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_keys(self):
        if len({c.key for c in self.criteria}) != len(self.criteria):
            raise ValueError("Ключи критериев повторяются")
        return self


class SubmissionIn(Input):
    task_version_id: UUID
    text: Nonempty
    artifact_url: HttpUrl | None = None


class CriterionResult(Input):
    criterion_key: Nonempty
    result: Literal["confirmed", "needs_revision", "not_verified"]
    reason: Nonempty


class ReviewIn(Input):
    results: list[CriterionResult] = Field(min_length=1)


class MentorIn(Reason):
    mentor_actor_id: UUID


def related(unit, kind, placement_id):
    return [r for r in unit.all(kind) if r["placement_id"] == str(placement_id)]


def current_task(unit, placement_id):
    tasks = related(unit, "task", placement_id)
    if not tasks:
        fail("TASK_REQUIRED", "Наставник ещё не опубликовал задание.")
    return max(tasks, key=lambda t: t["version"])


def latest_results(unit, placement_id):
    tasks = related(unit, "task", placement_id)
    if not tasks:
        return None, None, None
    task = max(tasks, key=lambda t: t["version"])
    submissions = [s for s in related(unit, "submission", placement_id) if s["task_version_id"] == task["id"]]
    if not submissions:
        return task, None, None
    submission = max(submissions, key=lambda s: s["attempt_no"])
    review = next((r for r in related(unit, "review", placement_id) if r["submission_id"] == submission["id"]), None)
    return task, submission, review


def work_state(unit, placement_id):
    task, submission, review = latest_results(unit, placement_id)
    if task is None:
        return "task_required"
    if submission is None:
        return "awaiting_submission"
    if review is None:
        return "awaiting_review"
    outcomes = {r["result"] for r in review["results"]}
    if "needs_revision" in outcomes:
        return "needs_revision"
    if "not_verified" in outcomes:
        return "not_verified"
    return "confirmed"


def install(app, store):
    @app.post(PREFIX + "/placements/{ident}/tasks", status_code=201)
    def create_task(ident: UUID, body: TaskIn, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            placement = read_placement(unit, ident)
            require(placement["mentor_actor_id"] == actor["actor_id"])
            active(placement)
            if related(unit, "submission", ident):
                fail("TASK_ALREADY_SUBMITTED", "После первой сдачи нельзя менять критерии этого пути.")
            tasks = related(unit, "task", ident)
            return unit.save("task", {**body.model_dump(mode="json"), "placement_id": str(ident),
                             "version": max((t["version"] for t in tasks), default=0) + 1}, "task_published")

    @app.get(PREFIX + "/placements/{ident}/tasks")
    def tasks(ident: UUID, actor: ActorDep):
        with store.transaction(actor) as unit:
            read_placement(unit, ident)
            rows = sorted(related(unit, "task", ident), key=lambda t: t["version"])
            return {"current": rows[-1] if rows else None, "items": rows}

    @app.post(PREFIX + "/placements/{ident}/submissions", status_code=201)
    def submit(ident: UUID, body: SubmissionIn, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            placement = read_placement(unit, ident)
            require(placement["student_actor_id"] == actor["actor_id"])
            active(placement)
            task = current_task(unit, ident)
            if task["id"] != str(body.task_version_id):
                fail("TASK_VERSION_MISMATCH", "Выберите опубликованную версию задания этого участия.")
            attempts = related(unit, "submission", ident)
            return unit.save("submission", {**body.model_dump(mode="json"), "placement_id": str(ident),
                "attempt_no": max((s["attempt_no"] for s in attempts), default=0) + 1,
                "submitted_at": now(), "submitted_by": actor["actor_id"],
                "artifact_source": "external_mutable_link" if body.artifact_url else "saved_text"}, "submitted")

    @app.get(PREFIX + "/placements/{ident}/submissions")
    def submissions(ident: UUID, actor: ActorDep):
        with store.transaction(actor) as unit:
            read_placement(unit, ident)
            reviews = related(unit, "review", ident)
            rows = sorted(related(unit, "submission", ident), key=lambda s: s["attempt_no"])
            return {"items": [{**s, "review": next((r for r in reviews if r["submission_id"] == s["id"]), None)} for s in rows],
                    "work_state": work_state(unit, ident)}

    @app.post(PREFIX + "/submissions/{ident}/review")
    def review(ident: UUID, body: ReviewIn, actor: ActorDep):
        with store.transaction(actor, True) as unit:
            submission = unit.get("submission", ident)
            placement = read_placement(unit, submission["placement_id"])
            require(placement["mentor_actor_id"] == actor["actor_id"])
            active(placement)
            task = unit.get("task", submission["task_version_id"])
            results = sorted(body.model_dump(mode="json")["results"], key=lambda r: r["criterion_key"])
            keys = [r["criterion_key"] for r in results]
            if len(keys) != len(set(keys)) or set(keys) != {c["key"] for c in task["criteria"]}:
                fail("INVALID_CRITERIA", "Нужен один результат по каждому критерию именно этой версии.", 422)
            existing = next((r for r in related(unit, "review", placement["id"]) if r["submission_id"] == str(ident)), None)
            if existing:
                if existing["results"] == results and existing["reviewed_by"] == actor["actor_id"]:
                    return existing
                fail("REVIEW_ALREADY_RECORDED", "Отзыв сохранён; иной итог требует новой попытки.")
            return unit.save("review", {"placement_id": placement["id"], "submission_id": str(ident),
                 "task_version_id": task["id"], "reviewed_by": actor["actor_id"], "reviewed_at": now(), "results": results}, "reviewed")

    @app.post(PREFIX + "/placements/{ident}/mentor")
    def replace_mentor(ident: UUID, body: MentorIn, actor: ActorDep):
        require(organizer(actor))
        store.mentor(actor, body.mentor_actor_id)
        with store.transaction(actor, True) as unit:
            placement = read_placement(unit, ident)
            check_revision(placement, body.expected_revision)
            active(placement)
            mentor_available(unit, str(body.mentor_actor_id), placement["starts_on"], placement["ends_on"],
                             store.settings.mentor_capacity, excluding=placement["id"])
            placement["mentor_actor_id"] = str(body.mentor_actor_id)
            placement["mentor_change_reason"] = body.reason
            return unit.save("placement", placement, "mentor_changed")
