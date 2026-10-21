"""Versioned interchange metadata; native engine files retain their own formats."""
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from engines.plugin_sdk import StageGraph
from engines.quality import fingerprint


class AssetType(StrEnum):
    static_3d='static_3d'
    character='character'
    animation='animation'
    map_environment='map_environment'
    vfx='vfx'
    material='material'
    sprite_2d='sprite_2d'
    ui='ui'
    audio='audio'
    cinematic='cinematic'


class ArtifactFile(BaseModel):
    model_config=ConfigDict(extra='forbid')
    artifact_id: str | None=None
    path: str
    sha256: str=Field(pattern=r'^[a-f0-9]{64}$')
    bytes: int=Field(ge=0)
    role: str
    integrity: Literal['recorded','verified']='recorded'

    @model_validator(mode='after')
    def local_path(self):
        from pathlib import PurePosixPath
        if '\\' in self.path or ':' in self.path or PurePosixPath(self.path).is_absolute() or '..' in PurePosixPath(self.path).parts:
            raise ValueError('Manifest file paths must be relative to the library')
        return self


class Provenance(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_code: str='UNKNOWN'
    model_weights: str='UNKNOWN'
    input_asset_rights: str='UNKNOWN'
    commercial: Literal['blocked','review_required','cleared']='review_required'
    evidence: list[str]=Field(default_factory=list)
    restrictions: list[str]=Field(default_factory=list)


class AssetManifest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_version: Literal['2.0']='2.0'
    project_id: str
    asset_id: str
    asset_type: AssetType=AssetType.static_3d
    family_id: str | None=None
    version: str
    status: Literal['draft','source_generated','exported','imported','engine_validated','human_approved','game_ready']='draft'
    target_engines: list[Literal['unity','unreal']]=Field(default_factory=list)
    units: Literal['m','cm']='m'
    coordinate_system: str='per_file; GLB/FBX Y-up, Blender source Z-up; native conversion must be verified'
    prompt: str=''
    references: list[ArtifactFile]=Field(default_factory=list)
    art_bible: dict=Field(default_factory=dict)
    golden_reference_ids: list[str]=Field(default_factory=list)
    effective_configs: list[dict]=Field(default_factory=list)
    effective_config_hashes: list[str]=Field(default_factory=list)
    graph: StageGraph
    source_master: ArtifactFile | None=None
    candidates: list[ArtifactFile]=Field(default_factory=list)
    derivatives: list[ArtifactFile]=Field(default_factory=list)
    expected_outputs: list[str]=Field(default_factory=list)
    actual_outputs: list[ArtifactFile]=Field(default_factory=list)
    licenses: list[Provenance]=Field(default_factory=list)
    toolchain_versions: dict[str,str]=Field(default_factory=dict)
    import_tests: list[dict]=Field(default_factory=list)
    previews: list[ArtifactFile]=Field(default_factory=list)
    approvals: list[dict]=Field(default_factory=list)
    engine_metadata: dict=Field(default_factory=dict)
    qa_profile: str='technical_validation_plus_separate_human_review'
    platform_budget_criteria: dict | None=None

    @model_validator(mode='after')
    def invariants(self):
        if len(self.effective_configs)!=len(self.effective_config_hashes) or any(fingerprint(c)!=h for c,h in zip(self.effective_configs,self.effective_config_hashes)):
            raise ValueError('EffectiveGenerationConfig hash mismatch')
        if self.status in ['engine_validated','human_approved','game_ready'] and not any(t.get('status')=='PASS_EDITOR_VALIDATION' for t in self.import_tests):
            raise ValueError('Engine validation requires an actual passing import report')
        if self.status in ['human_approved','game_ready'] and not any(a.get('scope')=='production_artistic' and a.get('sha256')==(self.source_master.sha256 if self.source_master else None) for a in self.approvals):
            raise ValueError('Production artistic approval must match the immutable master hash')
        if self.status=='game_ready' and not self.platform_budget_criteria:raise ValueError('Game-ready requires explicit target-platform criteria')
        return self
