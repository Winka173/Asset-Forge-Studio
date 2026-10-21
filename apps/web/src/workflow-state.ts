import {useEffect} from 'react';
/** Synchronize validated project settings across the existing workspace panels. */
export function publishWorkflow(projectId:string,value:unknown){window.dispatchEvent(new CustomEvent('afs-project-workflow',{detail:{projectId,value}}));}
export function useWorkflowUpdates<T>(projectId:string,setValue:(value:T)=>void){useEffect(()=>{const handler=(event:Event)=>{const data=(event as CustomEvent<{projectId:string;value:T}>).detail;if(data.projectId===projectId)setValue(data.value);};window.addEventListener('afs-project-workflow',handler);return()=>window.removeEventListener('afs-project-workflow',handler);},[projectId,setValue]);}
