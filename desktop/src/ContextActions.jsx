import { useEffect, useRef } from "react";

// Transient actions only. Dismiss on outside click, scroll or Escape.
export function ContextActions({ menu, actions, onClose }) {
  const root = useRef(null);
  useEffect(() => {
    if (!menu) return;
    const close = event => {
      if (event.type === "keydown" && event.key !== "Escape") return;
      if (event.type === "pointerdown" && root.current?.contains(event.target)) return;
      if (event.type === "keydown") event.preventDefault();
      onClose();
    };
    root.current?.querySelector("button:not(:disabled)")?.focus();
    window.addEventListener("pointerdown", close);
    window.addEventListener("keydown", close);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("pointerdown", close);
      window.removeEventListener("keydown", close);
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", close, true);
    };
  }, [menu, onClose]);
  if (!menu) return null;
  return <div ref={root} className="context-actions" role="menu" aria-label={menu.label}
    style={{ left: Math.max(4, Math.min(menu.x, window.innerWidth - 260)),
      top: Math.max(4, Math.min(menu.y, window.innerHeight - 48 - actions.length * 38)) }}
    onContextMenu={event => event.preventDefault()}
    onKeyDown={event => {
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const buttons = [...root.current.querySelectorAll("button:not(:disabled)")];
      if (!buttons.length) return;
      const index = buttons.indexOf(document.activeElement);
      buttons[event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 :
        (index + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length]?.focus();
    }}>
    <strong>{menu.label}</strong>
    {actions.map(action => <button key={action.label} type="button" role="menuitem" disabled={action.disabled}
      onClick={() => { onClose(); action.run(); }}>{action.label}</button>)}
  </div>;
}
