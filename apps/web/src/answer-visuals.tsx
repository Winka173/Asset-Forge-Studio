// Small visual hints for suggested answers: colour swatches and material samples, only when the text names them.
// Whole words in any script: \b only knows ASCII letters, so it would never match "đỏ" or "vàng".
const w=(alternatives:string)=>new RegExp(`(?<!\\p{L})(${alternatives})(?!\\p{L})`,'iu');
const COLOURS:[RegExp,string][]=[
 [w('đỏ sẫm|đỏ đô|crimson|maroon|dark red'),'#8b1e2b'],[w('đỏ|red'),'#d23b32'],[w('cam|orange'),'#e8862b'],
 [w('vàng kim|vàng đồng|gold|golden'),'#d4a73a'],[w('vàng|yellow'),'#e9cf42'],[w('xanh lá|lục|green'),'#3f9a4a'],
 [w('xanh ngọc|lam ngọc|teal|cyan'),'#2fa8a3'],[w('xanh đậm|navy|dark blue'),'#22336b'],[w('xanh dương|xanh lam|lam|blue'),'#3a6fd0'],
 [w('tím|purple|violet'),'#7b4bc4'],[w('hồng|pink'),'#e07aa8'],[w('nâu|brown'),'#7a4e2d'],[w('be|kem|beige|cream'),'#e6d6b4'],
 [w('trắng|white'),'#f2f2ee'],[w('xám|ghi|grey|gray'),'#8a8d92'],[w('đen|black'),'#1c1d20'],[w('bạc|silver'),'#c4c8ce'],
 [w('đồng|bronze|copper'),'#a8693a'],
];
const MATERIALS:[RegExp,string][]=[
 [w('gỗ|wood|wooden|timber'),'wood'],[w('đá|stone|rock'),'stone'],[w('gạch|brick'),'brick'],
 [w('kim loại|thép|sắt|metal|steel|iron'),'metal'],[w('pha lê|kính|crystal|glass'),'crystal'],[w('vải|cloth|fabric'),'cloth'],
 [w('ngói|tile|tiles'),'tile'],[w('rơm|mái tranh|thatch|straw'),'thatch'],
];

export function answerVisuals(text:string){
 const colours:string[]=[];let rest=text;
 for(const [pattern,hex] of COLOURS){if(pattern.test(rest)){colours.push(hex);rest=rest.replace(pattern,' ');}}
 const materials=MATERIALS.filter(([pattern])=>pattern.test(text)).map(([,name])=>name);
 return {colours:colours.slice(0,3),materials:materials.slice(0,2)};
}

export function AnswerVisual({text}:{text:string}){
 const {colours,materials}=answerVisuals(text);
 if(!colours.length&&!materials.length)return null;
 return <span className="answer-visual" aria-hidden="true">{colours.map(c=><i key={c} className="answer-swatch" style={{background:c}}/>)}{materials.map(m=><i key={m} className={`answer-material material-${m}`}/>)}</span>;
}
