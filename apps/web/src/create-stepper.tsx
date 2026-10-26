import {Check} from 'lucide-react';
/** The one step indicator used by every Create workflow (same look as Single asset). workflow = prepend the "Choose workflow" step that returns to the Create hub. */
export function CreateStepper({steps,current,onGo,disabledFrom,label='Creation steps',workflow=false}:{steps:string[];current:number;onGo?:(index:number)=>void;disabledFrom?:number;label?:string;workflow?:boolean}){
 const all=workflow?['Choose workflow',...steps]:steps,at=workflow?current+1:current,offset=workflow?1:0;
 const go=(index:number)=>{if(workflow&&index===0){window.dispatchEvent(new Event('afs-change-workflow'));return;}onGo?.(index-offset);};
 return <ol className="create-stepper" aria-label={label}>{all.map((text,index)=>{const locked=disabledFrom!==undefined&&index-offset>=disabledFrom,clickable=index===0&&workflow||!!onGo;return <li key={index}><button type="button" aria-current={index===at?'step':undefined} disabled={!clickable||locked} onClick={()=>go(index)}><span>{index<at?<Check size={14} aria-hidden="true"/>:index+1}</span>{text}</button></li>;})}</ol>;
}
