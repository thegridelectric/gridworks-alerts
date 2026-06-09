"""PascalCase aliases for GridWorks message payloads."""

from pydantic import BaseModel, ConfigDict, ValidationError


def snake_to_pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


class GwMessage(BaseModel):
    """Base for journal payloads keyed in PascalCase."""

    model_config = ConfigDict(
        extra="ignore",
        alias_generator=snake_to_pascal,
        populate_by_name=True,
    )

    @classmethod
    def from_dict(cls, data: dict) -> "GwMessage":
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise ValueError(f"Invalid {cls.__name__} payload: {e}") from e
