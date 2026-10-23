// Editable deterministic runtime effect. Procedural weapon motion is a preview, not character animation.
using System;
using System.Collections.Generic;
using UnityEngine;

[ExecuteAlways]
public class AFSSlashEffect : MonoBehaviour {
    public string element="fire";
    public float duration=2.4f, radius=1.8f, trailLifetime=.18f, intensity=1.8f;
    public int segments=48, particleCount=12, seed=42;
    public bool playing=true;
    public Material effectMaterial,solidMaterial;
    public float previewTime;
    Mesh trail;MeshFilter filter;Transform weapon;readonly List<Transform> particles=new List<Transform>();
    // Optional project accent: the trail keeps the element colour (measured: blending fire with cyan washed it to pale peach);
    // only the secondary sparks use the accent material.
    public Color accent=Color.clear;public float accentStrength;public Material accentMaterial;
    public Color Tint(){return ElementTint();}
    Color ElementTint(){switch(element){case "ice":return new Color(.23f,.77f,1);case "lightning":return new Color(.52f,.38f,1);case "wind":return new Color(.55f,.95f,.8f);case "earth":return new Color(.82f,.5f,.2f);case "poison":return new Color(.45f,.95f,.15f);default:return new Color(1,.29f,.035f);}}
    void OnEnable(){Ensure();Seek(previewTime);}
    void Update(){if(Application.isPlaying&&playing){previewTime=Mathf.Repeat(previewTime+Time.deltaTime,duration);Seek(previewTime);}}
    void OnDestroy(){if(trail){if(Application.isPlaying)Destroy(trail);else DestroyImmediate(trail);}}
    void Ensure(){
        particles.RemoveAll(p=>!p);
        if(!filter){var child=transform.Find("AFS_RuntimeTrail");if(!child)child=new GameObject("AFS_RuntimeTrail",typeof(MeshFilter),typeof(MeshRenderer)).transform;child.SetParent(transform,false);filter=child.GetComponent<MeshFilter>();}
        if(!trail){trail=new Mesh{name="AFS_DynamicSweptBladeTrail"};trail.MarkDynamic();filter.sharedMesh=trail;}
        filter.sharedMesh=trail;
        filter.GetComponent<MeshRenderer>().sharedMaterial=effectMaterial;
        if(!weapon){weapon=transform.Find("AFS_PreviewSword");if(!weapon){weapon=new GameObject("AFS_PreviewSword").transform;weapon.SetParent(transform,false);var blade=GameObject.CreatePrimitive(PrimitiveType.Cube);blade.name="Blade";blade.transform.SetParent(weapon,false);blade.transform.localPosition=new Vector3(0,.65f,0);blade.transform.localScale=new Vector3(.075f,1.3f,.035f);blade.GetComponent<Renderer>().sharedMaterial=solidMaterial;var guard=GameObject.CreatePrimitive(PrimitiveType.Cube);guard.name="Guard";guard.transform.SetParent(weapon,false);guard.transform.localScale=new Vector3(.42f,.06f,.08f);guard.GetComponent<Renderer>().sharedMaterial=solidMaterial;}}
        if(particles.Count==0){for(int i=0;i<Mathf.Clamp(particleCount,0,24);i++){Transform p=transform.Find("AFS_Accent_"+i);if(!p){var go=GameObject.CreatePrimitive(element=="ice"||element=="earth"?PrimitiveType.Cube:PrimitiveType.Sphere);go.name="AFS_Accent_"+i;p=go.transform;p.SetParent(transform,false);var collider=go.GetComponent<Collider>();if(collider){if(Application.isPlaying)Destroy(collider);else DestroyImmediate(collider);}}p.GetComponent<Renderer>().sharedMaterial=element=="earth"?solidMaterial:accentMaterial&&accentStrength>0?accentMaterial:effectMaterial;particles.Add(p);}}
    }
    void Pose(float seconds,out Vector3 root,out Quaternion rotation){
        float phase=Mathf.Repeat(seconds,duration)/duration*3;int attack=Mathf.FloorToInt(phase);float u=phase-attack;float move=Mathf.SmoothStep(0,1,Mathf.InverseLerp(.08f,.62f,u));
        float yaw=Mathf.Lerp(-105,105,attack==1?1-move:move);float tilt=attack==0?-18:attack==1?25:68;
        rotation=Quaternion.Euler(0,yaw,tilt)*Quaternion.Euler(0,0,-90);root=new Vector3(0,1.25f,0)+rotation*Vector3.up*(radius-1.3f);
    }
    public void Seek(float seconds){
        Ensure();previewTime=seconds;Vector3 root;Quaternion rot;Pose(seconds,out root,out rot);weapon.localPosition=root;weapon.localRotation=rot;
        int count=Mathf.Clamp(segments,12,128);var vertices=new List<Vector3>();var uv=new List<Vector2>();var colors=new List<Color>();var triangles=new List<int>();Color tint=Tint()*Mathf.Clamp(intensity,.1f,4);float swingTime=duration/3;float phase=Mathf.Repeat(seconds,swingTime)/swingTime;
        for(int i=0;i<=count;i++){
            float age=(1-i/(float)count)*trailLifetime;float t=seconds-age;Vector3 origin;Quaternion r;Pose(t,out origin,out r);float samplePhase=Mathf.Repeat(t,swingTime)/swingTime;float alpha=t<0||samplePhase<.08f||samplePhase>.72f||Mathf.Floor(t/swingTime)!=Mathf.Floor(seconds/swingTime)?0:Mathf.Pow(i/(float)count,.65f);
            Vector3 inner=origin+r*Vector3.up*.12f,outer=origin+r*Vector3.up*1.3f;
            if(element=="lightning"){float zig=Mathf.Sin(i*2.27f+seed)*.045f;inner+=r*Vector3.right*zig;outer-=r*Vector3.right*zig;}
            vertices.Add(inner);vertices.Add(outer);uv.Add(new Vector2(i/(float)count,0));uv.Add(new Vector2(i/(float)count,1));var c=tint;c.a=alpha*(element=="wind"?.4f:.78f);colors.Add(c);colors.Add(c);
            if(i<count){int k=i*2;triangles.AddRange(new[]{k,k+1,k+2,k+1,k+3,k+2});}
        }
        trail.Clear();trail.SetVertices(vertices);trail.SetUVs(0,uv);trail.SetColors(colors);trail.SetTriangles(triangles,0);trail.RecalculateBounds();
        for(int i=0;i<particles.Count;i++){
            float offset=i/(float)Mathf.Max(1,particles.Count),age=Mathf.Repeat(phase+offset,1);float emitTime=seconds-age*.32f;Vector3 o;Quaternion r;Pose(emitTime,out o,out r);Vector3 tip=o+r*Vector3.up*(.8f+offset*.5f);float jitter=Mathf.Sin(i*13.3f+seed);
            Vector3 drift=new Vector3(jitter*.4f,age*.9f,Mathf.Cos(i*7.7f)*.3f)*age;
            if(element=="ice")drift=new Vector3(jitter*.2f,-age*age*.8f,offset*.2f);
            if(element=="earth")drift=new Vector3(jitter*.5f,-age*age*2,.2f*age);
            if(element=="wind")drift=new Vector3(Mathf.Sin(age*7+i),age*.5f,Mathf.Cos(age*7+i))*.22f;
            if(element=="poison")drift=new Vector3(jitter*.2f,Mathf.Sin(age*Mathf.PI)*.3f,offset*.2f);
            if(element=="lightning")drift=new Vector3(jitter*.2f,Mathf.Sin(age*37+i)*.1f,0);
            var p=particles[i];p.localPosition=tip+drift;p.localRotation=Quaternion.Euler(i*32+age*120,i*14,45);float size=(1-age)*(element=="earth"?.12f:element=="ice"?.07f:.035f);p.localScale=element=="ice"?new Vector3(size*.5f,size*2.5f,size*.5f):Vector3.one*size;p.gameObject.SetActive(phase>.08f&&phase<.85f);
        }
    }
    public int TrailVertices(){return trail?trail.vertexCount:0;}
}
