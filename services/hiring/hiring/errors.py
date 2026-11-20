"""Error envelope of wave-1-common: {"error": {code, message, field, request_id}}."""


class Problem(Exception):
    def __init__(self, status: int, code: str, message: str, field: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.field = field


def not_found(what: str = "Object") -> Problem:
    # Hidden objects of another organization or case look exactly like missing ones.
    return Problem(404, "NOT_FOUND", f"{what} not found")


def forbidden(message: str = "Role is not allowed to do this") -> Problem:
    return Problem(403, "FORBIDDEN", message)


def invalid_state(message: str, field: str | None = None) -> Problem:
    return Problem(409, "INVALID_STATE", message, field)


def stale(field: str = "expected_revision") -> Problem:
    return Problem(409, "STALE_REVISION", "The object was changed by someone else; reload it", field)
