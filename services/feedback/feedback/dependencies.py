from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from feedback.store import authenticate, fail, transaction

security = HTTPBearer()


def context(request: Request, credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    with transaction(request.app.state.database_path) as db:
        yield db, authenticate(db, credentials.credentials)


Context = Annotated[tuple, Depends(context)]


def fixed_view(request: Request):
    if request.query_params:
        fail(422, "UNSUPPORTED_FILTER")
