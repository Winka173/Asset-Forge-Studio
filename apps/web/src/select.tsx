import {selectHelp} from "./select-help";
import { Children, isValidElement, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode, type SelectHTMLAttributes } from "react";
import { createPortal } from "react-dom";

type Choice = { value: string; label: ReactNode; text: string; disabled: boolean; group?: string;description?:string };
function textOf(node: ReactNode): string {
  return Children.toArray(node).map(child => isValidElement<{ children?: ReactNode }>(child) ? textOf(child.props.children) : String(child)).join("");
}
function choicesOf(children: ReactNode, group?: string, disabled = false): Choice[] {
  return Children.toArray(children).flatMap(child => {
    if (!isValidElement<{ children?: ReactNode; value?: string | number; disabled?: boolean; label?: string; "data-description"?:string }>(child)) return [];
    if (child.type === "option") return [{ value: String(child.props.value ?? textOf(child.props.children)), label: child.props.children, text: textOf(child.props.children), disabled: disabled || !!child.props.disabled, group,description:child.props["data-description"] }];
    return choicesOf(child.props.children, child.type === "optgroup" ? child.props.label : group, disabled || !!child.props.disabled);
  });
}

/** Custom, keyboard-operable single select. The hidden native control retains form and automation semantics. */
export function Select({ children, className = "", ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  const generatedId = useId();
  const listId = `${generatedId}-list`;
  const trigger = useRef<HTMLButtonElement>(null);
  const native = useRef<HTMLSelectElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const [helpOpen,setHelpOpen]=useState(false);
  const [query,setQuery]=useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [uncontrolled, setUncontrolled] = useState(String(props.defaultValue ?? ""));
  const [inferredLabel, setInferredLabel] = useState<string>();
  const [position, setPosition] = useState({ top: 0, left: 0, width: 0, maxHeight: 300 });
  const search = useRef({ value: "", time: 0 });
  const choices = choicesOf(children);
  const choicesSignature = JSON.stringify(choices.map(choice => [choice.value, choice.text, choice.disabled, choice.group]));
  const value = props.value === undefined ? uncontrolled : String(props.value);
  const selected = choices.find(c => c.value === value) ?? choices[0];
  const visible=choices.map((choice,index)=>({choice,index})).filter(({choice})=>!query||choice.text.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  const enabled = visible.map(({choice:c,index:i}) => c.disabled ? -1 : i).filter(i => i >= 0);
  const show = () => {
    if (props.disabled || !choices.some(c=>!c.disabled)) return;
    setHelpOpen(false);setQuery('');
    setActive(Math.max(0, choices.findIndex(c => c.value === selected?.value)));
    setOpen(true);
  };
  const choose = (index: number) => {
    const choice = choices[index];
    if (!choice || choice.disabled || !native.current) return;
    const select = native.current;
    select.value = choice.value;
    // Dispatch a real native change: existing React handlers keep their event/value semantics.
    select.dispatchEvent(new Event("change", { bubbles: true }));
    setUncontrolled(choice.value);
    setOpen(false);
    trigger.current?.focus();
  };
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      if (!trigger.current || !menu.current) return;
      const rect = trigger.current.getBoundingClientRect();
      const viewport = window.visualViewport;
      const viewportTop = viewport?.offsetTop || 0;
      const viewportLeft = viewport?.offsetLeft || 0;
      const viewportHeight = viewport?.height || window.innerHeight;
      const viewportWidth = viewport?.width || window.innerWidth;
      const edge = 10, gap = 7;
      const minTop = viewportTop + edge;
      const maxBottom = viewportTop + viewportHeight - edge;
      const availableBelow = Math.max(0, maxBottom - rect.bottom - gap);
      const availableAbove = Math.max(0, rect.top - gap - minTop);
      const above = availableBelow < Math.min(180, menu.current.scrollHeight) && availableAbove > availableBelow;
      const maxHeight = Math.max(1, Math.min(320, viewportHeight - edge * 2, above ? availableAbove : availableBelow));
      const width = Math.max(1, Math.min(viewportWidth - edge * 2, Math.max(rect.width, 230)));
      // Measure at the final width: wrapped labels may change the popup height.
      menu.current.style.width = `${width}px`;
      const height = Math.min(maxHeight, menu.current.scrollHeight + 2);
      const desiredTop = above ? rect.top - gap - height : rect.bottom + gap;
      const top = Math.max(minTop, Math.min(desiredTop, maxBottom - height));
      const left = Math.max(viewportLeft + edge, Math.min(rect.left, viewportLeft + viewportWidth - width - edge));
      setPosition(previous => previous.top === top && previous.left === left && previous.width === width && previous.maxHeight === maxHeight ? previous : { top, left, width, maxHeight });
    };
    place();
    // Options can arrive after the popup opens (API refresh, font or label layout).
    // Re-anchor to the new height instead of leaving a short popup's old top edge.
    const resize = new ResizeObserver(place);
    if (menu.current) resize.observe(menu.current);
    const onScroll = (event: Event) => {
      // Scrolling options must not reposition the popup or scroll its trigger.
      if (menu.current?.contains(event.target as Node)) return;
      place();
    };
    window.addEventListener("resize", place);
    window.addEventListener("scroll", onScroll, true);
    window.visualViewport?.addEventListener("resize", place);
    window.visualViewport?.addEventListener("scroll", place);
    const outside = (event: PointerEvent) => {
      if (!trigger.current?.contains(event.target as Node) && !menu.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => { resize.disconnect(); window.removeEventListener("resize", place); window.removeEventListener("scroll", onScroll, true); window.visualViewport?.removeEventListener("resize", place); window.visualViewport?.removeEventListener("scroll", place); document.removeEventListener("pointerdown", outside); };
  }, [open, choicesSignature]);
  useEffect(() => {
    if (!open || !menu.current) return;
    const container = menu.current;
    const option = container.querySelector<HTMLElement>(`[data-index="${active}"]`);
    if (!option) return;
    // scrollIntoView also scrolls the page behind a fixed portal, moving the trigger
    // off-screen and causing a placement/scroll feedback loop on long forms.
    const bounds = container.getBoundingClientRect();
    const item = option.getBoundingClientRect();
    if (item.top < bounds.top + 6) container.scrollTop -= bounds.top + 6 - item.top;
    else if (item.bottom > bounds.bottom - 6) container.scrollTop += item.bottom - bounds.bottom + 6;
  }, [active, open]);
  useEffect(() => { setOpen(false); }, [props.disabled]);
  useLayoutEffect(() => {
    const associated = Array.from(native.current?.labels || []);
    const text = associated.map(label => {
      const copy = label.cloneNode(true) as HTMLElement;
      copy.querySelectorAll("select,.afs-select,small,input,textarea").forEach(child => child.remove());
      return copy.textContent?.trim();
    }).filter(Boolean).join(" ");
    setInferredLabel(text || undefined);
  }, [children]);
  const label = props["aria-label"] || inferredLabel;
  const explanation=selectHelp(label||'',value,selected?.text||'');
  useEffect(()=>{if(!helpOpen)return;const dismiss=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();setHelpOpen(false);}};document.addEventListener('keydown',dismiss,true);return()=>document.removeEventListener('keydown',dismiss,true);},[helpOpen]);
  return <span className={`afs-select has-help ${className}${open ? " is-open" : ""}${props.disabled ? " is-disabled" : ""}`}>
    <select {...props} className="afs-select-native" ref={native} tabIndex={-1} aria-hidden="true" onFocus={() => trigger.current?.focus()} onChange={event => { setUncontrolled(event.target.value); props.onChange?.(event); }}>{children}</select>
    <button ref={trigger} type="button" id={props.id ? `${props.id}-trigger` : undefined} role="combobox" aria-label={label} aria-labelledby={props["aria-labelledby"]} aria-expanded={open} aria-controls={open ? listId : undefined} aria-haspopup="listbox" aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined} aria-describedby={props["aria-describedby"]} aria-invalid={props["aria-invalid"]} aria-required={props.required} disabled={props.disabled} title={props.title} className="afs-select-trigger" onClick={() => open ? setOpen(false) : show()} onKeyDown={event => {
      if (["ArrowDown", "ArrowUp", "Home", "End", "Enter", " ", "Escape"].includes(event.key)) {
        event.preventDefault();
        if (event.key === "Escape") { if (open) event.stopPropagation(); setOpen(false); return; }
        if (event.key === "Enter" || event.key === " ") { open ? choose(active) : show(); return; }
        if (!open) { show(); return; }
        if (event.key === "Home") setActive(enabled[0]);
        else if (event.key === "End") setActive(enabled[enabled.length - 1]);
        else setActive(enabled[(Math.max(0, enabled.indexOf(active)) + (event.key === "ArrowDown" ? 1 : enabled.length - 1)) % enabled.length]);
      } else if (event.key === "Tab") setOpen(false);
      else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
        const now = Date.now();
        search.current = { value: (now - search.current.time > 700 ? "" : search.current.value) + event.key.toLocaleLowerCase(), time: now };
        const found = choices.findIndex(c => !c.disabled && c.text.toLocaleLowerCase().startsWith(search.current.value));
        if (found >= 0) { if (!open) show(); setActive(found); }
      }
    }}><span className="afs-select-value">{selected?.label || "Select an option"}</span><svg aria-hidden="true" width="14" height="14" viewBox="0 0 20 20" fill="none"><path d="m5 8 5 5 5-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg></button><button type="button" className="afs-select-help-button" aria-label={`Explain ${label||'options'}`} aria-expanded={helpOpen} aria-controls={helpOpen?generatedId+'-help':undefined} onClick={event=>{event.preventDefault();setHelpOpen(v=>!v);}} title="What does this setting do?">i</button>
    {helpOpen&&<span id={generatedId+'-help'} role="note" className="afs-select-help"><strong>{label||'Choose an option'}</strong><span>{explanation.purpose}</span>{(selected?.description||explanation.option)&&<span><b>{selected?.text}: </b>{selected?.description||explanation.option}</span>}<small>Arrow keys to browse; Enter to select; Esc to close.</small></span>}
    {open && createPortal(<div ref={menu} className="afs-select-menu" style={position}>
      {choices.length>=10&&<input className="afs-select-search" aria-label={`Search ${label||'options'}`} placeholder="Type to filter..." value={query} onChange={e=>{setQuery(e.target.value);setActive(choices.findIndex(c=>!c.disabled&&c.text.toLocaleLowerCase().includes(e.target.value.toLocaleLowerCase())));}} onKeyDown={e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();setOpen(false);trigger.current?.focus();}else if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();trigger.current?.focus();}else if(e.key==='Enter'){e.preventDefault();choose(active);}}}/>}
      <div id={listId} role="listbox" aria-label={label}>{!visible.length&&<p className="afs-select-empty" role="status">No matching options</p>}
      {visible.map(({choice,index:i}) => <div key={`${choice.value}-${i}`}>
        {choice.group && choice.group !== choices[i - 1]?.group && <div className="afs-select-group">{choice.group}</div>}
        <div id={`${listId}-${i}`} role="option" aria-selected={choice.value === selected?.value} aria-disabled={choice.disabled || undefined} data-index={i} className={`afs-select-option${active === i ? " is-active" : ""}`} onMouseMove={() => !choice.disabled && setActive(i)} onPointerDown={event => event.preventDefault()} onClick={() => choose(i)}><span>{choice.label}{(choice.description||selectHelp(label||'',choice.value,choice.text).option)&&<small className="afs-select-option-description">{choice.description||selectHelp(label||'',choice.value,choice.text).option}</small>}</span>{choice.value === selected?.value && <span className="afs-select-check" aria-hidden="true">✓</span>}</div>
      </div>)}</div>
    </div>, document.fullscreenElement || document.body)}
  </span>;
}
