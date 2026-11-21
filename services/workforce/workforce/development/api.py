from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from workforce.api import authenticate
from workforce.development import schemas as s
from workforce.development.service import Development
from workforce.domain import lock_organization, serialize

router = APIRouter(prefix="/api/v1/development", tags=["development"])


def service(request: Request):
    with Session(request.app.state.engine) as session, session.begin():
        actor = authenticate(session, request)
        if request.method not in {"GET", "HEAD"}:
            lock_organization(session, actor.organization_id)
        yield Development(session, actor)


Service = Annotated[Development, Depends(service)]


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
