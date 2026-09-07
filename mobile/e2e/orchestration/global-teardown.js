import { execSync } from "child_process";

async function globalTeardown() {
  // Stop the backend stack that start-backend.sh brought up. The Expo web
  // server is already terminated by Playwright's webServer teardown.
  execSync("bash ./e2e/orchestration/stop-backend.sh", {
    stdio: "inherit",
    cwd: process.cwd(),
  });
}

export default globalTeardown;
