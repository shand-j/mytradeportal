import { headers } from "next/headers";
import { Nav } from "@/components/nav";
import { Hero } from "@/components/hero";
import { Marquee } from "@/components/marquee";
import { Features } from "@/components/features";
import { HowItWorks } from "@/components/how-it-works";
import { Pricing } from "@/components/pricing";
import { Faq } from "@/components/faq";
import { BetaCta } from "@/components/beta-cta";
import { Footer } from "@/components/footer";

export default async function Home() {
  const h = await headers();
  const country = h.get("x-vercel-ip-country") ?? "OTHERS";

  return (
    <>
      <Nav />
      <main>
        <Hero />
        <Marquee />
        <Features />
        <HowItWorks />
        <Pricing country={country} />
        <Faq />
        <BetaCta />
      </main>
      <Footer />
    </>
  );
}
