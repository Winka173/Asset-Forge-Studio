using UnityEngine;
using UnityEngine.AI;
[ExecuteAlways]
public class AFSWorldNavigation : MonoBehaviour {
    public NavMeshData data;
    private NavMeshDataInstance instance;
    void OnEnable(){if(data!=null)instance=NavMesh.AddNavMeshData(data);}
    void OnDisable(){if(instance.valid)instance.Remove();}
}
