import { Children, isValidElement, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode, type SelectHTMLAttributes } from "react";
import { createPortal } from "react-dom";

type Choice = { value: string; label: ReactNode; text: string; disabled: boolean; group?: string };
function textOf(node: ReactNode): string {
  return Children.toArray(node).map(child => isValidElement<{ children?: ReactNode }>(child) ? textOf(child.props.children) : String(child)).join("");
}
function choicesOf(children: ReactNode, group?: string, disabled = false): Choice[] {
  return Children.toArray(children).flatMap(child => {
    if (!isValidElement<{ children?: ReactNode; value?: string | number; disabled?: boolean; label?: string }>(child)) return [];
    if (child.type === "option") return [{ value: String(child.props.value ?? textOf(child.props.children)), label: child.props.children, text: textOf(child.props.children), disabled: disabled || !!child.props.disabled, group }];
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
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [uncontrolled, setUncontrolled] = useState(String(props.defaultValue ?? ""));
  const [inferredLabel, setInferredLabel] = useState<string>();
  const [position, setPosition] = useState({ top: 0, left: 0, width: 0, maxHeight: 300 });
  const search = useRef({ value: "", time: 0 });
  const choices = choicesOf(children);
  const value = props.value === undefined ? uncontrolled : String(props.value);
  const selected = choices.find(c => c.value === value) ?? choices[0];
  const enabled = choices.map((c, i) => c.disabled ? -1 : i).filter(i => i >= 0);
  const show = () => {
    if (props.disabled || !enabled.length) return;
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
      const rect = trigger.current!.getBoundingClientRect();
      const availableBelow = window.innerHeight - rect.bottom - 14;
      const above = availableBelow < 180 && rect.top > availableBelow;
      const maxHeight = Math.min(320, Math.max(100, above ? rect.top - 16 : availableBelow));
      const width = Math.min(window.innerWidth - 24, Math.max(rect.width, 230));
      setPosition({ top: above ? Math.max(8, rect.top - Math.min(maxHeight, menu.current?.scrollHeight || 320) - 7) : rect.bottom + 7, left: Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)), width, maxHeight });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    const outside = (event: PointerEvent) => {
      if (!trigger.current?.contains(event.target as Node) && !menu.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => { window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); document.removeEventListener("pointerdown", outside); };
  }, [open]);
  useEffect(() => { if (open) menu.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" }); }, [active, open]);
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
  return <span className={`afs-select ${className}${open ? " is-open" : ""}${props.disabled ? " is-disabled" : ""}`}>
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
    }}><span className="afs-select-value">{selected?.label || "Select an option"}</span><svg aria-hidden="true" width="14" height="14" viewBox="0 0 20 20" fill="none"><path d="m5 8 5 5 5-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg></button>
    {open && createPortal(<div ref={menu} id={listId} role="listbox" aria-label={label} className="afs-select-menu" style={position}>
      {choices.map((choice, i) => <div key={`${choice.value}-${i}`}>
        {choice.group && choice.group !== choices[i - 1]?.group && <div className="afs-select-group">{choice.group}</div>}
        <div id={`${listId}-${i}`} role="option" aria-selected={choice.value === selected?.value} aria-disabled={choice.disabled || undefined} data-index={i} className={`afs-select-option${active === i ? " is-active" : ""}`} onMouseMove={() => !choice.disabled && setActive(i)} onPointerDown={event => event.preventDefault()} onClick={() => choose(i)}><span>{choice.label}</span>{choice.value === selected?.value && <span className="afs-select-check" aria-hidden="true">✓</span>}</div>
      </div>)}
    </div>, document.body)}
  </span>;
}
