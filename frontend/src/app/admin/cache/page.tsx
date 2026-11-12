'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { adminApi } from '@/lib/api/endpoints';
import { CacheStats } from '@/types/api';

export default function AdminCachePage() {
  const [stats, setStats] = useState<CacheStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');

  const loadStats = useCallback(async () => {
    setLoading(true);
    setErrorMsg('');
    try {
      const res = await adminApi.cacheStats();
      setStats(res.stats);
    } catch {
      setErrorMsg('Failed to load cache & Redis telemetry.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  const hitPct = stats ? `${(stats.hitRatio * 100).toFixed(1)}%` : '0.0%';

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-serif text-3xl font-bold text-espresso-900">
            Redis &amp; Cache Observability
          </h1>
          <p className="mt-1 text-sm text-espresso-600">
            Live catalog cache hit/miss ratios, sliding-window limiter blocks, idempotent checkout replays, and scanned key counts.
          </p>
        </div>
        <button
          type="button"
          onClick={loadStats}
          disabled={loading}
          className="inline-flex min-h-[42px] items-center gap-2 rounded-xl border border-espresso-200 bg-white px-4 text-sm font-semibold text-espresso-900 hover:bg-espresso-50 disabled:opacity-60"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {errorMsg && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
          {errorMsg}
        </div>
      )}

      {stats && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-2xl border border-espresso-200 bg-white p-5 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wider text-espresso-500">
                Redis Status
              </p>
              <div className="mt-2 flex items-center gap-2">
                <span
                  className={`inline-block h-2.5 w-2.5 rounded-full ${
                    stats.connected
                      ? 'bg-emerald-500'
                      : stats.enabled
                        ? 'bg-amber-500'
                        : 'bg-espresso-300'
                  }`}
                />
                <p className="text-xl font-bold text-espresso-900">
                  {stats.connected
                    ? 'Connected'
                    : stats.enabled
                      ? 'Fallback Mode (Unreachable)'
                      : 'Disabled (In-Memory)'}
                </p>
              </div>
              <p className="mt-1 text-xs text-espresso-500">
                Memory: {stats.memoryUsedHuman} ({stats.memoryUsedBytes.toLocaleString()} bytes)
              </p>
            </div>

            <div className="rounded-2xl border border-espresso-200 bg-white p-5 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wider text-espresso-500">
                Catalog Cache Hit Ratio
              </p>
              <p className="mt-2 text-2xl font-bold text-espresso-900">{hitPct}</p>
              <p className="mt-1 text-xs text-espresso-500">
                Hits: {stats.hits.toLocaleString()} · Misses: {stats.misses.toLocaleString()}
              </p>
            </div>

            <div className="rounded-2xl border border-espresso-200 bg-white p-5 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wider text-espresso-500">
                Rate-Limit Blocks (429)
              </p>
              <p className="mt-2 text-2xl font-bold text-espresso-900">
                {stats.rateLimitBlocks.toLocaleString()}
              </p>
              <p className="mt-1 text-xs text-espresso-500">
                Blocked across sliding-window ZSET buckets
              </p>
            </div>

            <div className="rounded-2xl border border-espresso-200 bg-white p-5 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wider text-espresso-500">
                Idempotent Replays
              </p>
              <p className="mt-2 text-2xl font-bold text-espresso-900">
                {stats.idempotentReplays.toLocaleString()}
              </p>
              <p className="mt-1 text-xs text-espresso-500">
                Duplicate checkout/payment requests safely replayed
              </p>
            </div>

            <div className="rounded-2xl border border-espresso-200 bg-white p-5 shadow-sm sm:col-span-2">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wider text-espresso-500">
                  Active Keys by Domain (Bounded SCAN)
                </p>
                <span className="text-xs font-semibold text-espresso-700">
                  Total: {stats.totalKeys.toLocaleString()}
                  {stats.scanTruncated ? ' (capped)' : ''}
                </span>
              </div>
              {Object.keys(stats.keysByDomain).length === 0 ? (
                <p className="mt-3 text-sm text-espresso-500">No active Redis keys.</p>
              ) : (
                <div className="mt-3 flex flex-wrap gap-2">
                  {Object.entries(stats.keysByDomain)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([domain, count]) => (
                      <div
                        key={domain}
                        className="rounded-xl border border-espresso-200 bg-cream-50 px-3 py-2 text-xs"
                      >
                        <span className="font-semibold text-espresso-900">{domain}</span>
                        <span className="ml-2 text-espresso-600">{count}</span>
                      </div>
                    ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
