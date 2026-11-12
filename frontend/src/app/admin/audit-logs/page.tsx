'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { adminApi } from '@/lib/api/endpoints';
import { formatDateIN } from '@/lib/format';
import { AuditLogEntry, PaginationMeta } from '@/types/api';

const OUTCOME_BADGE: Record<AuditLogEntry['outcome'], string> = {
  success: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  failure: 'border-rose-200 bg-rose-50 text-rose-800',
  warning: 'border-amber-200 bg-amber-50 text-amber-800'
};

const EVENT_FILTERS = [
  { value: '', label: 'All Events' },
  { value: 'login_success', label: 'Login Success' },
  { value: 'login_failed', label: 'Login Failed' },
  { value: 'login_locked', label: 'Brute-Force Lockout' },
  { value: 'refresh_reuse_detected', label: 'Refresh Reuse Detected' },
  { value: 'logout', label: 'Logout' },
  { value: 'logout_all', label: 'Logout All Devices' },
  { value: 'session_revoked', label: 'Session Revoked' },
  { value: 'password_changed', label: 'Password Changed' },
  { value: 'password_reset_completed', label: 'Password Reset' },
  { value: '2fa_enabled', label: '2FA Enabled' },
  { value: '2fa_disabled', label: '2FA Disabled' },
  { value: 'role_changed', label: 'Role Changed' }
];

export default function AdminAuditLogsPage() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [pagination, setPagination] = useState<PaginationMeta | null>(null);
  const [eventType, setEventType] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminApi.auditLogs({
        page,
        limit: 25,
        eventType: eventType || undefined
      });
      setLogs(res.items);
      setPagination(res.pagination);
    } finally {
      setLoading(false);
    }
  }, [page, eventType]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="font-serif text-xl font-bold text-espresso-900">
            Security Audit Trail
          </h2>
          <p className="text-xs text-espresso-600">
            Immutable security events recorded with IP, User-Agent, and Request ID.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <label
            htmlFor="audit-event-filter"
            className="text-xs font-semibold text-espresso-700"
          >
            Event Filter:
          </label>
          <select
            id="audit-event-filter"
            value={eventType}
            onChange={(e) => {
              setEventType(e.target.value);
              setPage(1);
            }}
            className="h-10 rounded-xl border border-espresso-200 bg-white px-3 text-xs font-medium text-espresso-900"
          >
            {EVENT_FILTERS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="h-72 animate-pulse rounded-2xl border border-espresso-200 bg-white" />
      ) : logs.length === 0 ? (
        <div className="rounded-2xl border border-espresso-200 bg-white p-8 text-center text-sm text-espresso-600">
          No audit events recorded for this filter yet.
        </div>
      ) : (
        <div
          tabIndex={0}
          role="region"
          aria-labelledby="audit-table-caption"
          className="table-scroll-region max-h-[560px] rounded-2xl border border-espresso-200 bg-white"
        >
          <table className="text-left text-xs">
            <caption id="audit-table-caption" className="sr-only">
              Security audit log entries
            </caption>
            <thead className="bg-espresso-50 text-[11px] uppercase tracking-wider text-espresso-600">
              <tr>
                <th scope="col" className="px-4 py-3 font-semibold">
                  Time
                </th>
                <th scope="col" className="px-4 py-3 font-semibold">
                  Event
                </th>
                <th scope="col" className="px-4 py-3 font-semibold">
                  Outcome
                </th>
                <th scope="col" className="px-4 py-3 font-semibold">
                  User ID
                </th>
                <th scope="col" className="px-4 py-3 font-semibold">
                  IP / Request ID
                </th>
                <th scope="col" className="px-4 py-3 font-semibold">
                  Metadata
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-espresso-100">
              {logs.map((entry) => (
                <tr key={entry.id} className="hover:bg-espresso-50/60">
                  <td className="whitespace-nowrap px-4 py-3 text-espresso-700">
                    {formatDateIN(entry.createdAt)}
                  </td>
                  <th
                    scope="row"
                    className="whitespace-nowrap px-4 py-3 font-mono font-semibold text-espresso-900"
                  >
                    {entry.eventType}
                  </th>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span
                      className={`inline-block rounded-full border px-2 py-0.5 text-[11px] font-semibold capitalize ${OUTCOME_BADGE[entry.outcome]}`}
                    >
                      {entry.outcome}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-[11px] text-espresso-700">
                    {entry.userId ? `${entry.userId.slice(0, 8)}…` : '—'}
                  </td>
                  <td className="px-4 py-3 font-mono text-[11px] text-espresso-600">
                    <div>{entry.ip}</div>
                    <div className="text-espresso-400">
                      req:{entry.requestId.slice(0, 8)}
                    </div>
                  </td>
                  <td className="max-w-xs truncate px-4 py-3 font-mono text-[11px] text-espresso-600">
                    {Object.keys(entry.metadata).length > 0
                      ? JSON.stringify(entry.metadata)
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pagination && pagination.totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-espresso-600">
          <span>
            Page {pagination.page} of {pagination.totalPages} ({pagination.totalItems} events)
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={!pagination.hasPrev}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded-xl border border-espresso-200 bg-white px-3 py-1.5 font-semibold disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={!pagination.hasNext}
              onClick={() => setPage((p) => p + 1)}
              className="rounded-xl border border-espresso-200 bg-white px-3 py-1.5 font-semibold disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
