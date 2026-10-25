import {useEffect,useState} from "react";
import {apiFetch} from "./api";
import {Select} from "./select";

export const ASSET_KINDS:[string,string][]=[["auto","Auto · detect from the description"],["building","Building"],["character","Character"],["creature","Creature / animal"],["prop","Prop / item"],["vehicle","Vehicle / machine"],["nature","Nature / terrain"]];
const LABEL=Object.fromEntries(ASSET_KINDS.slice(1));
export const KIND_HELP:Record<string,string>={building:"Human-scale doors, no castle or ruins unless asked, water in wells and fountains",character:"Rig-friendly pose, auto-rig with standard bone names, ready for animation",creature:"Rig-friendly pose, auto-rig, ready for animation",prop:"No rig, no building checks",vehicle:"Carts, ships, siege machines: no rig, no building checks",nature:"Trees, rocks, terrain: no rig, no door checks"};
// Asset type: decides the type-specific steps. Auto shows what it detected; a choice the description clearly
// contradicts is asked back here (Use the detected type / Keep mine) before anything runs.
export function AssetKindField({value,prompt,onChange,compact,confirmed,onConfirm}:{value:string;prompt:string;onChange:(kind:string)=>void;compact?:boolean;confirmed?:boolean;onConfirm?:()=>void}){
  const [detected,setDetected]=useState<{kind:string;label:string;sure:boolean}|null>(null);
  useEffect(()=>{if(!prompt.trim()){setDetected(null);return;}const t=setTimeout(()=>{apiFetch(`/api/asset-kind?text=${encodeURIComponent(prompt.slice(0,4000))}`).then(r=>r.ok?r.json():null).then(setDetected).catch(()=>setDetected(null));},400);return()=>clearTimeout(t);},[prompt]);
  const shown=value==="auto"?detected?.kind:value;
  const conflict=value!=="auto"&&detected?.sure&&detected.kind!==value?detected:null;
  return <label className={`asset-kind-field${compact?" compact":""}`}>{!compact&&"Asset type"}<Select aria-label="Asset type" value={value} onChange={e=>onChange(e.target.value)}>{ASSET_KINDS.map(([k,l])=><option key={k} value={k}>{l}</option>)}</Select>
    {!compact&&!(conflict&&!confirmed)&&<small>{value==="auto"?(detected?`Detected: ${detected.label}. `:"")+(shown?KIND_HELP[shown]:"Picks building, character, prop… from your description."):KIND_HELP[value]}</small>}
    {!compact&&conflict&&!confirmed&&<span className="asset-kind-conflict" role="alert">The description reads as <strong>{conflict.label}</strong>, not {LABEL[value]}.
      <span><button type="button" onClick={e=>{e.preventDefault();onChange(conflict.kind);}}>Use {conflict.label}</button><button type="button" onClick={e=>{e.preventDefault();onConfirm?.();}}>Keep {LABEL[value]}</button></span></span>}
    {compact&&value==="auto"&&detected&&<small>{detected.label}</small>}
    {compact&&conflict&&<small className="asset-kind-warn" title={`The description reads as ${conflict.label}`}>Reads as {conflict.label}</small>}</label>;
}
