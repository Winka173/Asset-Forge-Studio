"""Deterministic world layout contract. Text is context, never authoritative coordinates."""
import math
from collections import deque
from typing import Literal
import numpy as np
from pydantic import BaseModel,ConfigDict,Field,model_validator


class Point(BaseModel):
    model_config=ConfigDict(extra='forbid')
    x: float
    z: float


class Road(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,60}$')
    width_m:float=Field(default=6,ge=3,le=20)
    points:list[Point]=Field(min_length=2,max_length=30)


class Zone(Point):
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,60}$')
    width_m:float=Field(default=8,ge=4,le=40)
    depth_m:float=Field(default=8,ge=4,le=40)


class Spawn(Point):
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,60}$')


class Prop(Point):
    package_artifact_id:str=Field(min_length=1)
    yaw_degrees:float=Field(default=0,ge=-360,le=360)
    scale:float=Field(default=1,ge=.1,le=3)


class WorldPlan(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    schema_version:Literal['1.0']='1.0'
    project_id:str
    name:str=Field(min_length=1,max_length=200)
    prompt:str=Field(default='',max_length=100000)
    units:Literal['m']='m'
    coordinate_system:Literal['Unity Y-up; x/east, z/north']='Unity Y-up; x/east, z/north'
    width_m:float=Field(default=256,ge=64,le=512)
    depth_m:float=Field(default=256,ge=64,le=512)
    max_height_m:float=Field(default=20,ge=4,le=60)
    resolution:Literal[129,257]=129
    seed:int=Field(default=42,ge=0,le=4294967295)
    grass_color:str=Field(default='#607247',pattern=r'^#[0-9a-fA-F]{6}$')
    road_color:str=Field(default='#88755b',pattern=r'^#[0-9a-fA-F]{6}$')
    roads:list[Road]=Field(min_length=1,max_length=8)
    spawns:list[Spawn]=Field(min_length=1,max_length=8)
    goal:Point
    build_zones:list[Zone]=Field(default_factory=list,max_length=24)
    props:list[Prop]=Field(default_factory=list,max_length=16)
    missing_props_policy:Literal['block']='block'
    terrain_style:Literal['seeded_hills_flattened_roads']='seeded_hills_flattened_roads'
    layout_source:Literal['explicit_procedural_template','user_edited_structured_plan']='explicit_procedural_template'
    assumptions:list[str]=Field(default_factory=lambda:['Provisional terrain colors and dimensions require plan approval','Prompt is recorded context; template rules generate coordinates, not an LLM or concept image','No rivers/bridges/AI prop sub-jobs in this tested slice'])

    @model_validator(mode='after')
    def layout(self):
        points=[self.goal,*self.spawns,*self.props]+[p for r in self.roads for p in r.points]
        if any(not math.isfinite(p.x) or not math.isfinite(p.z) or not (0<=p.x<=self.width_m and 0<=p.z<=self.depth_m) for p in points):raise ValueError('World coordinates must be finite and inside the explicit world bounds')
        for zone in self.build_zones:
            if not (zone.width_m/2<=zone.x<=self.width_m-zone.width_m/2 and zone.depth_m/2<=zone.z<=self.depth_m-zone.depth_m/2):raise ValueError('Build zone extends outside terrain')
        for n,a in enumerate(self.build_zones):
            for b in self.build_zones[n+1:]:
                if abs(a.x-b.x)<(a.width_m+b.width_m)/2 and abs(a.z-b.z)<(a.depth_m+b.depth_m)/2:raise ValueError('Build zones overlap')
        for items in [self.roads,self.spawns,self.build_zones]:
            if len({i.id for i in items})!=len(items):raise ValueError('Duplicate layout identifiers')
        return self


def template(project_id,name,prompt,width=256,depth=256,seed=42):
    goal=Point(x=.5*width,z=.9*depth)
    spawns=[Spawn(id='spawn_west',x=.25*width,z=.1*depth),Spawn(id='spawn_east',x=.75*width,z=.1*depth)]
    roads=[Road(id='lane_'+str(n),points=[Point(x=s.x,z=s.z),Point(x=s.x,z=.65*depth),Point(x=.5*width,z=.8*depth),goal]) for n,s in enumerate(spawns)]
    zones=[Zone(id='build_'+str(n),x=x*width,z=.45*depth) for n,x in enumerate([.1,.4,.6,.9])]
    return WorldPlan(project_id=project_id,name=name,prompt=prompt,width_m=width,depth_m=depth,seed=seed,roads=roads,spawns=spawns,goal=goal,build_zones=zones)


def terrain(plan:WorldPlan):
    r=plan.resolution;xs=np.linspace(0,plan.width_m,r);zs=np.linspace(0,plan.depth_m,r);x,z=np.meshgrid(xs,zs)
    rng=np.random.default_rng(plan.seed);heights=np.zeros((r,r),dtype=np.float64)
    # Smooth deterministic value noise; no external model or random untracked source.
    for grid,weight in [(5,.22),(9,.1),(17,.04)]:
        values=rng.random((grid,grid));ix=np.linspace(0,grid-1,r);iz=np.linspace(0,grid-1,r)
        rows=np.array([np.interp(ix,np.arange(grid),row) for row in values]);layer=np.array([np.interp(iz,np.arange(grid),rows[:,i]) for i in range(r)]).T
        heights+=weight*layer
    heights+=.08;distance=np.full((r,r),np.inf)
    for road in plan.roads:
        for a,b in zip(road.points,road.points[1:]):
            dx=b.x-a.x;dz=b.z-a.z;norm=dx*dx+dz*dz
            t=np.clip(((x-a.x)*dx+(z-a.z)*dz)/max(norm,1e-12),0,1)
            d=np.sqrt((x-(a.x+t*dx))**2+(z-(a.z+t*dz))**2)-road.width_m/2
            distance=np.minimum(distance,d)
    mask=distance<=0
    blend=np.clip(distance/5,0,1);heights=.08+(heights-.08)*blend
    zone_mask=np.zeros((r,r),dtype=bool)
    for zone in plan.build_zones:
        area=(abs(x-zone.x)<=zone.width_m/2)&(abs(z-zone.z)<=zone.depth_m/2)
        if np.any(area&mask):raise ValueError('Build zone overlaps a road corridor')
        heights[area]=.08;zone_mask|=area
    # Quantize once to the actual 16-bit source used by Unity, then validate that data.
    raw=np.rint(np.clip(heights,0,1)*65535).astype('<u2')
    meters=raw.astype(np.float64)/65535*plan.max_height_m
    dz,dx=np.gradient(meters,plan.depth_m/(r-1),plan.width_m/(r-1))
    walkable=np.sqrt(dx*dx+dz*dz)<=math.tan(math.radians(30))
    def index(p):return int(round(p.z/plan.depth_m*(r-1))),int(round(p.x/plan.width_m*(r-1)))
    start=index(plan.goal);seen={start};queue=deque([start])
    while queue:
        a,b=queue.popleft()
        for i,j in [(a-1,b),(a+1,b),(a,b-1),(a,b+1)]:
            if 0<=i<r and 0<=j<r and walkable[i,j] and (i,j) not in seen:seen.add((i,j));queue.append((i,j))
    reachable={s.id:index(s) in seen and bool(mask[index(s)]) for s in plan.spawns}
    if not all(reachable.values()) or not mask[start]:raise ValueError('Every spawn must connect to the goal through a valid road/navigation layout')
    # Separate corridor connectivity from general terrain reachability.
    corridor={start};queue=deque([start])
    while queue:
        a,b=queue.popleft()
        for i,j in [(a-1,b),(a+1,b),(a,b-1),(a,b+1)]:
            if 0<=i<r and 0<=j<r and mask[i,j] and (i,j) not in corridor:corridor.add((i,j));queue.append((i,j))
    if any(index(s) not in corridor for s in plan.spawns):raise ValueError('Road corridors are disconnected at the exported grid resolution')
    return raw,mask,zone_mask,dict(status='PASS_PROCEDURAL_LAYOUT_QA',spawn_to_goal=reachable,road_connectivity=True,non_overlapping_build_zones=True,
        height_min_m=float(meters.min()),height_max_m=float(meters.max()),seed=plan.seed,resolution=r,bit_depth=16,
        coordinate_system=plan.coordinate_system,physics_navmesh='Requires native Unity build/test; this grid QA is not a NavMesh substitute',quality='NEEDS_HUMAN_REVIEW')
