import {createRoot} from 'react-dom/client';
import {ComponentsSetup} from './components-setup';
/** The first-run wizard is plain DOM; this mounts the same one-click component setup inside it. */
export function mountComponentsSetup(host:HTMLElement){createRoot(host).render(<ComponentsSetup/>);}
