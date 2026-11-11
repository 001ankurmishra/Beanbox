'use client';

import React, { useEffect, useId, useRef } from 'react';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'primary';
  isBusy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  isBusy = false,
  onConfirm,
  onCancel
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  // Fallback click-outside light dismiss where `closedby` is unsupported (e.g. Safari)
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog || 'closedBy' in HTMLDialogElement.prototype) return;

    let pressedOutside = false;
    const isOutside = (e: PointerEvent) => {
      const r = dialog.getBoundingClientRect();
      return (
        e.clientX < r.left ||
        e.clientX > r.right ||
        e.clientY < r.top ||
        e.clientY > r.bottom
      );
    };
    const onDown = (e: PointerEvent) => {
      pressedOutside = isOutside(e);
    };
    const onUp = (e: PointerEvent) => {
      if (pressedOutside && isOutside(e) && !isBusy) {
        onCancel();
      }
    };
    dialog.addEventListener('pointerdown', onDown);
    dialog.addEventListener('pointerup', onUp);
    return () => {
      dialog.removeEventListener('pointerdown', onDown);
      dialog.removeEventListener('pointerup', onUp);
    };
  }, [isBusy, onCancel]);

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      aria-describedby={descId}
      {...({ closedby: isBusy ? 'none' : 'any' } as Record<string, string>)}
      onCancel={(e) => {
        if (isBusy) {
          e.preventDefault();
          return;
        }
        onCancel();
      }}
      onClose={() => {
        if (open) onCancel();
      }}
      className="m-auto w-[min(92vw,28rem)] rounded-2xl border border-espresso-200 bg-espresso-50 p-6 text-espresso-900 shadow-2xl"
    >
      <h2 id={titleId} className="font-serif text-xl font-semibold text-espresso-900">
        {title}
      </h2>
      <p id={descId} className="mt-2 text-sm text-espresso-700 leading-relaxed">
        {description}
      </p>
      <div className="mt-6 flex items-center justify-end gap-3">
        <button
          type="button"
          autoFocus
          disabled={isBusy}
          onClick={onCancel}
          className="min-h-[44px] rounded-xl border border-espresso-300 bg-white px-4 py-2 text-sm font-medium text-espresso-800 hover:bg-espresso-100 disabled:opacity-50"
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          disabled={isBusy}
          onClick={onConfirm}
          className={`min-h-[44px] rounded-xl px-4 py-2 text-sm font-semibold text-white transition disabled:opacity-50 ${
            variant === 'danger'
              ? 'bg-rose-700 hover:bg-rose-800'
              : 'bg-espresso-900 hover:bg-espresso-800'
          }`}
        >
          {isBusy ? 'Processing…' : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
