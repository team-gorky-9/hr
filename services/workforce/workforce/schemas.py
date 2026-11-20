import re
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def date_format(cls, value, info):
        if (
            info.field_name not in {"starts_on", "ends_on", "issued_on"}
            or value is None
            or type(value) is date
        ):
            return value
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Date must use YYYY-MM-DD")
        return value


class Revision(Input):
    expected_revision: Annotated[int, Field(ge=1, strict=True)]


class Login(Input):
    login: Code
    password: Annotated[str, Field(min_length=1, max_length=300)]


class Basis(Input):
    reference: Text
    issued_on: date


class Source(Input):
    system: Code
    id: Text


class DepartmentCreate(Input):
    code: Code
    name: Text
    parent_id: UUID | None = None


class DepartmentPatch(Revision):
    name: Text | None = None
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def not_null_name(self):
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class EmployeeCreate(Input):
    display_name: Text
    source_refs: Annotated[list[Source], Field(min_length=1, max_length=100)]
    account_actor_id: UUID | None = None
    confirmation_basis: Text


class EmployeePatch(Revision):
    display_name: Text | None = None
    account_actor_id: UUID | None = None
    correction_basis: Text

    @model_validator(mode="after")
    def not_null_name(self):
        if "display_name" in self.model_fields_set and self.display_name is None:
            raise ValueError("display_name cannot be null")
        return self


class AssignmentCreate(Input):
    department_id: UUID
    position_code: Code
    starts_on: date
    ends_on: date | None = None
    manager_employee_id: UUID | None = None
    basis: Basis


class End(Revision):
    ends_on: date
    reason: Text


class Transfer(Revision):
    ends_on: date
    new_department_id: UUID
    new_position_code: Code
    starts_on: date
    manager_employee_id: UUID | None = None
    basis: Basis


class Correct(Revision):
    starts_on: date | None = None
    ends_on: date | None = None
    manager_employee_id: UUID | None = None
    reason: Text
    basis: Basis

    @model_validator(mode="after")
    def not_null_start(self):
        if "starts_on" in self.model_fields_set and self.starts_on is None:
            raise ValueError("starts_on cannot be null")
        return self


class DelegationCreate(Input):
    manager_employee_id: UUID
    substitute_employee_id: UUID
    department_id: UUID
    starts_on: date
    ends_on: date
    basis: Basis


class NewEmployee(Input):
    display_name: Text


class Register(Revision):
    employee_id: UUID | None
    create_employee: NewEmployee | None
    identity_basis: Text

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.employee_id is None) == (self.create_employee is None):
            raise ValueError("Choose either an existing or a new employee")
        return self


class Reject(Revision):
    reason: Text


class Review(Revision):
    expected_assignment_revision: Annotated[int, Field(ge=1, strict=True)]
    decision: Literal["apply", "keep"]
    reason: Text | None = None

    @model_validator(mode="after")
    def explanation_for_keep(self):
        if self.decision == "keep" and self.reason is None:
            raise ValueError("Keeping the previous values requires an explanation")
        return self
