from uuid import UUID

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from workforce.api import authenticate
from workforce.domain import lock_organization, serialize
from workforce.onboarding import schemas as s
from workforce.onboarding.models import Template
from workforce.onboarding.service import Onboarding, reader
from workforce.schemas import Revision

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])


@router.get("/templates", response_model=s.Templates)
def templates(request: Request):
    with Session(request.app.state.engine) as session:
        reader(authenticate(session, request))
        return {
            "items": [
                serialize(row)
                for row in session.scalars(select(Template).order_by(Template.code, Template.version))
            ]
        }


@router.get("/programs", response_model=s.Programs)
def programs(request: Request):
    with Session(request.app.state.engine) as session:
        return Onboarding(session, authenticate(session, request)).list()


@router.get("/programs/{id}", response_model=s.ProgramView)
def program(id: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        service = Onboarding(session, authenticate(session, request))
        return service.view(service.get(id))


@router.post(
    "/programs",
    response_model=s.ProgramView,
    status_code=201,
    responses={200: {"model": s.ProgramView, "description": "Existing assignment of this template"}},
)
def assign(body: s.Assign, request: Request, response: Response):
    with Session(request.app.state.engine) as session, session.begin():
        actor = authenticate(session, request)
        lock_organization(session, actor.organization_id)
        result, response.status_code = Onboarding(session, actor).assign(body)
        return result


@router.post("/programs/{id}/steps/{key}/acknowledge", response_model=s.ProgramView)
def acknowledge(id: UUID, key: str, body: Revision, request: Request):
    with Session(request.app.state.engine) as session, session.begin():
        actor = authenticate(session, request)
        lock_organization(session, actor.organization_id)
        return Onboarding(session, actor).acknowledge(id, key, body)


@router.post("/programs/{id}/cancel", response_model=s.ProgramView)
def cancel(id: UUID, body: s.Cancel, request: Request):
    with Session(request.app.state.engine) as session, session.begin():
        actor = authenticate(session, request)
        lock_organization(session, actor.organization_id)
        return Onboarding(session, actor).cancel(id, body)
