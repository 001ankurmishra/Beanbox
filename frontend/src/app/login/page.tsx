'use client';

import React, { Suspense, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Eye, EyeOff, Coffee } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import { ApiClientError } from '@/lib/api/client';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = searchParams.get('next') || '/';
  const { login } = useAuth();
  const { showToast } = useToast();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg('');
    setSubmitting(true);
    try {
      const user = await login(email, password);
      showToast(`Welcome back, ${user.name.split(' ')[0]}!`, 'success');
      router.push(nextPath);
    } catch (err) {
      const msg =
        err instanceof ApiClientError ? err.message : 'Could not sign in';
      setErrorMsg(msg);
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-md px-4 py-14">
      <div className="rounded-3xl border border-espresso-200 bg-white p-7 shadow-warm">
        <div className="flex items-center gap-2.5 text-espresso-900">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-espresso-900 text-caramel-light">
            <Coffee className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <h1 className="font-serif text-2xl font-bold">Sign in to BeanBox</h1>
            <p className="text-xs text-espresso-600">
              Your guest cart merges automatically on login.
            </p>
          </div>
        </div>

        {errorMsg && (
          <div
            role="alert"
            className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs font-medium text-rose-800"
          >
            {errorMsg}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label
              htmlFor="login-email"
              className="block text-xs font-semibold text-espresso-800"
            >
              Email Address *
            </label>
            <input
              id="login-email"
              name="email"
              type="email"
              required
              autoComplete="username"
              autoCorrect="off"
              autoCapitalize="none"
              spellCheck={false}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 h-12 w-full rounded-xl border border-espresso-200 px-3.5 text-base"
            />
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label
                htmlFor="login-password"
                className="block text-xs font-semibold text-espresso-800"
              >
                Password *
              </label>
              <Link
                href="/forgot-password"
                className="text-xs font-medium text-caramel-dark hover:underline"
              >
                Forgot password?
              </Link>
            </div>
            <div className="relative mt-1">
              <input
                id="login-password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="h-12 w-full rounded-xl border border-espresso-200 pl-3.5 pr-11 text-base"
              />
              <button
                type="button"
                aria-pressed={showPassword}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                onClick={() => setShowPassword((s) => !s)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-espresso-500 hover:text-espresso-900"
              >
                {showPassword ? (
                  <EyeOff className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <Eye className="h-4 w-4" aria-hidden="true" />
                )}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="min-h-[48px] w-full rounded-xl bg-espresso-900 px-4 text-sm font-semibold text-white hover:bg-caramel transition disabled:opacity-50"
          >
            {submitting ? 'Signing in…' : 'Sign In'}
          </button>
        </form>

        {/* Demo Quick Fill */}
        <div className="mt-6 rounded-2xl border border-espresso-200 bg-espresso-50 p-4">
          <div className="text-xs font-semibold text-espresso-800">
            Quick Demo Accounts
          </div>
          <div className="mt-2.5 grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => {
                setEmail('arjun@beanbox.in');
                setPassword('Coffee@1234');
              }}
              className="rounded-xl border border-espresso-200 bg-white px-3 py-2 text-xs font-medium text-espresso-800 hover:border-caramel"
            >
              Customer (Arjun)
            </button>
            <button
              type="button"
              onClick={() => {
                setEmail('admin@beanbox.in');
                setPassword('Admin@1234');
              }}
              className="rounded-xl border border-espresso-200 bg-white px-3 py-2 text-xs font-medium text-espresso-800 hover:border-caramel"
            >
              Roaster Admin
            </button>
          </div>
        </div>

        <p className="mt-5 text-center text-xs text-espresso-600">
          New to BeanBox?{' '}
          <Link href="/signup" className="font-semibold text-caramel-dark hover:underline">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="py-14 text-center">Loading…</div>}>
      <LoginForm />
    </Suspense>
  );
}
