import { PortalShell } from '../components/PortalShell'
import { ResetPasswordPanel } from '../reset/ResetPasswordPanel'

/**
 * Portal-branded /reset-password — same form flow as the marketing page,
 * wrapped in tenant chrome instead of the marketing Nav/Footer.
 */
export default function PortalResetPassword() {
  return (
    <PortalShell maxWidth="520px">
      <div className="flex justify-center">
        <ResetPasswordPanel />
      </div>
    </PortalShell>
  )
}
