'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Cpu,
  Layers,
  RefreshCw,
  RotateCcw
} from 'lucide-react';
import { adminApi } from '@/lib/api/endpoints';
import { AdminJobsResponse, FailedJobRecord } from '@/types/api';

export default function AdminJobsPage() {
  const [data, setData] = useState<AdminJobsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [expandedTraceback, setExpandedTraceback] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setErrorMsg('');
    try {
      const res = await adminApi.jobs();
      setData(res);
    } catch {
      setErrorMsg('Failed to load Celery worker & queue telemetry.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRetry = async (jobId: string) => {
    setRetryingId(jobId);
    setErrorMsg('');
    setSuccessMsg('');
    try {
      await adminApi.retryJob(jobId);
      setSuccessMsg(`Task ${jobId} successfully re-enqueued to its original queue.`);
      await loadData();
    } catch {
      setErrorMsg(`Failed to retry task ${jobId}.`);
    } finally {
      setRetryingId(null);
    }
  };

  const formatDate = (isoString?: string | null) => {
    if (!isoString) return 'Never / Pending';
    try {
      const d = new Date(isoString);
      return d.toLocaleString('en-IN', {
        dateStyle: 'medium',
        timeStyle: 'medium',
        timeZone: 'Asia/Kolkata'
      }) + ' IST';
    } catch {
      return isoString;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-serif text-3xl font-bold text-espresso-900">
            Background Jobs &amp; Dead Letters
          </h1>
          <p className="mt-1 text-sm text-espresso-600">
            Celery worker queue lengths on Redis DB 1, Beat scheduled jobs, distributed lock statuses, and failed job dead letters.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={loadData}
            disabled={loading}
            className="inline-flex min-h-[42px] items-center gap-2 rounded-xl border border-espresso-200 bg-white px-4 text-sm font-semibold text-espresso-900 hover:bg-espresso-50 disabled:opacity-60 transition"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {errorMsg && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800 flex items-center gap-2">
          <AlertCircle className="h-5 w-5 text-rose-600 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {successMsg && (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 flex items-center gap-2">
          <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Broker & Queue Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-3xl border border-espresso-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-espresso-500">
              Celery Broker (DB 1)
            </span>
            <Cpu className="h-5 w-5 text-espresso-400" />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                data?.brokerConnected ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'
              }`}
            />
            <p className="font-serif text-2xl font-bold text-espresso-900">
              {data?.brokerConnected ? 'Active' : 'Unreachable'}
            </p>
          </div>
          <p className="mt-1 text-xs text-espresso-500">
            Dedicated Redis DB 1 isolated from cache (DB 0)
          </p>
        </div>

        {data?.queues.map((q) => (
          <div key={q.name} className="rounded-3xl border border-espresso-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-espresso-500">
                Queue: {q.name}
              </span>
              <Layers className="h-5 w-5 text-espresso-400" />
            </div>
            <p className="mt-2 font-serif text-3xl font-bold text-espresso-900">
              {q.length}
            </p>
            <p className="mt-1 text-xs text-espresso-500">
              {q.name === 'emails'
                ? 'Welcome, reset, order confirmations'
                : q.name === 'maintenance'
                ? 'Order expiry, auth cleanup, stock digest'
                : 'General asynchronous application tasks'}
            </p>
          </div>
        ))}
      </div>

      {/* Scheduled Jobs (Beat) */}
      <div className="rounded-3xl border border-espresso-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="font-serif text-xl font-bold text-espresso-900">
              Scheduled Jobs (Celery Beat)
            </h2>
            <p className="text-xs text-espresso-500">
              Periodic tasks guarded by Redis distributed locks (<code className="text-xs bg-espresso-100 px-1 py-0.5 rounded">SET NX EX</code> with Lua release) to prevent duplicate runs across Beat instances.
            </p>
          </div>
          <Clock className="h-5 w-5 text-espresso-400" />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-espresso-100 text-xs font-semibold uppercase text-espresso-500">
                <th className="pb-3 pr-4">Task Name</th>
                <th className="pb-3 pr-4">Schedule</th>
                <th className="pb-3 pr-4">Queue</th>
                <th className="pb-3 pr-4">Overlap Lock</th>
                <th className="pb-3">Last Run (IST)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-espresso-100">
              {data?.scheduledJobs.map((job) => (
                <tr key={job.name} className="hover:bg-espresso-50/50">
                  <td className="py-3 pr-4 font-mono text-xs font-medium text-espresso-900">
                    {job.name}
                  </td>
                  <td className="py-3 pr-4 text-xs text-espresso-700">
                    <span className="inline-flex rounded-lg bg-espresso-100 px-2.5 py-1 font-semibold text-espresso-800">
                      {job.schedule}
                    </span>
                  </td>
                  <td className="py-3 pr-4 text-xs font-mono text-espresso-600">
                    {job.queue}
                  </td>
                  <td className="py-3 pr-4 text-xs text-emerald-700 font-medium">
                    <span className="inline-flex items-center gap-1">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      Active (TTL Lock)
                    </span>
                  </td>
                  <td className="py-3 text-xs text-espresso-600">
                    {formatDate(job.lastRunAt)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Failed Jobs (Dead Letter Queue) */}
      <div className="rounded-3xl border border-espresso-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="font-serif text-xl font-bold text-espresso-900">
              Failed Jobs (Dead Letters)
            </h2>
            <p className="text-xs text-espresso-500">
              Tasks recorded to <code className="text-xs bg-espresso-100 px-1 py-0.5 rounded">failed_jobs</code> after exhausting all retries. Arguments contain IDs only (PII redacted).
            </p>
          </div>
          <AlertTriangle className="h-5 w-5 text-amber-500" />
        </div>

        {(!data?.failedJobs || data.failedJobs.length === 0) ? (
          <div className="rounded-2xl border border-dashed border-espresso-200 bg-espresso-50/50 p-8 text-center">
            <CheckCircle2 className="mx-auto h-8 w-8 text-emerald-600" />
            <p className="mt-2 text-sm font-semibold text-espresso-900">
              No Failed Jobs
            </p>
            <p className="mt-1 text-xs text-espresso-500">
              All queues are healthy. Tasks that encounter transient network or DB drops are safely retried with exponential backoff.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {data.failedJobs.map((job: FailedJobRecord) => {
              const isResolved = Boolean(job.resolvedAt);
              const isExpanded = expandedTraceback === job.id;

              return (
                <div
                  key={job.id}
                  className={`rounded-2xl border p-4 transition ${
                    isResolved
                      ? 'border-emerald-200 bg-emerald-50/30'
                      : 'border-rose-200 bg-rose-50/30'
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                          isResolved
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-rose-100 text-rose-800'
                        }`}
                      >
                        {isResolved ? 'Resolved / Retried' : 'Failed'}
                      </span>
                      <span className="font-mono text-xs font-bold text-espresso-900">
                        {job.taskName}
                      </span>
                      <span className="text-xs text-espresso-500">
                        (Queue: <span className="font-mono">{job.queue}</span> · Attempts: {job.attempts})
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-xs text-espresso-500">
                        {formatDate(job.createdAt)}
                      </span>
                      {!isResolved && (
                        <button
                          type="button"
                          onClick={() => handleRetry(job.id)}
                          disabled={retryingId === job.id}
                          className="inline-flex min-h-[32px] items-center gap-1.5 rounded-lg border border-espresso-300 bg-white px-3 text-xs font-semibold text-espresso-900 hover:bg-espresso-50 disabled:opacity-50 transition"
                        >
                          <RotateCcw className={`h-3.5 w-3.5 ${retryingId === job.id ? 'animate-spin' : ''}`} />
                          Retry Task
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="mt-3 text-xs text-rose-900 font-mono bg-white/70 p-2.5 rounded-xl border border-rose-100 break-words">
                    {job.errorMessage}
                  </div>

                  {job.argsJson && (
                    <div className="mt-2 text-xs text-espresso-600">
                      <span className="font-semibold text-espresso-800">Task Args: </span>
                      <code className="bg-espresso-100 px-1 py-0.5 rounded text-[11px]">
                        {JSON.stringify(job.argsJson)}
                      </code>
                    </div>
                  )}

                  {job.traceback && (
                    <div className="mt-2">
                      <button
                        type="button"
                        onClick={() => setExpandedTraceback(isExpanded ? null : job.id)}
                        className="text-xs font-medium text-espresso-700 hover:text-espresso-900 underline"
                      >
                        {isExpanded ? 'Hide Traceback' : 'View Traceback (truncated)'}
                      </button>

                      {isExpanded && (
                        <pre className="mt-2 max-h-48 overflow-y-auto rounded-xl bg-espresso-950 p-3 text-[11px] font-mono text-espresso-200">
                          {job.traceback}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
