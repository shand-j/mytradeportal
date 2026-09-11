export const TESTFLIGHT_URL = import.meta.env.VITE_TESTFLIGHT_URL ?? '#beta'

/** True when the TestFlight link hasn't been configured yet. */
export const testflightConfigured = () => Boolean(import.meta.env.VITE_TESTFLIGHT_URL)
