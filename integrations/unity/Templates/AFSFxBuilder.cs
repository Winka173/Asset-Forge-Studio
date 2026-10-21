using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class AFSFxBuilder {
    [Serializable] class Recipe {public string element,name;public float duration,radius,trail_lifetime,intensity;public int segments,particle_count,seed;}
    [Serializable] class Request {public string outputPath,configHash;public int frames,width,height;}
    static Request request;static Recipe recipe;static readonly List<string> errors=new List<string>();
    const string Root="Assets/AFS/FX";
    static string Project=>Directory.GetParent(Application.dataPath).FullName;
    static void Load(){request=JsonUtility.FromJson<Request>(File.ReadAllText(Path.Combine(Project,"FxRequest.json")));recipe=JsonUtility.FromJson<Recipe>(File.ReadAllText(Root+"/recipe.json"));}
    static void Check(bool value,string message){if(!value)errors.Add(message);}
    static string Json(object value){if(value==null)return "null";if(value is string s)return "\""+s.Replace("\\","\\\\").Replace("\"","\\\"").Replace("\n","\\n").Replace("\r","\\r").Replace("\t","\\t")+"\"";if(value is bool b)return b?"true":"false";if(value is System.Collections.IDictionary dictionary){var rows=new List<string>();foreach(System.Collections.DictionaryEntry e in dictionary)rows.Add(Json(e.Key.ToString())+":"+Json(e.Value));return "{"+string.Join(",",rows)+"}";}if(value is System.Collections.IEnumerable list){var rows=new List<string>();foreach(var x in list)rows.Add(Json(x));return "["+string.Join(",",rows)+"]";}return Convert.ToString(value,System.Globalization.CultureInfo.InvariantCulture);}
    static void Report(string name,Dictionary<string,object> result){result["checks_passed"]=errors.Count==0;result["failures"]=errors;result["unity_version"]=Application.unityVersion;result["config_hash"]=request.configHash;result["artistic_approval"]=false;result["character_animation"]=false;File.WriteAllText(Path.Combine(request.outputPath,name),Json(result));EditorApplication.Exit(errors.Count==0?0:1);}
    public static void Run(){Load();var report=new Dictionary<string,object>();try{Build(report);}catch(Exception e){errors.Add(e.ToString());Debug.LogException(e);}Report("fx_report.json",report);}
    static void Build(Dictionary<string,object> report){
        EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
        var shader=AssetDatabase.LoadAssetAtPath<Shader>(Root+"/Runtime/AFSSlash.shader");Check(shader&&shader.isSupported,"Runtime slash shader must compile on actual GPU");if(!shader)throw new Exception("Slash shader missing");
        var material=new Material(shader){name="AFS_"+recipe.element+"_Emission"};AssetDatabase.CreateAsset(material,Root+"/Effect.mat");
        var solid=new Material(Shader.Find("Standard")){name="AFS_Steel"};solid.color=new Color(.33f,.4f,.45f);solid.SetFloat("_Metallic",.8f);solid.SetFloat("_Glossiness",.65f);AssetDatabase.CreateAsset(solid,Root+"/Steel.mat");
        var root=new GameObject(recipe.name);var fx=root.AddComponent<AFSSlashEffect>();fx.element=recipe.element;fx.duration=recipe.duration;fx.radius=recipe.radius;fx.trailLifetime=recipe.trail_lifetime;fx.intensity=recipe.intensity;fx.segments=recipe.segments;fx.particleCount=recipe.particle_count;fx.seed=recipe.seed;fx.effectMaterial=material;fx.solidMaterial=solid;fx.playing=true;
        // AddComponent calls OnEnable before recipe assignment; recreate only the preview children.
        foreach(Transform child in root.transform.Cast<Transform>().ToArray())UnityEngine.Object.DestroyImmediate(child.gameObject);
        fx.enabled=false;fx.enabled=true;fx.Seek(.32f);
        var floor=GameObject.CreatePrimitive(PrimitiveType.Plane);floor.name="AFS_PreviewGround";floor.transform.localScale=Vector3.one*5f;var ground=new Material(Shader.Find("Standard")){name="AFS_PreviewGroundMaterial"};ground.color=new Color(.055f,.065f,.08f);AssetDatabase.CreateAsset(ground,Root+"/Ground.mat");floor.GetComponent<Renderer>().sharedMaterial=ground;
        var light=new GameObject("AFS_KeyLight").AddComponent<Light>();light.type=LightType.Directional;light.intensity=1.6f;light.transform.rotation=Quaternion.Euler(40,-35,0);RenderSettings.ambientLight=new Color(.3f,.33f,.4f);
        var camera=new GameObject("AFS_PreviewCamera").AddComponent<Camera>();camera.transform.position=new Vector3(3.4f,2.8f,-4.5f);camera.transform.LookAt(new Vector3(0,1.3f,0));camera.backgroundColor=new Color(.025f,.032f,.045f);camera.clearFlags=CameraClearFlags.SolidColor;camera.fieldOfView=42;camera.nearClipPlane=.05f;camera.farClipPlane=100;
        var renders=new List<Dictionary<string,object>>();
        for(int i=0;i<request.frames;i++){float t=i*recipe.duration/request.frames;fx.Seek(t);string name="frame_"+i.ToString("D3")+".png";Capture(camera,name);renders.Add(new Dictionary<string,object>{{"file",name},{"seconds",t},{"width",request.width},{"height",request.height}});Check(fx.TrailVertices()==(recipe.segments+1)*2,"Runtime mesh sample count");}
        fx.Seek(.32f);floor.SetActive(false);root.transform.Find("AFS_PreviewSword").gameObject.SetActive(false);Capture(camera,"effect_isolation.png");var image=new Texture2D(2,2);image.LoadImage(File.ReadAllBytes(Path.Combine(request.outputPath,"effect_isolation.png")));int visible=image.GetPixels32().Count(c=>c.r>60||c.g>60||c.b>60);Check(visible>50,"Effect-only GPU capture must contain visible effect pixels");UnityEngine.Object.DestroyImmediate(image);floor.SetActive(true);root.transform.Find("AFS_PreviewSword").gameObject.SetActive(true);
        fx.Seek(0);var prefab=PrefabUtility.SaveAsPrefabAsset(root,Root+"/AFS_Effect.prefab");Check(prefab,"Editable native effect prefab saved");EditorSceneManager.SaveScene(root.scene,Root+"/AFS_EffectPreview.unity");AssetDatabase.SaveAssets();AssetDatabase.ExportPackage(Root,Path.Combine(request.outputPath,"AFS_Effect.unitypackage"),ExportPackageOptions.Recurse|ExportPackageOptions.IncludeDependencies);
        report["renders"]=renders;report["effect_only_visible_pixels"]=visible;report["element"]=recipe.element;report["runtime_mesh_vertices"]=(recipe.segments+1)*2;report["preview_motion"]="Deterministic procedural three-swing sword demonstration; no humanoid/retarget validation";report["player_performance"]="NOT_TESTED";
    }
    static void Capture(Camera camera,string name){var rt=new RenderTexture(request.width,request.height,24,RenderTextureFormat.ARGB32);camera.targetTexture=rt;camera.Render();RenderTexture.active=rt;var image=new Texture2D(request.width,request.height,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,request.width,request.height),0,0);image.Apply();File.WriteAllBytes(Path.Combine(request.outputPath,name),image.EncodeToPNG());camera.targetTexture=null;RenderTexture.active=null;UnityEngine.Object.DestroyImmediate(image);rt.Release();UnityEngine.Object.DestroyImmediate(rt);}
    public static void Reopen(){Load();var report=new Dictionary<string,object>();try{EditorSceneManager.OpenScene(Root+"/AFS_EffectPreview.unity");var fx=UnityEngine.Object.FindFirstObjectByType<AFSSlashEffect>();Check(fx,"Cold scene reopen retains runtime effect");if(fx){fx.Seek(.32f);var a=fx.transform.Find("AFS_PreviewSword").localRotation;fx.Seek(.5f);var b=fx.transform.Find("AFS_PreviewSword").localRotation;Check(Quaternion.Angle(a,b)>1,"Runtime weapon path changes over time");Check(fx.TrailVertices()==(recipe.segments+1)*2,"Cold reopen reconstructs runtime trail");Check(fx.effectMaterial&&fx.solidMaterial,"Cold reopen retains native materials");Check(fx.element==recipe.element,"Recipe element retained");}Check(File.Exists(Root+"/Runtime/AFSSlashEffect.cs")&&File.Exists(Root+"/Runtime/AFSSlash.shader"),"Editable runtime sources included");}catch(Exception e){errors.Add(e.ToString());}Report("fx_reopen.json",report);}
}
