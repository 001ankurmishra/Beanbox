'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Coffee, Eye, EyeOff } from 'lucide-react';
import { GoogleSignInButton } from '@/components/auth/GoogleSignInButton';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';
import { ApiClientError } from '@/lib/api/client';

export default function SignupPage() {
  const router = useRouter();
  const { signup } = useAuth();
  const { showToast } = useToast();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg('');
    setSubmitting(true);
    try {
      await signup({
        name,
        email,
        password,
        phone: phone.trim() || undefined
      });
      showToast(
        'Welcome to BeanBox! Please verify your email before checkout.',
        'success'
      );
      router.push('/verify-email');
    } catch (err) {
      setErrorMsg(
        err instanceof ApiClientError ? err.message : 'Signup failed'
      );
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
            <h1 className="font-serif text-2xl font-bold">Join BeanBox</h1>
            <p className="text-xs text-espresso-600">
              Enjoy faster checkouts, order tracking & wishlist sync.
            </p>
          </div>
        </div>

        <GoogleSignInButton nextPath="/shop" />

        <div className="my-5 flex items-center gap-3 text-[11px] uppercase tracking-wider text-espresso-400">
          <span className="h-px flex-1 bg-espresso-200" />
          <span>or sign up with email</span>
          <span className="h-px flex-1 bg-espresso-200" />
        </div>

        {errorMsg && (
          <div
            role="alert"
            className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs font-medium text-rose-800"
          >
            {errorMsg}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="signup-name"
              className="block text-xs font-semibold text-espresso-800"
            >
              Full Name <span aria-hidden="true">*</span>
            </label>
            <input
              id="signup-name"
              name="name"
              type="text"
              required
              minLength={2}
              autoComplete="name"
              enterKeyHint="next"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="auth-field mt-1 h-12 w-full rounded-xl border border-espresso-200 px-3.5 text-base"
            />
          </div>

          <div>
            <label
              htmlFor="signup-email"
              className="block text-xs font-semibold text-espresso-800"
            >
              Email Address <span aria-hidden="true">*</span>
            </label>
            <input
              id="signup-email"
              name="email"
              type="email"
              required
              autoComplete="username"
              autoCorrect="off"
              autoCapitalize="none"
              spellCheck={false}
              enterKeyHint="next"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="auth-field mt-1 h-12 w-full rounded-xl border border-espresso-200 px-3.5 text-base"
            />
          </div>

          <div>
            <label
              htmlFor="signup-phone"
              className="block text-xs font-semibold text-espresso-800"
            >
              Indian Mobile Number (Optional)
            </label>
            <input
              id="signup-phone"
              name="phone"
              type="tel"
              inputMode="numeric"
              autoComplete="tel"
              enterKeyHint="next"
              placeholder="9876543210"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="auth-field mt-1 h-12 w-full rounded-xl border border-espresso-200 px-3.5 text-base"
            />
          </div>

          <div>
            <label
              htmlFor="signup-password"
              className="block text-xs font-semibold text-espresso-800"
            >
              Password <span aria-hidden="true">*</span>
            </label>
            <p id="pw-hint" className="mt-0.5 text-xs text-espresso-500">
              At least 10 characters, not a common password, and must not include your email.
            </p>
            <div className="relative mt-1.5">
              <input
                id="signup-password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                required
                minLength={10}
                autoComplete="new-password"
                enterKeyHint="done"
                aria-describedby="pw-hint"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="auth-field h-12 w-full rounded-xl border border-espresso-200 pl-3.5 pr-11 text-base"
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
            {submitting ? 'Creating Account…' : 'Create Account'}
          </button>
        </form>

        <p className="mt-5 text-center text-xs text-espresso-600">
          Already have an account?{' '}
          <Link href="/login" className="font-semibold text-caramel-dark hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
