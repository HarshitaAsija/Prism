import { useEffect, useRef } from "react";
export default function useDialogFocus(onClose) {
  const ref = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    const element = ref.current;
    if (!element) return;
    const focusable = () =>
      [
        ...element.querySelectorAll(
          'button, a[href], input, textarea, select, [tabindex="0"]',
        ),
      ].filter((el) => !el.disabled);
    (focusable()[0] || element).focus();
    const keyboard = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
      if (e.key !== "Tab") return;
      const nodes = focusable();
      if (!nodes.length) {
        e.preventDefault();
        return;
      }
      if (e.shiftKey && document.activeElement === nodes[0]) {
        e.preventDefault();
        nodes[nodes.length - 1].focus();
      } else if (
        !e.shiftKey &&
        document.activeElement === nodes[nodes.length - 1]
      ) {
        e.preventDefault();
        nodes[0].focus();
      }
    };
    element.addEventListener("keydown", keyboard);
    return () => {
      element.removeEventListener("keydown", keyboard);
      previous?.focus();
    };
  }, [onClose]);
  return ref;
}
