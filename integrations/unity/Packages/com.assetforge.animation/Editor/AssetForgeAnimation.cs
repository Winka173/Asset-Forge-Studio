// Existing single-clip, untextured Generic rigs only. No humanoid/retarget claim.
using System;
using System.Collections;
using System.Globalization;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;

public static class AssetForgeAnimation
{
    [Serializable] private class Request { public string outputPath, fbxPath, sourcePath, packagePath, effectiveConfigHash; public float duration; public int bones; }
    [Serializable] private class Bridge { public float[] source_dimensions; public float source_motion_m; }
    private const string Root="Assets/AFS";
    private static Request Config;
    private static List<string> Failures;
    private static Dictionary<string,object> Report;
    public static void Run(){Execute("unity_report.json",false,false);}
    public static void Reopen(){Execute("unity_reopen_report.json",true,false);}
    public static void CleanImport(){Execute("unity_clean_import_report.json",true,true);}
    private static void Check(bool value,string message){if(!value)Failures.Add(message);}
    private static bool Finite(float value){return !float.IsNaN(value)&&!float.IsInfinity(value);}
    private static void Execute(string report,bool reopen,bool clean)
    {
        Config=JsonUtility.FromJson<Request>(File.ReadAllText(Path.Combine(Directory.GetParent(Application.dataPath).FullName,"AnimationRequest.json")));
        Failures=new List<string>();Report=new Dictionary<string,object>{["unity_version"]=Application.unityVersion,["effective_config_hash"]=Config.effectiveConfigHash,["cold_reopen"]=reopen,["clean_package_import"]=report.Contains("clean"),["root_motion_quality"]="not_evaluated",["foot_contact_quality"]="not_evaluated",["artistic_approval"]="not_given"};
        Application.logMessageReceived+=(message,trace,type)=>{if(type==LogType.Error||type==LogType.Exception||type==LogType.Assert)Failures.Add(message);};
        try
        {
            if(clean)
            {
                AssetDatabase.importPackageCompleted+=name=>EditorApplication.delayCall+=()=>Execute(report,true,false);
                AssetDatabase.importPackageFailed+=(name,error)=>{Debug.LogError(error);EditorApplication.Exit(1);};
                AssetDatabase.ImportPackage(Config.packagePath,false);return;
            }
            if(!reopen)Build();
            Validate(reopen);
            if(!reopen&&Failures.Count==0)AssetDatabase.ExportPackage(Root,Config.packagePath,ExportPackageOptions.Recurse|ExportPackageOptions.IncludeDependencies);
        }
        catch(Exception error){Failures.Add(error.ToString());Debug.LogException(error);}
        Report["failures"]=Failures;Report["checks_passed"]=Failures.Count==0;
        File.WriteAllText(Path.Combine(Config.outputPath,report),Json(Report));
        EditorApplication.Exit(Failures.Count==0?0:1);
    }
    private static AnimationClip[] Clips(){return AssetDatabase.LoadAllAssetsAtPath(Root+"/Input/Animation.fbx").OfType<AnimationClip>().Where(c=>!c.name.StartsWith("__preview__")).ToArray();}
    private static void Build()
    {
        Directory.CreateDirectory(Root+"/Input");Directory.CreateDirectory(Root+"/Output");
        File.Copy(Config.fbxPath,Root+"/Input/Animation.fbx",false);
        File.Copy(Config.sourcePath,Root+"/Input/Original.glb",false);
        AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        var importer=AssetImporter.GetAtPath(Root+"/Input/Animation.fbx") as ModelImporter;
        if(importer==null)throw new Exception("Missing FBX importer");
        importer.animationType=ModelImporterAnimationType.Generic;
        importer.avatarSetup=ModelImporterAvatarSetup.CreateFromThisModel;
        importer.importAnimation=true;importer.animationCompression=ModelImporterAnimationCompression.Off;
        importer.resampleCurves=false;importer.optimizeGameObjects=false;
        importer.meshCompression=ModelImporterMeshCompression.Off;importer.isReadable=true;
        importer.skinWeights=ModelImporterSkinWeights.Custom;importer.maxBonesPerVertex=4;importer.minBoneWeight=0;importer.optimizeBones=false;
        importer.importNormals=ModelImporterNormals.Import;importer.importTangents=ModelImporterTangents.Import;
        importer.SaveAndReimport();
        var clips=Clips();if(clips.Length!=1)throw new Exception("Expected one real FBX clip, got "+clips.Length);
        var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
        var model=AssetDatabase.LoadAssetAtPath<GameObject>(Root+"/Input/Animation.fbx");
        var instance=(GameObject)PrefabUtility.InstantiatePrefab(model);instance.name="AFS Animated Asset";
        var animator=instance.GetComponent<Animator>();if(animator==null)animator=instance.AddComponent<Animator>();
        var controller=AnimatorController.CreateAnimatorControllerAtPath(Root+"/Output/AFS_Animation.controller");
        var state=controller.layers[0].stateMachine.AddState("Source clip");state.motion=clips[0];controller.layers[0].stateMachine.defaultState=state;
        animator.runtimeAnimatorController=controller;animator.applyRootMotion=false;animator.cullingMode=AnimatorCullingMode.AlwaysAnimate;
        PrefabUtility.SaveAsPrefabAsset(instance,Root+"/Output/AFS_Animated.prefab");
        EditorSceneManager.SaveScene(scene,Root+"/Output/AFS_Animation.unity");AssetDatabase.SaveAssets();
    }
    private static Vector3[] Bake(GameObject instance)
    {
        var points=new List<Vector3>();
        foreach(var renderer in instance.GetComponentsInChildren<SkinnedMeshRenderer>())
        {
            var mesh=new Mesh();renderer.BakeMesh(mesh,true);
            foreach(var p in mesh.vertices){var v=renderer.transform.TransformPoint(p);Check(Finite(v.x)&&Finite(v.y)&&Finite(v.z),"Nonfinite skinned vertex");points.Add(v);}
            UnityEngine.Object.DestroyImmediate(mesh);
        }
        foreach(var filter in instance.GetComponentsInChildren<MeshFilter>())
            if(filter.sharedMesh!=null)foreach(var vertex in filter.sharedMesh.vertices)points.Add(filter.transform.TransformPoint(vertex));
        return points.ToArray();
    }
    private static void Validate(bool reopen)
    {
        AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        if(reopen){EditorSceneManager.OpenScene(Root+"/Output/AFS_Animation.unity");Check(UnityEngine.Object.FindObjectsByType<Animator>(FindObjectsSortMode.None).Length>0,"Saved scene lost animator");}
        var prefab=AssetDatabase.LoadAssetAtPath<GameObject>(Root+"/Output/AFS_Animated.prefab");Check(prefab!=null,"Saved animated prefab missing");if(prefab==null)return;
        var instance=UnityEngine.Object.Instantiate(prefab);var animator=instance.GetComponent<Animator>();
        Check(animator!=null&&animator.runtimeAnimatorController!=null,"Animator/controller reference missing");
        var clips=Clips();Check(clips.Length==1,"Clip count changed");if(clips.Length!=1)return;var clip=clips[0];
        Check(Mathf.Abs(clip.length-Config.duration)<=1f/120f+.001f,"Clip duration changed");Check(!clip.legacy,"Generic clip unexpectedly legacy");
        var renderers=instance.GetComponentsInChildren<SkinnedMeshRenderer>();Check(renderers.Length>0,"No actual skinned mesh");
        var bones=new HashSet<Transform>();int weighted=0;float minWeight=float.MaxValue,maxWeight=0;
        foreach(var renderer in renderers)
        {
            Check(renderer.sharedMesh!=null,"Skinned mesh reference missing");foreach(var bone in renderer.bones){Check(bone!=null,"Bone reference missing");if(bone!=null)bones.Add(bone);}
            var mesh=renderer.sharedMesh;Check(mesh.bindposes.Length==renderer.bones.Length,"Bind pose/bone count mismatch");
            foreach(var weight in mesh.boneWeights)
            {
                var values=new[]{weight.weight0,weight.weight1,weight.weight2,weight.weight3};var indices=new[]{weight.boneIndex0,weight.boneIndex1,weight.boneIndex2,weight.boneIndex3};float sum=0;
                for(int n=0;n<4;n++){Check(Finite(values[n])&&values[n]>=0,"Invalid bone weight");if(values[n]>0)Check(indices[n]>=0&&indices[n]<renderer.bones.Length,"Invalid weighted bone index");sum+=values[n];}
                Check(Mathf.Abs(sum-1)<.002f,"Weights not normalized");minWeight=Mathf.Min(minWeight,sum);maxWeight=Mathf.Max(maxWeight,sum);weighted++;
            }
        }
        Check(bones.Count==Config.bones,"Bone count changed from GLB");Check(weighted>0,"No weighted vertices");
        var poses=new List<Vector3[]>();
        foreach(float ratio in new[]{0f,.2f,.4f,.6f,.8f,1f}){clip.SampleAnimation(instance,Mathf.Min(clip.length,Config.duration*ratio));poses.Add(Bake(instance));}
        float movement=0;foreach(var pose in poses.Skip(1)){Check(pose.Length==poses[0].Length,"Deformed vertex count changed");for(int n=0;n<Math.Min(pose.Length,poses[0].Length);n++)movement=Mathf.Max(movement,Vector3.Distance(pose[n],poses[0][n]));}
        Check(movement>1e-6f,"Clip sampling produced no measurable deformation");
        var bridge=JsonUtility.FromJson<Bridge>(File.ReadAllText(Path.Combine(Config.outputPath,"fbx_qa.json")));
        var min=poses[0][0];var max=min;foreach(var point in poses[0]){min=Vector3.Min(min,point);max=Vector3.Max(max,point);}var size=max-min;
        var dimensions=new[]{size.x,size.y,size.z};var expected=bridge.source_dimensions.OrderBy(v=>v).ToArray();var actual=dimensions.OrderBy(v=>v).ToArray();
        for(int n=0;n<3;n++)Check(Mathf.Abs(actual[n]-expected[n])<Mathf.Max(.005f,expected[n]*.005f),"Metric dimensions changed through FBX");
        Check(Mathf.Abs(movement-bridge.source_motion_m)<Mathf.Max(.005f,bridge.source_motion_m*.02f),"Motion amplitude changed through FBX");
        Report["dimensions_xyz_m"]=dimensions;Report["source_motion_m"]=bridge.source_motion_m;
        // Independently drive the Generic clip through Unity's animation graph.
        var graph=PlayableGraph.Create("AFS CPU animation QA");graph.SetTimeUpdateMode(DirectorUpdateMode.Manual);
        try
        {
            var playable=AnimationClipPlayable.Create(graph,clip);playable.SetApplyFootIK(false);playable.SetApplyPlayableIK(false);
            var output=AnimationPlayableOutput.Create(graph,"Animation",animator);output.SetSourcePlayable(playable);graph.Play();
            playable.SetTime(0);graph.Evaluate(0);var first=Bake(instance);
            playable.SetTime(clip.length*.4);graph.Evaluate(0);var next=Bake(instance);float runtimeMotion=0;
            for(int n=0;n<Math.Min(first.Length,next.Length);n++)runtimeMotion=Mathf.Max(runtimeMotion,Vector3.Distance(first[n],next[n]));
            Check(runtimeMotion>1e-6f,"Playable graph produced no skinned motion");Report["playable_graph_motion_m"]=runtimeMotion;
        }
        finally{graph.Destroy();}
        Report["clip_duration_seconds"]=clip.length;Report["bone_count"]=bones.Count;Report["weighted_vertices"]=weighted;Report["min_weight_sum"]=minWeight;Report["max_weight_sum"]=maxWeight;Report["sampled_motion_m"]=movement;Report["samples"]=6;
        UnityEngine.Object.DestroyImmediate(instance);
    }
    internal static string Json(object value)
    {
        if (value == null) return "null"; if (value is string text) return "\"" + text.Replace("\\","\\\\").Replace("\"","\\\"").Replace("\n","\\n").Replace("\r","\\r").Replace("\t","\\t") + "\"";
        if (value is bool boolean) return boolean ? "true" : "false";
        if (value is IDictionary dictionary) { var entries = new List<string>(); foreach (DictionaryEntry entry in dictionary) entries.Add(Json(entry.Key.ToString()) + ":" + Json(entry.Value)); return "{" + String.Join(",",entries) + "}"; }
        if (value is IEnumerable enumerable) { var items = new List<string>(); foreach (var item in enumerable) items.Add(Json(item)); return "[" + String.Join(",",items) + "]"; }
        return Convert.ToString(value,CultureInfo.InvariantCulture);
    }
}
