from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,49}$")]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Revision(Input):
    expected_revision: Annotated[StrictInt, Field(ge=1)]


class Question(Input):
    key: Key
    text: Text
    min: Annotated[StrictInt, Field(ge=0, le=100)]
    max: Annotated[StrictInt, Field(ge=1, le=100)]

    @model_validator(mode="after")
    def valid_range(self):
        if self.min >= self.max:
            raise ValueError("Invalid range")
        return self


class Topic(Input):
    key: Key
    label: Text


class Group(Topic):
    eligible_count: Annotated[StrictInt, Field(ge=1, le=100000)]


class CycleCreate(Input):
    title: Text
    question_version: Text
    questions: Annotated[list[Question], Field(min_length=1, max_length=50)]
    topic_options: Annotated[list[Topic], Field(min_length=1, max_length=50)]
    groups: Annotated[list[Group], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def unique_keys(self):
        for values in (self.questions, self.topic_options, self.groups):
            if len({item.key for item in values}) != len(values):
                raise ValueError("Duplicate keys")
        return self


class CodeIssue(Input):
    group_key: Key
    count: Annotated[StrictInt, Field(ge=1, le=1000)]


class Answer(Input):
    question_key: Key
    value: StrictInt


class ResponseCreate(Input):
    access_code: Annotated[str, Field(min_length=20, max_length=200)]
    answers: Annotated[list[Answer], Field(min_length=1, max_length=50)]
    topic_key: Key


class Policy(Input):
    k: Annotated[StrictInt, Field(ge=2, le=100000)]


class PublicationCreate(Revision):
    policy: Policy
    policy_basis: Text
