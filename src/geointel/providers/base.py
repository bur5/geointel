from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class StructuredModel(Protocol):
    name: str

    def generate(self, role: str, payload: dict, output_type: type[T]) -> T: ...


class ModelRouter:
    def __init__(
        self,
        research_model: StructuredModel,
        reasoning_model: StructuredModel,
        fast_model: StructuredModel | None = None,
    ):
        self.research_model, self.reasoning_model = research_model, reasoning_model
        self.fast_model = fast_model or reasoning_model

    def for_role(self, role: str) -> StructuredModel:
        return (
            self.research_model
            if role == "research"
            else self.fast_model
            if role == "fast"
            else self.reasoning_model
        )

    def safe_config(self) -> dict:
        return {
            "research_model": self.research_model.name,
            "reasoning_model": self.reasoning_model.name,
            "fast_model": self.fast_model.name,
            "credentials_stored": False,
        }
