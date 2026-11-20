"""Safe, stable errors at the requirements boundary."""


class RequirementError(ValueError):
    def __init__(self, code: str, message: str, path: str | None = None):
        super().__init__(message)
        self.code = code
        self.path = path

    def as_dict(self):
        return {'code': self.code, 'message': str(self), 'path': self.path}


def invalid(path='profile'):
    return RequirementError('invalid_profile', 'Профиль не соответствует схеме; проверьте указанное поле.', path)
