import {useEffect,useRef,useState} from 'react';
import * as T from 'three';
import {Select} from './select';

/** Read-only preview of the actual glTF clips and joints. Never writes model files. */
export class MotionModel {
 readonly mixer:T.AnimationMixer;
 readonly bones:T.Bone[]=[];
 readonly helper:T.SkeletonHelper|null;
 private original=new Map<T.Bone,{p:T.Vector3;q:T.Quaternion;s:T.Vector3}>();
 private poseDeltas=new Map<number,number[]>();
 constructor(readonly root:T.Object3D,readonly clips:T.AnimationClip[],scene:T.Scene){
  this.mixer=new T.AnimationMixer(root);
  root.traverse(node=>{if(node instanceof T.Bone){this.bones.push(node);this.original.set(node,{p:node.position.clone(),q:node.quaternion.clone(),s:node.scale.clone()});}});
  this.helper=this.bones.length?new T.SkeletonHelper(root):null;
  if(this.helper){this.helper.visible=false;this.helper.renderOrder=1000;const materials=Array.isArray(this.helper.material)?this.helper.material:[this.helper.material];materials.forEach(m=>{m.depthTest=false;m.transparent=true;m.opacity=.95;});scene.add(this.helper);}
 }
 seek(name:string,seconds:number,loop:boolean){
  const clip=this.clips.find(c=>c.name===name);if(!clip)return;
  const action=this.mixer.clipAction(clip);action.reset();action.enabled=true;action.paused=false;action.clampWhenFinished=!loop;action.setLoop(loop?T.LoopRepeat:T.LoopOnce,loop?Infinity:1);action.play();this.mixer.setTime(seconds);this.root.updateMatrixWorld(true);
 }
 stop(){this.mixer.stopAllAction();}
 resetPose(){this.stop();this.poseDeltas.clear();this.restoreOriginal();}
 private restoreOriginal(){for(const [bone,pose] of this.original){bone.position.copy(pose.p);bone.quaternion.copy(pose.q);bone.scale.copy(pose.s);}this.root.updateMatrixWorld(true);}
 pose(index:number,degrees:number[]){this.stop();this.poseDeltas.set(index,degrees);this.restoreOriginal();for(const [i,angles] of this.poseDeltas){const bone=this.bones[i],original=bone&&this.original.get(bone);if(!original)continue;const delta=new T.Quaternion().setFromEuler(new T.Euler(...angles.map(T.MathUtils.degToRad) as [number,number,number]));bone.quaternion.copy(original.q).multiply(delta);}this.root.updateMatrixWorld(true);}
 delta(index:number){return this.poseDeltas.get(index)||[0,0,0];}
 checksum(){return this.bones.map(b=>[...b.position.toArray(),...b.quaternion.toArray()].map(n=>n.toFixed(4)).join(',')).join('|');}
 dispose(){this.stop();this.mixer.uncacheRoot(this.root);if(this.helper){this.helper.removeFromParent();this.helper.geometry.dispose();(Array.isArray(this.helper.material)?this.helper.material:[this.helper.material]).forEach(m=>m.dispose());}}
}

export function MotionPreview({models,onFit}:{models:MotionModel[];onFit:()=>void}){
 const leader=models.find(m=>m.clips.length)||models.find(m=>m.bones.length),[clipIndex,setClipIndex]=useState(0),[playing,setPlaying]=useState(false),[loop,setLoop]=useState(true),[speed,setSpeed]=useState(1),[time,setTime]=useState(0),[skeleton,setSkeleton]=useState(false),[bone,setBone]=useState(0),[angles,setAngles]=useState([0,0,0]);
 const elapsed=useRef(0),clip=leader?.clips[clipIndex],duration=clip?.duration||0;
 const write=(seconds:number)=>{if(!clip)return;elapsed.current=Math.min(duration,Math.max(0,seconds));for(const model of models)model.seek(clip.name,elapsed.current,loop);setTime(elapsed.current);};
 useEffect(()=>{setPlaying(false);setClipIndex(0);setBone(0);setAngles([0,0,0]);elapsed.current=0;setTime(0);const frame=requestAnimationFrame(onFit);return()=>cancelAnimationFrame(frame);},[models]);
 useEffect(()=>{for(const model of models){model.resetPose();if(clip)model.seek(clip.name,0,loop);}elapsed.current=0;setTime(0);setPlaying(false);setAngles([0,0,0]);},[clip,models]);
 useEffect(()=>{for(const model of models)if(model.helper)model.helper.visible=skeleton;},[skeleton,models]);
 useEffect(()=>{if(!playing||!clip||duration<=0)return;let frame=0,last=performance.now(),lastUI=0;const tick=(now:number)=>{const delta=document.hidden?0:Math.min((now-last)/1000,.1);last=now;let seconds=elapsed.current+delta*speed;if(seconds>=duration){seconds=loop?seconds%duration:duration;if(!loop)setPlaying(false);}elapsed.current=seconds;for(const model of models)model.seek(clip.name,seconds,loop);if(now-lastUI>80||seconds===duration){setTime(seconds);lastUI=now;}if(loop||seconds<duration)frame=requestAnimationFrame(tick);};frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame);},[playing,clip,duration,loop,speed,models]);
 if(!leader)return null;
 const reset=()=>{setPlaying(false);models.forEach(m=>m.resetPose());elapsed.current=0;setTime(0);setAngles([0,0,0]);};
 const step=(direction:number)=>{setPlaying(false);write(elapsed.current+direction/30);};
 return <div className="motion-controls" aria-label="Animation and rig preview" data-clips={leader.clips.length} data-bones={leader.bones.length} data-time={time.toFixed(4)} data-pose-checksum={leader.checksum()} data-skeleton={skeleton}>
  {clip&&<><div className="motion-transport"><button className="primary" aria-label={playing?'Pause animation':'Play animation'} onClick={()=>{if(playing){setPlaying(false);setTime(elapsed.current);}else{models.forEach(m=>m.resetPose());if(time>=duration)write(0);setPlaying(true);}}}>{playing?'Pause':'Play'}</button><button title="Step the preview by 1/30 second" aria-label="Previous animation frame" onClick={()=>step(-1)}>−1f</button><button title="Step the preview by 1/30 second" aria-label="Next animation frame" onClick={()=>step(1)}>+1f</button><Select aria-label="Animation clip" value={clipIndex} onChange={e=>setClipIndex(Number(e.target.value))}>{leader.clips.map((c,i)=><option value={i} key={c.uuid}>{c.name||`Clip ${i+1}`}</option>)}</Select><Select aria-label="Playback speed" value={speed} onChange={e=>setSpeed(Number(e.target.value))}>{[.25,.5,1,1.5,2].map(v=><option value={v} key={v}>{v}×</option>)}</Select><label><input type="checkbox" checked={loop} onChange={e=>setLoop(e.target.checked)}/>Loop</label></div><div className="motion-timeline"><input aria-label="Animation timeline" type="range" min={0} max={duration} step={Math.max(duration/1000,.001)} value={time} onChange={e=>{setPlaying(false);models.forEach(m=>m.resetPose());write(Number(e.target.value));}}/><output>{time.toFixed(2)} / {duration.toFixed(2)} s</output></div></>}
  <div className="motion-rig-toolbar">{leader.bones.length>0&&<label><input aria-label="Show skeleton" type="checkbox" checked={skeleton} onChange={e=>setSkeleton(e.target.checked)}/>Skeleton · {leader.bones.length} bones</label>}<button onClick={onFit}>Frame model</button><button onClick={reset}>Reset pose</button><small>Preview only · saved source stays unchanged</small></div>
  {leader.bones.length>0&&<details className="motion-rig-details"><summary>Inspect rig / test pose</summary><Select aria-label="Rig bone" value={bone} onChange={e=>{const index=Number(e.target.value);setBone(index);setAngles(leader.delta(index));}}>{leader.bones.map((b,i)=><option key={b.uuid} value={i}>{b.name||`Joint ${i+1}`}{b.parent instanceof T.Bone?` · parent ${b.parent.name||'joint'}`:' · root'}</option>)}</Select><div className="motion-pose-axes">{['X','Y','Z'].map((axis,i)=><label key={axis}>{axis}<input aria-label={`Preview bone rotation ${axis}`} type="range" min={-90} max={90} step={1} value={angles[i]} onChange={e=>{setPlaying(false);const next=angles.map((n,j)=>j===i?Number(e.target.value):n);setAngles(next);leader.pose(bone,next);}}/><output>{angles[i]}°</output></label>)}</div><p>Tests rotations relative to this file’s source pose. This is not auto-rigging, retargeting or a saved animation edit.</p></details>}
 </div>;
}
