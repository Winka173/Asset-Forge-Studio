// Asset Forge Studio: turns an exported flipbook (<name>.png + <name>.afsflipbook.json) into a ready Particle System prefab.
// Put this file in any Editor folder, then drop the PNG and its .afsflipbook.json into Assets/. A material and
// <name>_FX.prefab are created next to them. Built-in render pipeline, unlit particle shader. Not yet tested in Unity by AFS.
#if UNITY_EDITOR
using System.IO;
using UnityEditor;
using UnityEngine;

public class AFSFlipbookImporter : AssetPostprocessor
{
    [System.Serializable] class Sheet { public int columns = 1; public int rows = 1; public int frames = 1; public float fps = 12; public bool loop; public float size_m = 1; }

    static void OnPostprocessAllAssets(string[] imported, string[] deleted, string[] moved, string[] movedFrom)
    {
        foreach (var path in imported)
        {
            if (!path.EndsWith(".afsflipbook.json")) continue;
            var png = path.Replace(".afsflipbook.json", ".png");
            if (!File.Exists(png)) png = Path.Combine(Path.GetDirectoryName(path), "flipbook.png").Replace('\\', '/');
            var texture = AssetDatabase.LoadAssetAtPath<Texture2D>(png);
            if (texture == null) { Debug.LogWarning("AFS flipbook: no PNG next to " + path); continue; }
            Build(path, png, texture, JsonUtility.FromJson<Sheet>(File.ReadAllText(path)));
        }
    }

    static void Build(string jsonPath, string pngPath, Texture2D texture, Sheet sheet)
    {
        var importer = (TextureImporter)AssetImporter.GetAtPath(pngPath);
        if (importer != null && (!importer.alphaIsTransparency || importer.mipmapEnabled)) { importer.alphaIsTransparency = true; importer.mipmapEnabled = false; importer.SaveAndReimport(); }
        var stem = Path.Combine(Path.GetDirectoryName(jsonPath), Path.GetFileName(jsonPath).Replace(".afsflipbook.json", "")).Replace('\\', '/');
        var shader = Shader.Find("Particles/Standard Unlit") ?? Shader.Find("Legacy Shaders/Particles/Alpha Blended");
        var material = new Material(shader) { mainTexture = texture };
        if (material.HasProperty("_Mode")) material.SetFloat("_Mode", 2);  // fade (alpha blended)
        AssetDatabase.CreateAsset(material, stem + "_FX.mat");

        var go = new GameObject(Path.GetFileName(stem) + "_FX");
        var ps = go.AddComponent<ParticleSystem>();
        var main = ps.main;
        float life = Mathf.Max(0.1f, sheet.frames / Mathf.Max(1f, sheet.fps));
        main.duration = life; main.loop = sheet.loop; main.startLifetime = life; main.startSpeed = 0; main.startSize = Mathf.Max(0.1f, sheet.size_m);
        main.maxParticles = sheet.loop ? 1 : 4; main.simulationSpace = ParticleSystemSimulationSpace.World;
        var emission = ps.emission; emission.rateOverTime = 0; emission.SetBursts(new[] { new ParticleSystem.Burst(0f, 1) });
        var shape = ps.shape; shape.enabled = false;
        var anim = ps.textureSheetAnimation; anim.enabled = true; anim.numTilesX = sheet.columns; anim.numTilesY = sheet.rows;
        anim.animation = ParticleSystemAnimationType.WholeSheet; anim.cycleCount = 1;
        anim.frameOverTime = new ParticleSystem.MinMaxCurve(1f, AnimationCurve.Linear(0, 0, 1, (sheet.frames - 0.01f) / (sheet.columns * sheet.rows)));
        var renderer = go.GetComponent<ParticleSystemRenderer>(); renderer.sharedMaterial = material; renderer.renderMode = ParticleSystemRenderMode.Billboard;
        PrefabUtility.SaveAsPrefabAsset(go, stem + "_FX.prefab");
        Object.DestroyImmediate(go);
        Debug.Log("AFS flipbook prefab created: " + stem + "_FX.prefab");
    }
}
#endif
