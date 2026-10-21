import {Component,type ErrorInfo,type ReactNode} from 'react';
/** Render failures must not strand a local production queue behind a blank screen. */
export class WorkspaceErrorBoundary extends Component<{children:ReactNode},{error:string;details:string}>{
 state={error:'',details:''};
 static getDerivedStateFromError(error:Error){return {error:error.message||'Unexpected interface error'};}
 componentDidCatch(error:Error,info:ErrorInfo){this.setState({details:(error.stack||error.message)+'\n'+(info.componentStack||'')});}
 render(){if(!this.state.error)return this.props.children;return <main className="workspace-recovery" role="alert"><div><span>LOCAL WORKSPACE</span><h1>The interface needs to reload.</h1><p>Reopen the workspace to continue. Reloading the interface does not submit generation jobs. Existing server jobs and saved files are managed separately.</p><button onClick={()=>{location.hash='home';location.reload();}}>Reopen workspace</button><details><summary>Technical details</summary><pre>{this.state.details||this.state.error}</pre></details></div></main>;}
}
