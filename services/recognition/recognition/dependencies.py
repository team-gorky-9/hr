from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from recognition.store import authenticate, transaction

security = HTTPBearer()


def context(request: Request, credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    with transaction(request.app.state.database_path) as db:
        yield db, authenticate(db, credentials.credentials)


Context = Annotated[tuple, Depends(context)]
Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[UUID | None, Query()]
