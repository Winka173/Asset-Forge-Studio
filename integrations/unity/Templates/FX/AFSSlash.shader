Shader "AFS/ProceduralSlash" {
 Properties{_Color("Tint",Color)=(1,1,1,1) _Softness("Edge softness",Range(.01,.5))=.16}
 SubShader{Tags{"Queue"="Transparent" "RenderType"="Transparent"} Blend SrcAlpha One Cull Off ZWrite Off
 Pass{CGPROGRAM
 #pragma vertex vert
 #pragma fragment frag
 #include "UnityCG.cginc"
 struct appdata{float4 vertex:POSITION;float2 uv:TEXCOORD0;float4 color:COLOR;};
 struct v2f{float4 position:SV_POSITION;float2 uv:TEXCOORD0;float4 color:COLOR;};
 float4 _Color;float _Softness;
 v2f vert(appdata v){v2f o;o.position=UnityObjectToClipPos(v.vertex);o.uv=v.uv;o.color=v.color*_Color;return o;}
 float4 frag(v2f i):SV_Target{float rim=pow(saturate(i.uv.y),2);float edge=smoothstep(0,_Softness,i.uv.y)*(1-smoothstep(1-_Softness,1,i.uv.y));float grain=.9+.1*sin(i.uv.x*13+i.uv.y*9);float fade=smoothstep(0,.18,i.uv.x);return float4(i.color.rgb*(.5+rim*1.8),i.color.a*edge*grain*fade);}
 ENDCG}
 }
}
