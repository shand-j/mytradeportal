import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Zap, Loader2 } from 'lucide-react';

import { authService } from '@/lib/api/auth';
import { useAuthStore } from '@/stores/authStore';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

const loginSchema = z.object({
  tenantSlug: z.string().min(1, 'Business slug is required'),
  email: z.string().email('Enter a valid email'),
  password: z.string().min(1, 'Password is required'),
});

type LoginForm = z.infer<typeof loginSchema>;

export function Login() {
  const navigate = useNavigate();
  const { login } = useAuthStore();
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      tenantSlug: '',
      email: '',
      password: '',
    },
  });

  const onSubmit = async (data: LoginForm) => {
    setError(null);
    try {
      const user = await authService.login(data);
      login(user);
      navigate('/', { replace: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Login failed';
      setError(message);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#F8F7F4] p-4">
      <Card className="w-full max-w-md border-[#E7E5E4] bg-white">
        <CardHeader className="space-y-1 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-[#D4650A]">
            <Zap className="h-6 w-6 text-white" />
          </div>
          <CardTitle className="text-2xl font-semibold text-[#1C1917]">
            My Trade Portal
          </CardTitle>
          <CardDescription className="text-[#78716C]">
            Sign in to your back-office dashboard
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="tenantSlug" className="text-[#1C1917]">
                Business slug
              </Label>
              <Input
                id="tenantSlug"
                type="text"
                autoComplete="organization"
                {...register('tenantSlug')}
                placeholder="your-business"
                className="border-[#E7E5E4]"
              />
              {errors.tenantSlug && (
                <p className="text-xs text-[#DC2626]">{errors.tenantSlug.message}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="email" className="text-[#1C1917]">
                Email
              </Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                {...register('email')}
                placeholder="you@example.com"
                className="border-[#E7E5E4]"
              />
              {errors.email && (
                <p className="text-xs text-[#DC2626]">{errors.email.message}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="password" className="text-[#1C1917]">
                Password
              </Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                {...register('password')}
                placeholder="••••••••"
                className="border-[#E7E5E4]"
              />
              {errors.password && (
                <p className="text-xs text-[#DC2626]">{errors.password.message}</p>
              )}
            </div>

            {error && (
              <div className="rounded-lg bg-[#FEF2F2] px-3 py-2 text-sm text-[#DC2626]">
                {error}
              </div>
            )}

            <Button
              type="submit"
              disabled={isSubmitting}
              className="w-full bg-[#D4650A] hover:bg-[#B85500] text-white"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Signing in…
                </>
              ) : (
                'Sign in'
              )}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
