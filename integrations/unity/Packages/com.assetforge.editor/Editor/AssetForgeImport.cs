// Isolated Editor QA only. No production game project or source asset is modified.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

public static class AssetForgeImport
{
    [Serializable] private class Request { public string outputPath; public string mode; public int[] expectedTriangles; public float expectedHeight; public string effectiveConfigHash; }
    private static readonly List<string> Failures = new List<string>();
    private static readonly List<string> Warnings = new List<string>();
    private static Dictionary<string, object> Report;
    private static Request Config;
    private const string Root = "Assets/AFS/Input";

    public static void Run()
    {
        Config = JsonUtility.FromJson<Request>(File.ReadAllText(Path.Combine(Directory.GetParent(Application.dataPath).FullName, "QARequest.json")));
        Report = new Dictionary<string, object> { ["unity_version"] = Application.unityVersion, ["mode"] = Config.mode,
            ["graphics_device"] = SystemInfo.graphicsDeviceName, ["graphics_api"] = SystemInfo.graphicsDeviceType.ToString(),
            ["platform"] = Application.platform.ToString(), ["effective_config_hash"] = Config.effectiveConfigHash, ["render_pipeline"] = "Built-in", ["importer_version"] = "0.1.0", ["mobile_device_performance"] = "NOT_TESTED",
            ["geometry_quality"] = "NEEDS_HUMAN_REVIEW", ["mesh_quality_parity"] = "NOT_TESTED" };
        Application.logMessageReceived += (message, trace, type) => { if (type == LogType.Error || type == LogType.Exception || type == LogType.Assert) Failures.Add(message); else if (type == LogType.Warning) Warnings.Add(message); };
        try { Validate(); }
        catch (Exception exception) { Failures.Add(exception.ToString()); Debug.LogException(exception); }
        Report["failures"] = Failures.ToArray(); Report["warnings"] = Warnings.ToArray(); Report["checks_passed"] = Failures.Count == 0;
        Directory.CreateDirectory(Config.outputPath);
        File.WriteAllText(Path.Combine(Config.outputPath, "unity_report.json"), Json(Report), new UTF8Encoding(false));
        Debug.Log("ASSET_FORGE_VALIDATION_COMPLETE checks_passed=" + (Failures.Count == 0));
        EditorApplication.Exit(Failures.Count == 0 ? 0 : 1);
    }

    private static void Check(bool condition, string name) { if (!condition) Failures.Add(name); }
    private static void Validate()
    {
        AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        var lodRecords = new List<object>(); var automaticMaterials = new List<object>(); var prefabs = new List<GameObject>();
        for (int level = 0; level < 4; level++)
        {
            string path = Root + "/LOD" + level + ".fbx";
            var importer = AssetImporter.GetAtPath(path) as ModelImporter;
            Check(importer != null, "FBX importer missing: " + path); if (importer == null) continue;
            importer.importNormals = ModelImporterNormals.Import;
            importer.globalScale = 1; importer.useFileScale = true; importer.isReadable = true;
            importer.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
            importer.importCameras = false; importer.importLights = false; importer.animationType = ModelImporterAnimationType.None;
            importer.SaveAndReimport();
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);
            Check(prefab != null, "FBX did not produce model: " + path); if (prefab == null) continue;
            prefabs.Add(prefab);
            var meshRecords = new List<object>(); long triangles = 0; int vertices = 0;
            foreach (var filter in prefab.GetComponentsInChildren<MeshFilter>(true))
            {
                var mesh = filter.sharedMesh; if (mesh == null) continue;
                long count = 0; for (int sub = 0; sub < mesh.subMeshCount; sub++) count += (long)mesh.GetIndexCount(sub) / 3;
                triangles += count; vertices += mesh.vertexCount;
                Check(mesh.HasVertexAttribute(VertexAttribute.Normal), "Normals missing LOD" + level);
                Check(mesh.HasVertexAttribute(VertexAttribute.TexCoord0), "UV0 missing LOD" + level);
                meshRecords.Add(new Dictionary<string, object> { ["name"] = mesh.name, ["triangles"] = count, ["vertices"] = mesh.vertexCount,
                    ["submeshes"] = mesh.subMeshCount, ["normal_count"] = mesh.normals.Length, ["uv0_count"] = mesh.uv.Length });
            }
            foreach (var renderer in prefab.GetComponentsInChildren<Renderer>(true))
                foreach (var material in renderer.sharedMaterials)
                    automaticMaterials.Add(MaterialFacts(material, "automatic FBX importer / LOD" + level));
            Check(triangles == Config.expectedTriangles[level], "Triangle count differs from Blender LOD" + level + ": " + triangles);
            lodRecords.Add(new Dictionary<string, object> { ["level"] = level, ["source"] = path, ["triangles"] = triangles, ["vertices"] = vertices,
                ["matches_blender_triangles"] = triangles == Config.expectedTriangles[level], ["meshes"] = meshRecords });
        }
        Report["lods"] = lodRecords; Report["automatic_fbx_materials"] = automaticMaterials;
        Check(prefabs.Count == 4, "Expected four imported FBX LODs"); if (prefabs.Count != 4) return;
        ConfigureTexture(Root + "/textures/texture_000.png", true);
        ConfigureTexture(Root + "/textures/Unity_MetallicSmoothness.png", false);
        var baseColor = AssetDatabase.LoadAssetAtPath<Texture2D>(Root + "/textures/texture_000.png");
        var metallicSmoothness = AssetDatabase.LoadAssetAtPath<Texture2D>(Root + "/textures/Unity_MetallicSmoothness.png");
        Check(baseColor != null && metallicSmoothness != null, "Required source/converted texture missing");
        var materialAsset = AssetDatabase.LoadAssetAtPath<Material>("Assets/AFS/Output/AFS_Standard.mat");
        if (materialAsset == null) { materialAsset = new Material(Shader.Find("Standard")); AssetDatabase.CreateAsset(materialAsset, "Assets/AFS/Output/AFS_Standard.mat"); }
        materialAsset.shader = Shader.Find("Standard"); materialAsset.color = Color.white; materialAsset.mainTexture = baseColor;
        materialAsset.SetTexture("_MetallicGlossMap", metallicSmoothness); materialAsset.SetFloat("_Metallic", 1f);
        materialAsset.SetFloat("_GlossMapScale", 1f); materialAsset.SetFloat("_Glossiness", 1f); materialAsset.EnableKeyword("_METALLICGLOSSMAP");
        materialAsset.DisableKeyword("_EMISSION"); materialAsset.SetColor("_EmissionColor", Color.black);
        EditorUtility.SetDirty(materialAsset); AssetDatabase.SaveAssets();
        Check(materialAsset.mainTexture == baseColor && materialAsset.GetTexture("_MetallicGlossMap") == metallicSmoothness, "Unity Standard material map assignment failed");
        Report["assigned_material"] = MaterialFacts(materialAsset, "explicit glTF MR -> Unity Standard packing; not generated PBR");
        Report["material_mapping"] = new Dictionary<string, object> { ["base_color"] = "source texture_000.png, sRGB", ["metallic"] = "source texture_001 B -> Unity R, linear",
            ["smoothness"] = "1 - source texture_001 G -> Unity A, linear", ["normal"] = "SOURCE_ABSENT_NOT_GENERATED", ["ao"] = "SOURCE_ABSENT_NOT_GENERATED", ["emission"] = "DISABLED_NO_SOURCE_EMISSION_MAP" };
        EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        var root = new GameObject("AFS_Validated_LODs"); var group = root.AddComponent<LODGroup>(); var lods = new LOD[4];
        float[] transitions = {0.6f, 0.3f, 0.12f, 0.03f};
        for (int level = 0; level < 4; level++)
        {
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefabs[level]); instance.name = "LOD" + level; instance.transform.SetParent(root.transform, false);
            var renderers = instance.GetComponentsInChildren<Renderer>(true);
            foreach (var renderer in renderers) renderer.sharedMaterials = Enumerable.Repeat(materialAsset, renderer.sharedMaterials.Length).ToArray();
            lods[level] = new LOD(transitions[level], renderers);
        }
        group.SetLODs(lods); group.RecalculateBounds();
        var bounds = BoundsOf(lods[0].renderers);
        Check(Math.Abs(bounds.size.y - Config.expectedHeight) < 0.02f, "Unity metric scale/axis differs: height " + bounds.size.y);
        Report["bounds_m"] = new Dictionary<string, object> { ["center"] = Vec(bounds.center), ["size"] = Vec(bounds.size), ["expected_height"] = Config.expectedHeight };
        Report["lod_group"] = new Dictionary<string, object> { ["levels"] = group.GetLODs().Length, ["screen_relative_transitions"] = transitions, ["device_performance"] = "NOT_TESTED" };
        var collision = root.AddComponent<BoxCollider>(); collision.center = root.transform.InverseTransformPoint(bounds.center); collision.size = bounds.size;
        Check(Math.Abs(bounds.min.y) < 0.02f, "Bottom pivot is not on the ground plane");
        Report["collision"] = "BoxCollider from actual LOD0 bounds; not a concave mesh collider";
        PrefabUtility.SaveAsPrefabAsset(root, "Assets/AFS/Output/AFS_Validated.prefab");
        var scenePath = "Assets/AFS/Output/AFS_Validation.unity";
        EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene(), scenePath);
        Report["prefab_path"] = "Assets/AFS/Output/AFS_Validated.prefab"; Report["scene_path"] = scenePath;
        if (Config.mode == "render") Render(root, group, bounds);
        else Report["render_status"] = "NOT_REQUESTED_CPU_IMPORT_ONLY";
        AssetDatabase.SaveAssets();
        AssetDatabase.ExportPackage("Assets/AFS", Path.Combine(Config.outputPath,"AFS_Asset.unitypackage"), ExportPackageOptions.Recurse | ExportPackageOptions.IncludeDependencies);
        Report["native_package"] = "AFS_Asset.unitypackage";
        Check(File.Exists(Path.Combine(Config.outputPath,"AFS_Asset.unitypackage")),"Native Unity package was not exported");
    }

    public static void Reopen()
    {
        Config = JsonUtility.FromJson<Request>(File.ReadAllText(Path.Combine(Directory.GetParent(Application.dataPath).FullName,"QARequest.json")));
        try {
            var scene = EditorSceneManager.OpenScene("Assets/AFS/Output/AFS_Validation.unity",OpenSceneMode.Single);
            var root = scene.GetRootGameObjects().FirstOrDefault(g => g.GetComponent<LODGroup>() != null);
            Check(root != null,"Saved scene has no LODGroup root");
            if(root != null) {
                var group = root.GetComponent<LODGroup>(); Check(group.GetLODs().Length == 4,"Reopened scene LOD count");
                var collider = root.GetComponent<BoxCollider>();Check(collider != null,"Reopened scene collider missing");
                var renderers=group.GetLODs()[0].renderers;var bounds=BoundsOf(renderers);
                Check(Math.Abs(bounds.size.y-Config.expectedHeight)<0.02f,"Reopened scene scale changed");
                foreach(var r in renderers)foreach(var material in r.sharedMaterials)Check(material != null && material.mainTexture != null && material.GetTexture("_MetallicGlossMap") != null,"Reopened material references unresolved");
            }
            var prefab=AssetDatabase.LoadAssetAtPath<GameObject>("Assets/AFS/Output/AFS_Validated.prefab");
            Check(prefab != null && prefab.GetComponent<LODGroup>() != null,"Saved native prefab failed to reopen");
        } catch(Exception exception) {Failures.Add(exception.ToString());}
        File.WriteAllText(Path.Combine(Config.outputPath,"unity_reopen_report.json"),Json(new Dictionary<string,object>{["checks_passed"]=Failures.Count==0,["failures"]=Failures,["unity_version"]=Application.unityVersion,["effective_config_hash"]=Config.effectiveConfigHash,["scope"]="Separate Editor process reopened native serialized prefab/scene/material/LOD/collision"}),new UTF8Encoding(false));
        EditorApplication.Exit(Failures.Count==0?0:1);
    }

    private static void ConfigureTexture(string path, bool srgb)
    {
        var importer = AssetImporter.GetAtPath(path) as TextureImporter; Check(importer != null, "Missing texture importer " + path); if (importer == null) return;
        importer.sRGBTexture = srgb; importer.maxTextureSize = 4096; importer.textureCompression = TextureImporterCompression.Uncompressed;
        importer.alphaSource = TextureImporterAlphaSource.FromInput; importer.SaveAndReimport();
    }
    private static object MaterialFacts(Material material, string origin)
    {
        if (material == null) return new Dictionary<string, object> { ["origin"] = origin, ["missing"] = true };
        var textures = new List<object>();
        foreach (string property in material.GetTexturePropertyNames())
        {
            var texture = material.GetTexture(property); if (texture == null) continue;
            var importer = AssetImporter.GetAtPath(AssetDatabase.GetAssetPath(texture)) as TextureImporter;
            textures.Add(new Dictionary<string, object> { ["property"] = property, ["asset_path"] = AssetDatabase.GetAssetPath(texture), ["width"] = texture.width, ["height"] = texture.height,
                ["srgb"] = importer == null ? (object)null : importer.sRGBTexture });
        }
        return new Dictionary<string, object> { ["origin"] = origin, ["name"] = material.name, ["shader"] = material.shader == null ? "MISSING" : material.shader.name, ["textures"] = textures, ["keywords"] = material.shaderKeywords };
    }
    private static Bounds BoundsOf(Renderer[] renderers) { var bounds = renderers[0].bounds; foreach (var r in renderers.Skip(1)) bounds.Encapsulate(r.bounds); return bounds; }
    private static float[] Vec(Vector3 value) { return new[] {value.x, value.y, value.z}; }

    private static void Render(GameObject root, LODGroup group, Bounds bounds)
    {
        Check(SystemInfo.graphicsDeviceType != GraphicsDeviceType.Null, "Rendering unavailable: null GPU device");
        Check(Shader.Find("Standard").isSupported, "Unity Standard shader unsupported");
        QualitySettings.shadows = ShadowQuality.All; QualitySettings.shadowResolution = ShadowResolution.High;
        QualitySettings.antiAliasing = 0; RenderSettings.ambientMode = AmbientMode.Flat; RenderSettings.ambientLight = new Color(0.45f, 0.47f, 0.5f);
        var key = new GameObject("QA_Key").AddComponent<Light>(); key.type = LightType.Directional; key.intensity = 1.2f; key.shadows = LightShadows.Soft; key.transform.rotation = Quaternion.Euler(45, -35, 0);
        var fill = new GameObject("QA_Fill").AddComponent<Light>(); fill.type = LightType.Directional; fill.intensity = 0.55f; fill.transform.rotation = Quaternion.Euler(35, 140, 0);
        var ground = GameObject.CreatePrimitive(PrimitiveType.Plane); ground.name = "Neutral ground"; ground.transform.localScale = new Vector3(3,1,3);
        var groundMaterial = new Material(Shader.Find("Standard")); groundMaterial.color = new Color(0.17f,0.19f,0.21f); ground.GetComponent<Renderer>().sharedMaterial = groundMaterial;
        var marker = GameObject.CreatePrimitive(PrimitiveType.Cube); marker.name = "1.8m scale reference, not character"; marker.transform.position = new Vector3(-4,0.9f,0); marker.transform.localScale = new Vector3(0.4f,1.8f,0.4f);
        var markerMaterial = new Material(Shader.Find("Standard")); markerMaterial.color = new Color(0.55f,0.59f,0.55f); marker.GetComponent<Renderer>().sharedMaterial = markerMaterial;
        var camera = new GameObject("QA_Camera").AddComponent<Camera>(); camera.orthographic = true; camera.orthographicSize = 6.75f; camera.nearClipPlane = 0.1f; camera.farClipPlane = 150;
        camera.clearFlags = CameraClearFlags.SolidColor; camera.backgroundColor = new Color(0.12f,0.14f,0.18f); camera.allowHDR = false; camera.allowMSAA = false;
        var captures = new List<object>();
        Capture(camera, group, bounds, 2, new Vector3(1,1,-1), 1280,720,"unity_gameplay_1280x720.png",captures);
        Capture(camera, group, bounds, 0, new Vector3(1,0.5f,-1),2560,1440,"unity_three_quarter_2560x1440.png",captures);
        Capture(camera, group, bounds, 0, new Vector3(0,0.15f,1),2560,1440,"unity_back_2560x1440.png",captures);
        group.ForceLOD(-1); Report["render_status"] = "ACTUAL_UNITY_CAMERA_RENDER"; Report["renders"] = captures;
        Report["render_limitations"] = "Editor camera render, built-in pipeline; not player build, device FPS, or matched Meshy comparison";
        EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene(), "Assets/AFS/Output/AFS_Validation.unity");
    }
    private static void Capture(Camera camera, LODGroup group, Bounds bounds, int lod, Vector3 direction, int width, int height, string name, List<object> captures)
    {
        group.ForceLOD(lod); camera.transform.position = bounds.center + direction.normalized * 25; camera.transform.LookAt(bounds.center); camera.aspect = (float)width/height;
        var target = new RenderTexture(width,height,24,RenderTextureFormat.ARGB32); target.Create(); camera.targetTexture = target; camera.Render();
        var previous = RenderTexture.active; RenderTexture.active = target;
        var image = new Texture2D(width,height,TextureFormat.RGB24,false); image.ReadPixels(new Rect(0,0,width,height),0,0); image.Apply();
        File.WriteAllBytes(Path.Combine(Config.outputPath,name),image.EncodeToPNG()); RenderTexture.active = previous; camera.targetTexture = null; target.Release();
        captures.Add(new Dictionary<string, object> { ["file"] = name, ["width"] = width, ["height"] = height, ["forced_lod"] = lod, ["triangles"] = Config.expectedTriangles[lod],
            ["camera_position_m"] = Vec(camera.transform.position), ["target_m"] = Vec(bounds.center), ["orthographic_vertical_half_size_m"] = camera.orthographicSize });
        UnityEngine.Object.DestroyImmediate(image); UnityEngine.Object.DestroyImmediate(target);
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
