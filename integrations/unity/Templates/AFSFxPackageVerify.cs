using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

public static class AFSFxPackageVerify {
    [Serializable] class Request{public string outputPath,configHash;}
    public static void Run(){var request=JsonUtility.FromJson<Request>(File.ReadAllText(Path.Combine(Directory.GetParent(Application.dataPath).FullName,"FxRequest.json")));bool passed=false;string failure="";GameObject instance=null;try{
        instance=PrefabUtility.LoadPrefabContents("Assets/AFS/FX/AFS_Effect.prefab");var component=instance.GetComponentsInChildren<MonoBehaviour>(true).FirstOrDefault(c=>c&&c.GetType().Name=="AFSSlashEffect");if(!component)throw new Exception("Imported package missing compiled runtime component");component.GetType().GetMethod("Seek").Invoke(component,new object[]{.32f});var mesh=instance.GetComponentsInChildren<MeshFilter>(true).FirstOrDefault(m=>m.name=="AFS_RuntimeTrail");if(!mesh||!mesh.sharedMesh||mesh.sharedMesh.vertexCount<26)throw new Exception("Imported runtime cannot reconstruct trail");if(!instance.GetComponentsInChildren<Renderer>(true).Any(r=>r.sharedMaterial&&r.sharedMaterial.shader&&r.sharedMaterial.shader.name=="AFS/ProceduralSlash"))throw new Exception("Imported shader/material missing");passed=true;
    }catch(Exception e){failure=e.ToString();Debug.LogException(e);}finally{if(instance)PrefabUtility.UnloadPrefabContents(instance);}
        var report="{\"checks_passed\":"+(passed?"true":"false")+",\"unity_version\":\""+Application.unityVersion+"\",\"config_hash\":\""+request.configHash+"\",\"scope\":\"Imported unitypackage into a separate empty project; runtime source, shader, prefab and trail reconstruction\",\"failure\":\""+failure.Replace("\\","\\\\").Replace("\"","\\\"").Replace("\r","\\r").Replace("\n","\\n")+"\"}";File.WriteAllText(Path.Combine(request.outputPath,"fx_package_reopen.json"),report);EditorApplication.Exit(passed?0:1);
    }
}
