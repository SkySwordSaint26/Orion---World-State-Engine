import { useEffect, useId, useRef, type ReactNode } from 'react';

export function Dialog({ title, onClose, children, className = '' }: {
  title: string; onClose: () => void; children: ReactNode; className?: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    return () => element.close();
  }, []);
  return (
    <dialog ref={dialog} aria-labelledby={titleId} className={`studio-dialog ${className}`}
      onCancel={event => { event.preventDefault(); onClose(); }}
      onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="flex max-h-[85dvh] flex-col overflow-hidden rounded-xl border border-outline-variant/40 bg-surface-container-low shadow-2xl">
        <header className="flex items-center justify-between gap-4 border-b border-outline-variant/30 px-6 py-5">
          <h2 id={titleId} className="font-headline-md text-2xl text-on-surface">{title}</h2>
          <button type="button" aria-label={`Close ${title}`} onClick={onClose} className="p-1 text-on-surface-variant hover:text-primary"><span className="material-symbols-outlined">close</span></button>
        </header>
        <div className="overflow-y-auto p-6">{children}</div>
      </section>
    </dialog>
  );
}
