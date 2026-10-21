// Native TerrainData/Scene/NavMesh serialization. All inputs are schema-validated AFS data.
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.AI;
using UnityEngine.Rendering;

public static class AFSWorldBuilder {
    [Serializable] class Point { public float x,z; }
    [Serializable] class Spawn : Point { public string id; }
    [Serializable] class Zone : Spawn { public float width_m,depth_m; }
    [Serializable] class Road { public string id;public float width_m;public Point[] points; }
    [Serializable] class Prop : Point { public string prefab_path;public float yaw_degrees,scale; }
    [Serializable] class Plan { public string name;public float width_m,depth_m,max_height_m;public int resolution;public Point goal;public Spawn[] spawns;public Zone[] build_zones;public Road[] roads; }
    [Serializable] class Request { public string outputPath,configHash;public Prop[] props;public bool render; }
    static Request config;static Plan plan;static readonly List<string> failures=new List<string>();
    const string Root="Assets/AFS/World";
    static string Project => Directory.GetParent(Application.dataPath).FullName;
    static void Load(){config=JsonUtility.FromJson<Request>(File.ReadAllText(Path.Combine(Project,"WorldRequest.json")));plan=JsonUtility.FromJson<Plan>(File.ReadAllText(Root+"/Sources/world_plan.json"));}
    static void Check(bool ok,string message){if(!ok)failures.Add(message);}
    static void Report(string name,Dictionary<string,object> report){report["checks_passed"]=failures.Count==0;report["failures"]=failures;report["unity_version"]=Application.unityVersion;report["config_hash"]=config.configHash;report["game_ready"]=false;File.WriteAllText(Path.Combine(config.outputPath,name),AssetForgeImport.Json(report));EditorApplication.Exit(failures.Count==0?0:1);}
    public static void Run(){Load();var report=new Dictionary<string,object>();try{Build(report);}catch(Exception e){failures.Add(e.ToString());Debug.LogException(e);}Report("world_unity_report.json",report);}
    static void Build(Dictionary<string,object> report){
        EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
        int r=plan.resolution;var bytes=File.ReadAllBytes(Root+"/Sources/height.raw");Check(bytes.Length==r*r*2,"RAW height dimensions");
        var heights=new float[r,r];for(int z=0;z<r;z++)for(int x=0;x<r;x++){int i=(z*r+x)*2;heights[z,x]=(bytes[i]+256*bytes[i+1])/65535f;}
        var data=new TerrainData();data.name="AFSWorldTerrain";data.heightmapResolution=r;data.size=new Vector3(plan.width_m,plan.max_height_m,plan.depth_m);data.SetHeights(0,0,heights);
        var layers=new TerrainLayer[2];string[] names={"grass","road"};for(int i=0;i<2;i++){var importer=(TextureImporter)AssetImporter.GetAtPath(Root+"/Sources/"+names[i]+".png");importer.sRGBTexture=true;importer.textureCompression=TextureImporterCompression.Uncompressed;importer.SaveAndReimport();var layer=new TerrainLayer();layer.diffuseTexture=AssetDatabase.LoadAssetAtPath<Texture2D>(Root+"/Sources/"+names[i]+".png");layer.tileSize=new Vector2(8,8);AssetDatabase.CreateAsset(layer,Root+"/"+names[i]+".terrainlayer");layers[i]=layer;}
        data.terrainLayers=layers;data.alphamapResolution=128;var alpha=new float[128,128,2];var maskBytes=File.ReadAllBytes(Root+"/Sources/roads.raw");Check(maskBytes.Length==r*r,"Road raw mask dimensions");
        for(int z=0;z<128;z++)for(int x=0;x<128;x++){int iz=Mathf.RoundToInt(z/127f*(r-1)),ix=Mathf.RoundToInt(x/127f*(r-1));float road=maskBytes[iz*r+ix]/255f;alpha[z,x,0]=1-road;alpha[z,x,1]=road;}
        AssetDatabase.CreateAsset(data,Root+"/TerrainData.asset");var terrain=Terrain.CreateTerrainGameObject(data).GetComponent<Terrain>();terrain.name="AFS_Editable_Terrain";data.SetAlphamaps(0,0,alpha);terrain.Flush();EditorUtility.SetDirty(data);report["source_road_alpha"]=alpha[13,32,1];report["native_road_alpha"]=data.GetAlphamaps(32,13,1,1)[0,0,1];
        Check(terrain.GetComponent<TerrainCollider>()!=null,"Terrain collider missing");
        var layout=new GameObject("AFS_Gameplay_Layout");
        foreach(var spawn in plan.spawns)Marker("Spawn_"+spawn.id,spawn,terrain,Color.cyan,layout.transform);
        Marker("Goal",plan.goal,terrain,Color.red,layout.transform);
        foreach(var zone in plan.build_zones){var obj=GameObject.CreatePrimitive(PrimitiveType.Cube);obj.name="BuildZone_"+zone.id;obj.transform.SetParent(layout.transform);obj.transform.position=At(zone,terrain)+Vector3.up*.03f;obj.transform.localScale=new Vector3(zone.width_m,.04f,zone.depth_m);UnityEngine.Object.DestroyImmediate(obj.GetComponent<Collider>());obj.GetComponent<Renderer>().sharedMaterial=Material(new Color(.25f,.5f,.35f));}
        foreach(var road in plan.roads){var path=new GameObject("Road_"+road.id);path.transform.SetParent(layout.transform);foreach(var p in road.points){var node=new GameObject("Waypoint");node.transform.SetParent(path.transform);node.transform.position=At(p,terrain);}}
        var propRoot=new GameObject("AFS_Library_Props");foreach(var prop in config.props){var source=AssetDatabase.LoadAssetAtPath<GameObject>(prop.prefab_path);Check(source!=null,"Library prefab missing");if(source==null)continue;var instance=(GameObject)PrefabUtility.InstantiatePrefab(source);instance.transform.SetParent(propRoot.transform);instance.transform.position=At(prop,terrain);instance.transform.rotation=Quaternion.Euler(0,prop.yaw_degrees,0);instance.transform.localScale=Vector3.one*prop.scale;}
        Physics.SyncTransforms();var sources=new List<NavMeshBuildSource>();var bounds=new Bounds(new Vector3(plan.width_m/2,plan.max_height_m/2,plan.depth_m/2),new Vector3(plan.width_m+10,plan.max_height_m+40,plan.depth_m+10));
        NavMeshBuilder.CollectSources(bounds,~0,NavMeshCollectGeometry.PhysicsColliders,0,new List<NavMeshBuildMarkup>(),sources);
        var settings=NavMesh.GetSettingsByIndex(0);settings.agentRadius=.5f;settings.agentHeight=1.8f;settings.agentSlope=30;settings.agentClimb=.4f;settings.overrideVoxelSize=true;settings.voxelSize=.5f;
        var nav=NavMeshBuilder.BuildNavMeshData(settings,sources,bounds,Vector3.zero,Quaternion.identity);Check(nav!=null,"Native NavMesh generation failed");
        AssetDatabase.CreateAsset(nav,Root+"/Navigation.asset");NavMesh.RemoveAllNavMeshData();NavMesh.AddNavMeshData(nav);
        var loaderType=Type.GetType("AFSWorldNavigation, Assembly-CSharp");Check(loaderType!=null,"Runtime navigation loader did not compile");
        if(loaderType!=null){var loader=new GameObject("AFS_Navigation").AddComponent(loaderType);var serialized=new SerializedObject(loader);serialized.FindProperty("data").objectReferenceValue=nav;serialized.ApplyModifiedPropertiesWithoutUndo();}
        ValidateRoadPaint(terrain);ValidateProps();report["navigation"]=Navigation(terrain);report["terrain_resolution"]=r;report["terrain_size_m"]=new[]{data.size.x,data.size.y,data.size.z};report["prop_instances"]=config.props.Length;report["build_zones"]=plan.build_zones.Length;report["physics_sources"]=sources.Count;
        if(config.render)Render(terrain,report);else report["render_status"]="NOT_REQUESTED";
        AssetDatabase.SaveAssets();EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene(),Root+"/RunavelleWorld.unity");
        AssetDatabase.ExportPackage("Assets/AFS",Path.Combine(config.outputPath,"AFS_World.unitypackage"),ExportPackageOptions.Recurse|ExportPackageOptions.IncludeDependencies);
        report["scene_path"]=Root+"/RunavelleWorld.unity";report["terrain_path"]=Root+"/TerrainData.asset";report["navmesh_path"]=Root+"/Navigation.asset";report["performance"]="NOT_TESTED_IN_PLAYER";report["artistic_quality"]="NEEDS_HUMAN_REVIEW";
    }
    static Vector3 At(Point p,Terrain terrain){return new Vector3(p.x,terrain.SampleHeight(new Vector3(p.x,0,p.z)),p.z);}
    static Material Material(Color color){string file=Root+"/Marker_"+ColorUtility.ToHtmlStringRGB(color)+".mat";var saved=AssetDatabase.LoadAssetAtPath<Material>(file);if(saved!=null)return saved;var m=new Material(Shader.Find("Standard"));m.color=color;AssetDatabase.CreateAsset(m,file);return m;}
    static void Marker(string name,Point p,Terrain terrain,Color color,Transform parent){var g=GameObject.CreatePrimitive(PrimitiveType.Sphere);g.name=name;g.transform.SetParent(parent);g.transform.position=At(p,terrain)+Vector3.up;g.transform.localScale=Vector3.one*2;UnityEngine.Object.DestroyImmediate(g.GetComponent<Collider>());g.GetComponent<Renderer>().sharedMaterial=Material(color);}
    static object Navigation(Terrain terrain){var result=new Dictionary<string,object>();foreach(var spawn in plan.spawns){NavMeshHit a=new NavMeshHit(),b=new NavMeshHit();bool sampled=NavMesh.SamplePosition(At(spawn,terrain),out a,3,NavMesh.AllAreas)&&NavMesh.SamplePosition(At(plan.goal,terrain),out b,3,NavMesh.AllAreas);var path=new NavMeshPath();bool reachable=sampled&&NavMesh.CalculatePath(a.position,b.position,NavMesh.AllAreas,path)&&path.status==NavMeshPathStatus.PathComplete;Check(reachable,"Native spawn-to-goal navigation failed: "+spawn.id);result[spawn.id]=new Dictionary<string,object>{["reachable"]=reachable,["corners"]=path.corners.Length};}return result;}
    public static void Reopen(){Load();var report=new Dictionary<string,object>();try{NavMesh.RemoveAllNavMeshData();EditorSceneManager.OpenScene(Root+"/RunavelleWorld.unity",OpenSceneMode.Single);var terrain=UnityEngine.Object.FindFirstObjectByType<Terrain>();Check(terrain!=null,"Saved Terrain did not reopen");if(terrain!=null){Check(terrain.terrainData!=null&&terrain.terrainData.heightmapResolution==plan.resolution,"TerrainData resolution mismatch");Check(terrain.GetComponent<TerrainCollider>()!=null,"Saved TerrainCollider missing");Check(terrain.terrainData.terrainLayers.Length==2,"Saved terrain layers missing");ValidateRoadPaint(terrain);report["navigation"]=Navigation(terrain);}ValidateProps();report["prop_instances"]=config.props.Length;Check(AssetDatabase.LoadAssetAtPath<NavMeshData>(Root+"/Navigation.asset")!=null,"Saved native NavMeshData missing");report["scope"]="Separate Editor process reopened native scene, TerrainData, layers, collider, props and runtime-loaded NavMeshData";}catch(Exception e){failures.Add(e.ToString());}Report("world_unity_reopen.json",report);}
    static void ValidateRoadPaint(Terrain terrain){var data=terrain.terrainData;foreach(var spawn in plan.spawns){int x=Mathf.Clamp(Mathf.RoundToInt(spawn.x/plan.width_m*(data.alphamapWidth-1)),0,data.alphamapWidth-1);int z=Mathf.Clamp(Mathf.RoundToInt(spawn.z/plan.depth_m*(data.alphamapHeight-1)),0,data.alphamapHeight-1);float weight=data.GetAlphamaps(x,z,1,1)[0,0,1];Check(weight>.5f,"Road mask orientation/paint at spawn failed: "+spawn.id+" point="+spawn.x+","+spawn.z+" pixel="+x+","+z+" weight="+weight);}}
    static void ValidateProps(){var root=GameObject.Find("AFS_Library_Props");Check(root!=null&&root.transform.childCount==config.props.Length,"Saved library prop count mismatch");if(root==null)return;for(int i=0;i<Math.Min(root.transform.childCount,config.props.Length);i++){var child=root.transform.GetChild(i);var expected=config.props[i];Check(PrefabUtility.GetPrefabAssetPathOfNearestInstanceRoot(child.gameObject)==expected.prefab_path,"Prop lost native prefab reference");Check(Mathf.Abs(child.position.x-expected.x)<.001f&&Mathf.Abs(child.position.z-expected.z)<.001f,"Prop position changed");Check(Vector3.Distance(child.localScale,Vector3.one*expected.scale)<.001f,"Prop scale changed");}}
    static void Render(Terrain terrain,Dictionary<string,object> report){
        Check(SystemInfo.graphicsDeviceType!=GraphicsDeviceType.Null,"World render has no GPU device");RenderSettings.ambientMode=AmbientMode.Flat;RenderSettings.ambientLight=new Color(.5f,.52f,.55f);var light=new GameObject("World_Sun").AddComponent<Light>();light.type=LightType.Directional;light.intensity=1.1f;light.transform.rotation=Quaternion.Euler(50,-30,0);light.shadows=LightShadows.Soft;
        var camera=new GameObject("World_Overview_Camera").AddComponent<Camera>();camera.orthographic=true;camera.orthographicSize=Math.Max(plan.width_m,plan.depth_m)*.55f;camera.nearClipPlane=.1f;camera.farClipPlane=2000;camera.clearFlags=CameraClearFlags.SolidColor;camera.backgroundColor=new Color(.08f,.11f,.14f);
        foreach(var group in UnityEngine.Object.FindObjectsByType<LODGroup>(FindObjectsSortMode.None))group.ForceLOD(0);
        var center=new Vector3(plan.width_m/2,0,plan.depth_m/2);camera.transform.position=center+new Vector3(0,Math.Max(plan.width_m,plan.depth_m)*1.5f,0);camera.transform.rotation=Quaternion.Euler(90,0,0);Capture(camera,1280,1280,"world_overview.png");
        camera.orthographicSize=30;var focus=new Vector3(plan.width_m*.4f,2,plan.depth_m*.45f);camera.transform.position=focus+new Vector3(35,35,-35);camera.transform.LookAt(focus);Capture(camera,1920,1080,"world_gameplay_preview.png");foreach(var group in UnityEngine.Object.FindObjectsByType<LODGroup>(FindObjectsSortMode.None))group.ForceLOD(-1);
        report["render_status"]="ACTUAL_UNITY_CAMERA_RENDER";report["preview_lod_policy"]="LOD0 forced only for captures; saved scene restores automatic LODs; not player FPS";
    }
    static void Capture(Camera camera,int width,int height,string filename){camera.aspect=(float)width/height;var target=new RenderTexture(width,height,24,RenderTextureFormat.ARGB32);target.Create();camera.targetTexture=target;camera.Render();var prior=RenderTexture.active;RenderTexture.active=target;var image=new Texture2D(width,height,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,width,height),0,0);image.Apply();File.WriteAllBytes(Path.Combine(config.outputPath,filename),image.EncodeToPNG());RenderTexture.active=prior;camera.targetTexture=null;target.Release();UnityEngine.Object.DestroyImmediate(image);UnityEngine.Object.DestroyImmediate(target);}
}
