#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{fs, io, net::TcpListener, path::{Path, PathBuf}, process::{Child, Command, Stdio}, sync::{Arc, Mutex, atomic::{AtomicBool, AtomicU64, Ordering}}, thread, time::{Duration, Instant}};
use std::os::windows::process::CommandExt;
use std::os::windows::io::AsRawHandle;
use tauri::{Manager, State};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_notification::NotificationExt;
use windows_sys::Win32::{Foundation::{CloseHandle,HANDLE}, System::JobObjects::{CreateJobObjectW,SetInformationJobObject,AssignProcessToJobObject,JOBOBJECT_EXTENDED_LIMIT_INFORMATION,JobObjectExtendedLimitInformation,JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE}};

const HIDDEN: u32 = 0x08000000;
#[derive(Clone, Serialize, Deserialize)]
struct Config {workspace: String, library: String, blender: Option<String>, setup_complete: bool, #[serde(default)] export_directories: Vec<String>}
#[derive(Clone, Serialize)]
struct Bootstrap {phase: String, message: String, api_base: Option<String>, api_token: Option<String>, backend_pid: Option<u32>, workspace: String, library: String, logs: String, setup_complete: bool, version: String}
struct JobHandle(HANDLE);
unsafe impl Send for JobHandle {}
impl Drop for JobHandle {fn drop(&mut self) {unsafe {CloseHandle(self.0);}}}
struct Backend {config: Config, root: PathBuf, phase: String, message: String, token: String, port: u16, child: Option<Child>, job: Option<JobHandle>}
type Shared = Arc<Mutex<Backend>>;
static CLOSING: AtomicBool = AtomicBool::new(false);
static CLOSE_EPOCH: AtomicU64 = AtomicU64::new(0);
static ALLOW_EXIT: AtomicBool = AtomicBool::new(false);

fn settings_root() -> PathBuf {std::env::var_os("AFS_DESKTOP_CONFIG_DIR").map(PathBuf::from).unwrap_or_else(|| PathBuf::from(std::env::var_os("LOCALAPPDATA").unwrap()).join("AssetForgeStudio"))}
fn save_config(root: &Path, config: &Config) -> Result<(),String> {fs::create_dir_all(root).map_err(|e|e.to_string())?; fs::write(root.join("desktop-config.json"),serde_json::to_vec_pretty(config).unwrap()).map_err(|e|e.to_string())}
fn load_config(root: &Path) -> Config {
    if let Ok(bytes)=fs::read(root.join("desktop-config.json")) {if let Ok(config)=serde_json::from_slice(&bytes) {return config;}}
    let original=PathBuf::from(env!("AFS_DEFAULT_WORKSPACE"));
    let workspace=if original.is_dir(){original}else{root.join("Workspace")};
    Config{workspace:workspace.to_string_lossy().into(),library:root.join("Library").to_string_lossy().into(),blender:None,setup_complete:false,export_directories:Vec::new()}
}
fn snapshot(state:&Shared) -> Bootstrap {let value=state.lock().unwrap(); let ready=value.phase=="READY"; Bootstrap{phase:value.phase.clone(),message:value.message.clone(),api_base:if ready{Some(format!("http://127.0.0.1:{}",value.port))}else{None},api_token:if ready{Some(value.token.clone())}else{None},backend_pid:value.child.as_ref().map(Child::id),workspace:value.config.workspace.clone(),library:value.config.library.clone(),logs:value.root.join("logs").to_string_lossy().into(),setup_complete:value.config.setup_complete,version:env!("CARGO_PKG_VERSION").into()}}
fn credentials(state:&Shared)->(String,String){let value=state.lock().unwrap();(format!("http://127.0.0.1:{}",value.port),value.token.clone())}
fn health(state:&Shared)->Result<Value,String>{let(base,token)=credentials(state);ureq::get(&(base+"/api/desktop/health")).set("X-AFS-Token",&token).timeout(Duration::from_secs(4)).call().map_err(|_|"Backend health request failed".to_string())?.into_json().map_err(|_|"Invalid backend health response".into())}
fn active_count(value:&Value)->usize {value.get("active_jobs").and_then(Value::as_array).map(Vec::len).or_else(||value.get("active_jobs").and_then(Value::as_u64).map(|n|n as usize)).or_else(||value.get("active_count").and_then(Value::as_u64).map(|n|n as usize)).unwrap_or(0)}
fn assign_job(child:&Child)->Option<JobHandle>{unsafe{let handle=CreateJobObjectW(std::ptr::null(),std::ptr::null());if handle.is_null(){return None;}let mut limits:JOBOBJECT_EXTENDED_LIMIT_INFORMATION=std::mem::zeroed();limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;let ok=SetInformationJobObject(handle,JobObjectExtendedLimitInformation,&limits as *const _ as *const _,std::mem::size_of_val(&limits) as u32)!=0&&AssignProcessToJobObject(handle,child.as_raw_handle() as HANDLE)!=0;if ok{Some(JobHandle(handle))}else{CloseHandle(handle);None}}}
fn start_backend(app:tauri::AppHandle,state:Shared){thread::spawn(move||{
    let result=(||->Result<(),String>{
        let(config,root)={let mut value=state.lock().unwrap();if value.child.as_mut().and_then(|child|child.try_wait().ok()).flatten().is_none()&&value.child.is_some(){return Ok(());}value.phase="STARTING".into();value.message="Starting the managed Python backend…".into();(value.config.clone(),value.root.clone())};
        fs::create_dir_all(&config.library).map_err(|_|"Library directory is not writable".to_string())?;fs::create_dir_all(root.join("logs")).map_err(|e|e.to_string())?;save_config(&root,&config)?;
        let port=TcpListener::bind("127.0.0.1:0").map_err(|e|e.to_string())?.local_addr().unwrap().port();let token=format!("{}{}",uuid::Uuid::new_v4().simple(),uuid::Uuid::new_v4().simple());
        let adjacent=std::env::current_exe().unwrap().parent().unwrap().join("afs-backend.exe");
        let development=PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("binaries/afs-backend-x86_64-pc-windows-msvc.exe");
        let mut command=if adjacent.is_file(){Command::new(adjacent)}else if development.is_file(){Command::new(development)}else if cfg!(debug_assertions){let mut cmd=Command::new(Path::new(&config.workspace).join(".venv/Scripts/python.exe"));cmd.arg(Path::new(&config.workspace).join("desktop/backend_entry.py"));cmd}else{return Err("Packaged backend executable is missing. Reinstall the desktop package.".into());};
        let log=fs::OpenOptions::new().create(true).append(true).open(root.join("logs/backend.log")).map_err(|e|e.to_string())?;
        command.current_dir(if Path::new(&config.workspace).is_dir(){Path::new(&config.workspace)}else{root.as_path()}).env("AFS_DESKTOP","1").env("AFS_API_TOKEN",&token).env("AFS_PORT",port.to_string()).env("AFS_WORKSPACE",&config.workspace).env("AFS_DATA",&config.library).stdout(Stdio::from(log.try_clone().unwrap())).stderr(Stdio::from(log)).creation_flags(HIDDEN);
        if let Some(path)=&config.blender{command.env("AFS_BLENDER",path);}
        let child=command.spawn().map_err(|e|format!("Managed backend could not start: {}",e))?;let job=assign_job(&child);
        {let mut value=state.lock().unwrap();value.port=port;value.token=token;value.child=Some(child);value.job=job;}
        let began=Instant::now();while began.elapsed()<Duration::from_secs(180){
            {let mut value=state.lock().unwrap();if let Some(code)=value.child.as_mut().unwrap().try_wait().map_err(|e|e.to_string())?{return Err(format!("Backend exited with {}. Open local startup logs for details.",code));}}
            if health(&state).is_ok(){let mut value=state.lock().unwrap();value.phase="READY".into();value.message="Local backend ready. Engines load only when requested.".into();return Ok(());}thread::sleep(Duration::from_millis(300));
        }Err("Backend startup timed out. Local logs contain the retained error.".into())
    })();
    if let Err(message)=result{let mut value=state.lock().unwrap();value.phase="FAILED".into();value.message=message;}
    let _=app;
});}
fn stop_backend(state:&Shared,cancel:bool)->Result<(),String>{
    let(base,token)=credentials(state);
    {let mut value=state.lock().unwrap();if value.child.is_none(){return Ok(());}if value.child.as_mut().unwrap().try_wait().map_err(|e|e.to_string())?.is_some(){value.child=None;value.job=None;return Ok(());}}
    ureq::post(&(base+"/api/desktop/shutdown")).set("X-AFS-Token",&token).timeout(Duration::from_secs(120)).send_json(json!({"cancel_active":cancel})).map_err(|_|"Backend declined shutdown or has not checkpointed yet. Keep the studio open and inspect local jobs.".to_string())?;
    let started=Instant::now();while started.elapsed()<Duration::from_secs(120){let done={let mut value=state.lock().unwrap();value.child.as_mut().unwrap().try_wait().map_err(|e|e.to_string())?.is_some()};if done{let mut value=state.lock().unwrap();value.child=None;value.job=None;value.phase="STOPPED".into();return Ok(());}thread::sleep(Duration::from_millis(200));}
    Err("Backend has not exited; the studio remains open to preserve jobs.".into())
}

#[tauri::command] fn desktop_bootstrap(state:State<Shared>)->Bootstrap{snapshot(&state)}
#[tauri::command] fn desktop_retry_backend(app:tauri::AppHandle,state:State<Shared>){start_backend(app,state.inner().clone());}
#[tauri::command] fn desktop_finish_setup(state:State<Shared>)->Result<(),String>{let mut value=state.lock().unwrap();value.config.setup_complete=true;save_config(&value.root,&value.config)}
#[tauri::command] async fn desktop_pick_directory(app:tauri::AppHandle,state:State<'_,Shared>,kind:String)->Result<Option<String>,String>{
    if !["library","workspace"].contains(&kind.as_str()){return Err("Unknown directory setting".into());}if health(&state).map(|h|active_count(&h)>0).unwrap_or(false){return Err("Finish or cancel active jobs before changing runtime directories".into());}
    let file=app.dialog().file().set_title(if kind=="library"{"Choose persistent asset library"}else{"Choose existing local AI workspace"}).blocking_pick_folder();let Some(file)=file else{return Ok(None)};let path=file.into_path().map_err(|_|"Not a local directory".to_string())?;let text=path.to_string_lossy().to_string();stop_backend(&state,false)?;
    {let mut value=state.lock().unwrap();if kind=="library"{value.config.library=text.clone();}else{value.config.workspace=text.clone();}save_config(&value.root,&value.config)?;}start_backend(app,state.inner().clone());Ok(Some(text))
}
#[tauri::command] async fn desktop_pick_blender(app:tauri::AppHandle,state:State<'_,Shared>)->Result<Option<String>,String>{let file=app.dialog().file().set_title("Choose blender.exe").add_filter("Blender executable",&["exe"]).blocking_pick_file();let Some(file)=file else{return Ok(None)};let path=file.into_path().map_err(|_|"Not a local file".to_string())?;if !path.file_name().map(|s|s.to_string_lossy().eq_ignore_ascii_case("blender.exe")).unwrap_or(false){return Err("Choose blender.exe".into());}stop_backend(&state,false)?;let text=path.to_string_lossy().to_string();{let mut value=state.lock().unwrap();value.config.blender=Some(text.clone());save_config(&value.root,&value.config)?;}start_backend(app,state.inner().clone());Ok(Some(text))}
#[tauri::command] fn desktop_open_folder(state:State<Shared>,scope:String)->Result<(),String>{let value=state.lock().unwrap();let path=match scope.as_str(){"library"=>PathBuf::from(&value.config.library),"workspace"=>PathBuf::from(&value.config.workspace),"logs"=>value.root.join("logs"),_=>return Err("Unknown native folder scope".into())};if !path.is_dir(){return Err("Directory does not exist".into());}Command::new("explorer.exe").arg(path).creation_flags(HIDDEN).spawn().map_err(|e|e.to_string())?;Ok(())}
#[tauri::command] fn desktop_notify(app:tauri::AppHandle,message:String)->Result<(),String>{if message.len()>300{return Err("Notification too long".into());}app.notification().builder().title("Asset Forge Studio").body(message).show().map_err(|e|e.to_string())}
#[tauri::command] async fn desktop_pick_export_directory(app:tauri::AppHandle,state:State<'_,Shared>)->Result<Option<String>,String>{
    let selected=app.dialog().file().set_title("Choose game asset delivery directory").blocking_pick_folder();let Some(selected)=selected else{return Ok(None)};
    let path=selected.into_path().map_err(|_|"A local folder is required".to_string())?.canonicalize().map_err(|e|e.to_string())?;
    let text=path.to_string_lossy().trim_start_matches(r"\\?\").to_string();let mut value=state.lock().unwrap();if !value.config.export_directories.contains(&text){value.config.export_directories.push(text.clone());save_config(&value.root,&value.config)?;}Ok(Some(text))
}
#[tauri::command] fn desktop_open_export_directory(state:State<Shared>,path:String)->Result<(),String>{
    let target=PathBuf::from(path).canonicalize().map_err(|_|"Export directory does not exist".to_string())?;
    let value=state.lock().unwrap();let roots=value.config.export_directories.iter().map(PathBuf::from).chain(std::iter::once(PathBuf::from(&value.config.library)));
    if !target.is_dir() || !roots.filter_map(|p|p.canonicalize().ok()).any(|p|target.starts_with(p)){return Err("Choose this export root with the folder picker first".into());}
    Command::new("explorer.exe").arg(target).creation_flags(HIDDEN).spawn().map_err(|e|e.to_string())?;Ok(())
}
#[tauri::command] async fn desktop_download(app:tauri::AppHandle,state:State<'_,Shared>,api_path:String)->Result<Option<String>,String>{
    if !api_path.starts_with("/api/")||api_path.contains("..")||api_path.contains("//")||api_path.contains("afs_token"){return Err("Only scoped API downloads are allowed".into());}
    let(base,token)=credentials(&state);let response=ureq::get(&(base+&api_path)).set("X-AFS-Token",&token).timeout(Duration::from_secs(300)).call().map_err(|_|"Local download failed".to_string())?;
    let suggested=response.header("Content-Disposition").and_then(|s|s.split("filename=\"").nth(1)).and_then(|s|s.split('"').next()).and_then(|s|Path::new(s).file_name()).map(|s|s.to_string_lossy().to_string()).unwrap_or("asset-forge-export.bin".into());
    let selected=app.dialog().file().set_file_name(&suggested).blocking_save_file();let Some(selected)=selected else{return Ok(None)};let target=selected.into_path().map_err(|_|"Not a local save path".to_string())?;let temporary=target.with_extension("afs-download-part");let mut output=fs::File::create(&temporary).map_err(|e|e.to_string())?;io::copy(&mut response.into_reader(),&mut output).map_err(|_|"Download interrupted; partial file retained".to_string())?;drop(output);fs::rename(&temporary,&target).map_err(|e|e.to_string())?;Ok(Some(target.to_string_lossy().into()))
}
fn exit_notice(app:&tauri::AppHandle,phase:&str,message:&str){
    if let Some(window)=app.get_webview_window("main"){
        let payload=json!({"phase":phase,"message":message}).to_string();
        let _=window.eval(format!("window.dispatchEvent(new CustomEvent('afs-desktop-exit',{{detail:{}}}))",payload));
        let _=window.set_title(if phase=="waiting" {"Asset Forge Studio - saving stage before exit"} else {"Asset Forge Studio"});
    }
}
fn exit_control(state:&Shared,path:&str)->Result<(),String>{
    let(base,token)=credentials(state);
    ureq::post(&(base+path)).set("X-AFS-Token",&token).timeout(Duration::from_secs(15)).send_json(json!({})).map_err(|_|"Could not save the exit checkpoint. Studio stays open; inspect local jobs.".to_string())?;
    Ok(())
}
#[tauri::command] async fn desktop_cancel_close(app:tauri::AppHandle,state:State<'_,Shared>)->Result<(),String>{
    if state.lock().unwrap().phase=="STOPPING" {return Err("The saved backend is already shutting down.".into());}
    CLOSING.store(false,Ordering::SeqCst);CLOSE_EPOCH.fetch_add(1,Ordering::SeqCst);
    exit_control(&state,"/api/desktop/cancel-exit")?;
    exit_notice(&app,"cancelled","Studio kept open. Previous queue pause settings were restored.");Ok(())
}
#[tauri::command] fn desktop_request_close(app:tauri::AppHandle){if let Some(window)=app.get_webview_window("main"){let _=window.close();}}

fn main(){
    // Explicit profiles isolate QA/config/WebView state without touching an open
    // user session. Ordinary launches retain the packaged single-instance ID.
    let mut context=tauri::generate_context!();
    if let Some(profile)=std::env::var_os("AFS_DESKTOP_CONFIG_DIR").filter(|v|!v.is_empty()) {
        use std::hash::{Hash,Hasher};
        let mut hash=std::collections::hash_map::DefaultHasher::new();
        PathBuf::from(&profile).to_string_lossy().to_lowercase().hash(&mut hash);
        context.config_mut().identifier=format!("{}.profile{:x}",context.config().identifier,hash.finish());
        for window in &mut context.config_mut().app.windows {window.data_directory=Some(PathBuf::from(&profile).join("WebView2"));}
    }
    let root=settings_root();let config=load_config(&root);let state:Shared=Arc::new(Mutex::new(Backend{config,root,phase:"STARTING".into(),message:"Preparing your local workspace…".into(),token:String::new(),port:0,child:None,job:None}));
    let close_state=state.clone();
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app,_,_|{if let Some(window)=app.get_webview_window("main"){let _=window.show();let _=window.set_focus();}}))
        .plugin(tauri_plugin_dialog::init()).plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_window_state::Builder::default().with_state_flags(tauri_plugin_window_state::StateFlags::POSITION|tauri_plugin_window_state::StateFlags::SIZE|tauri_plugin_window_state::StateFlags::MAXIMIZED).build())
        .manage(state.clone()).invoke_handler(tauri::generate_handler![desktop_bootstrap,desktop_retry_backend,desktop_finish_setup,desktop_pick_directory,desktop_pick_blender,desktop_open_folder,desktop_pick_export_directory,desktop_open_export_directory,desktop_notify,desktop_download,desktop_request_close,desktop_cancel_close])
        .setup(move|app|{start_backend(app.handle().clone(),state.clone());Ok(())})
        .on_window_event(move|window,event|{if let tauri::WindowEvent::CloseRequested{api,..}=event{if ALLOW_EXIT.load(Ordering::SeqCst){return;}api.prevent_close();if CLOSING.swap(true,Ordering::SeqCst){return;}let epoch=CLOSE_EPOCH.fetch_add(1,Ordering::SeqCst)+1;let state=close_state.clone();let app=window.app_handle().clone();thread::spawn(move||{
            let current=||CLOSING.load(Ordering::SeqCst)&&CLOSE_EPOCH.load(Ordering::SeqCst)==epoch;
            let result=(||->Result<(),String>{
                if active_count(&health(&state)?)>0{
                    exit_control(&state,"/api/desktop/prepare-exit")?;
                    if !current(){return Ok(());}
                    exit_notice(&app,"waiting","No new jobs will start. The current stage will finish and save before AFS exits.");
                    loop{
                        if !current(){return Ok(());}
                        if active_count(&health(&state)?)==0{break;}
                        thread::sleep(Duration::from_millis(700));
                    }
                }
                if !current(){return Ok(());}
                {state.lock().unwrap().phase="STOPPING".into();}
                exit_notice(&app,"stopping","Stage checkpoint saved. Closing the local backend...");
                stop_backend(&state,false)?;
                ALLOW_EXIT.store(true,Ordering::SeqCst);app.exit(0);Ok(())
            })();
            if let Err(message)=result{
                if CLOSE_EPOCH.load(Ordering::SeqCst)!=epoch{return;}
                CLOSING.store(false,Ordering::SeqCst);
                {state.lock().unwrap().phase="READY".into();}
                exit_notice(&app,"error",&message);
            }
        });}})
        .run(context).expect("Asset Forge Studio desktop startup failed");
}
