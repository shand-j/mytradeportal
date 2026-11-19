import { useState } from 'react'
import { PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'

/**
 * Stripe Payment Element form shared by the token pay page (/pay/:token) and
 * the tenant portal invoice view. Must be rendered inside <Elements>.
 */
export function PaymentForm({
  returnUrl,
  submitLabel,
}: {
  returnUrl: string
  submitLabel: string
}) {
  const stripe = useStripe()
  const elements = useElements()
  const [processing, setProcessing] = useState(false)
  const [paymentError, setPaymentError] = useState<string | null>(null)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!stripe || !elements || processing) return
    setProcessing(true)
    setPaymentError(null)
    const { error } = await stripe.confirmPayment({
      elements,
      confirmParams: { return_url: returnUrl },
    })
    // Reaching here means the payment failed without a redirect (declined
    // card, validation error) — success navigates away to the return_url.
    setProcessing(false)
    setPaymentError(
      error.message ?? 'Your payment could not be processed — check your details and try again.',
    )
  }

  return (
    <form onSubmit={handleSubmit} className="mt-[var(--space-lg)]">
      <PaymentElement />
      {paymentError && (
        <p
          role="alert"
          className="mt-[var(--space-md)] border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed"
        >
          {paymentError}
        </p>
      )}
      <button
        type="submit"
        disabled={!stripe || !elements || processing}
        className="chip chip--fill chip--brand mt-[var(--space-lg)] w-full justify-center disabled:cursor-not-allowed disabled:opacity-60"
      >
        {processing ? 'Processing…' : submitLabel}
      </button>
      <p className="mt-[var(--space-sm)] text-center text-[12.5px] text-[var(--muted)]">
        Secured by Stripe — your card details never touch our servers.
      </p>
    </form>
  )
}
