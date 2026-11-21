from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session

from workforce.api import authenticate
from workforce.development import schemas as s
from workforce.development.service import Development
from workforce.domain import lock_organization, serialize

router = APIRouter(
    prefix="/api/v1/development",
    tags=["development"],
    dependencies=[Depends(HTTPBearer(auto_error=False))],
    responses={status: {"model": s.ErrorResponse} for status in (401, 403, 404, 409, 422, 503)},
)


def service(request: Request):
    with Session(request.app.state.engine) as session, session.begin():
        actor = authenticate(session, request)
        if request.method not in {"GET", "HEAD"}:
            lock_organization(session, actor.organization_id)
        yield Development(session, actor)


Service = Annotated[Development, Depends(service, scope="function")]


@router.post("/goals", response_model=s.GoalView, status_code=201)
def create_goal(body: s.GoalCreate, service: Service):
    return service.create_goal(body)


@router.get("/goals", response_model=s.Goals)
def goals(service: Service):
    return service.goals()


@router.get("/goals/{id}", response_model=s.GoalView)
def goal(id: UUID, service: Service):
    return serialize(service.goal(id))


@router.patch("/goals/{id}", response_model=s.GoalView)
def patch_goal(id: UUID, body: s.GoalPatch, service: Service):
    return service.patch_goal(id, body)


@router.post("/goals/{id}/share", response_model=s.GoalView)
def share_goal(id: UUID, body: s.Share, service: Service):
    return service.share_goal(id, body)


@router.post("/plans", response_model=s.PlanView, status_code=201)
def create_plan(body: s.PlanCreate, service: Service):
    return service.create_plan(body)


@router.get("/plans", response_model=s.Plans)
def plans(service: Service):
    return service.plans()


@router.get("/plans/{id}", response_model=s.PlanView)
def plan(id: UUID, service: Service):
    return serialize(service.plan(id))


@router.patch("/plans/{id}", response_model=s.PlanView)
def patch_plan(id: UUID, body: s.PlanPatch, service: Service):
    return service.patch_plan(id, body)


@router.post("/plans/{id}/respond", response_model=s.PlanView)
def respond(id: UUID, body: s.Respond, service: Service):
    return service.respond(id, body)


@router.post("/plans/{id}/submissions", response_model=s.SubmissionView, status_code=201)
def submit(id: UUID, body: s.SubmissionCreate, service: Service):
    return service.submit(id, body)


@router.get("/plans/{id}/submissions", response_model=s.Submissions)
def submissions(id: UUID, service: Service):
    return service.submissions(id)


@router.post(
    "/submissions/{id}/review",
    response_model=s.ReviewView,
    status_code=201,
    responses={200: {"model": s.ReviewView, "description": "Existing identical review"}},
)
def review(id: UUID, body: s.ReviewCreate, service: Service, response: Response):
    result, response.status_code = service.review(id, body)
    return result


@router.get("/plans/{id}/progress", response_model=s.Progress)
def progress(id: UUID, service: Service):
    return service.progress(id)


@router.post("/plans/{id}/close", response_model=s.PlanView)
def close(id: UUID, body: s.Close, service: Service):
    return service.close(id, body)


@router.post("/plans/{id}/share-result", response_model=s.PackageView)
def share_result(id: UUID, body: s.ShareResult, service: Service):
    return service.share_result(id, body)


@router.get("/result-packages/{id}", response_model=s.PackageView)
def package(id: UUID, service: Service):
    return service.package(id)
