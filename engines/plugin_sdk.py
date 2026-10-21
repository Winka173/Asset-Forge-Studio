"""Typed stage contracts; plugins expose only implemented hooks, never arbitrary code."""
from enum import StrEnum
from graphlib import TopologicalSorter, CycleError
from typing import Callable, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Operation(StrEnum):
    analyze='analyze'
    plan='plan'
    prepare='prepare'
    generate='generate'
    postprocess='postprocess'
    validate='validate'
    review='review'
    export='export'
    import_test='import_test'


class Stage(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id: str=Field(pattern=r'^[a-zA-Z0-9_-]{1,100}$')
    plugin: str
    operation: Operation
    depends_on: list[str]=Field(default_factory=list)
    resource: Literal['cpu','io','gpu','human']
    input_artifacts: list[str]=Field(default_factory=list)
    input_hashes: dict[str,str]=Field(default_factory=dict)
    expected_outputs: list[str]=Field(default_factory=list)
    skip_condition: str | None=None
    checkpoint: str
    recovery: Literal['retry_exact_config','reuse_verified_output','human_review']='retry_exact_config'
    requires_approval: bool=False
    acceptance: list[str]=Field(min_length=1)
    evidence_paths: list[str]=Field(default_factory=list)
    effective_config_hash: str | None=None
    status: Literal['planned','queued','running','validated','review_required','blocked','failed','cancelled']='planned'


class StageGraph(BaseModel):
    model_config=ConfigDict(extra='forbid')
    stages: list[Stage]

    @model_validator(mode='after')
    def valid_dag(self):
        ids={stage.id for stage in self.stages}
        if len(ids)!=len(self.stages):raise ValueError('Duplicate stage IDs')
        if any(dep not in ids for stage in self.stages for dep in stage.depends_on):raise ValueError('Unknown stage dependency')
        try:tuple(TopologicalSorter({stage.id:set(stage.depends_on) for stage in self.stages}).static_order())
        except CycleError as exc:raise ValueError('Stage dependency cycle') from exc
        return self


class Plugin:
    """Small hook dispatcher. A hook is executable code registered by trusted source only."""
    def __init__(self,identifier:str,hooks:dict[Operation,Callable]):
        self.id=identifier;self.hooks=dict(hooks)

    def invoke(self,operation:Operation,*args,**kwargs):
        if operation not in self.hooks:raise ValueError(f'{self.id} does not implement {operation}')
        return self.hooks[operation](*args,**kwargs)


def generation_plugin(identifier):
    # Reuse the proven subprocess adapter; no second inference implementation/queue.
    from .adapters import ADAPTERS
    adapter=ADAPTERS[identifier]
    return Plugin(identifier,{Operation.prepare:adapter.generate,Operation.validate:adapter.verify_outputs})
