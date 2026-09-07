/**
 * Customer persona for the demo Kimi-driven chat test.
 *
 * Wraps a minimal OpenAI-compatible chat completion call (LiteLLM-compatible)
 * so the test can hand any AI question over to a "clueless homeowner" LLM
 * persona and post its natural-language reply back into the chat UI.
 */

export type PersonaContext = {
  askedSoFar: string[];
  answeredSoFar: string[];
  latestQuestion: string;
};

// Backend job the AI chat is triaging. Kept together so the persona's ground
// truth and the seed lead's title stay in sync.
export const PERSONA = {
  leadTitle: "Extra sockets in living room and bedroom",
  leadRawText:
    "I'd like a couple more sockets in the living room and one in the bedroom. I don't know much about the electrics — happy for the electrician to advise.",
  category: "socket_upgrade",
  postcode: "SK8 3NJ",
  // The homeowner "knows" these facts and reveals them naturally when asked.
  homeownerFacts: {
    property: "3-bed semi-detached, about 20 years old",
    consumerUnit:
      "the fuse box is in a cupboard under the stairs, looks pretty old with white switches",
    parking: "there's a driveway right in front",
    rooms: "two extra double sockets in the living room, one in the main bedroom",
    existingSetup:
      "the current sockets are white plastic, mounted flush in the walls; happy with surface trunking if it's easier",
    timing: "any time in the next couple of weeks, we work from home so anytime really",
    preference:
      "would prefer sockets to match the existing white ones, but not fussy — happy with electrician's recommendation",
    budget:
      "not really sure what it should cost, hoping it's under £500 all-in for the whole job",
    knownIssues: "no known problems, everything works fine now",
  },
};

const CUSTOMER_SYSTEM_PROMPT = `You are role-playing a UK homeowner who has requested an electrician quote via an app. You are chatting with the electrician's AI assistant.

Ground truth about your home and the job (reveal facts naturally when asked, don't dump them):
${Object.entries(PERSONA.homeownerFacts)
  .map(([key, value]) => `- ${key}: ${value}`)
  .join("\n")}

Job the electrician is quoting: ${PERSONA.leadTitle}
Details you provided in the original request: ${PERSONA.leadRawText}

Rules:
- Reply in a friendly, natural tone — like a real homeowner texting.
- Answer only the question you were just asked. Don't volunteer unrelated details.
- You are NOT an electrician — never use technical jargon (RCBO, ring final, etc). If the AI asks something technical, say you don't know but describe what you see (colours, position, number of switches, etc.).
- Keep replies short — 1 to 2 sentences.
- Do NOT include quotation marks in your reply.
- Do NOT ask questions back.
- Respond with the reply text ONLY. No prefixes, no JSON, no formatting.`;

function resolveEnv(): {
  apiKey: string;
  apiBase: string;
  model: string;
} {
  // Customer persona prefers a small chatty model (gpt-4o-mini via OpenAI)
  // over the backend's reasoning LLM. Reasoning models like kimi-k2.6 often
  // return their answer in ``reasoning_content`` with an empty ``content``
  // field, which does not fit a plain "answer as a homeowner" role. When only
  // LLM_API_KEY is present (or the caller sets E2E_CUSTOMER_MODEL) we fall
  // back to the backend LLM.
  const preferOpenAI = !process.env.E2E_CUSTOMER_MODEL && !!process.env.OPENAI_API_KEY;
  const apiKey = preferOpenAI
    ? (process.env.OPENAI_API_KEY as string)
    : process.env.LLM_API_KEY || process.env.OPENAI_API_KEY || "";
  if (!apiKey) {
    throw new Error(
      "OPENAI_API_KEY or LLM_API_KEY is required for the customer persona"
    );
  }
  const rawBase = preferOpenAI
    ? "https://api.openai.com/v1"
    : process.env.LLM_API_BASE || "https://api.openai.com/v1";
  const apiBase = rawBase.replace(/\/+$/, "");
  const rawModel = preferOpenAI
    ? "gpt-4o-mini"
    : process.env.E2E_CUSTOMER_MODEL || process.env.LLM_MODEL || "gpt-4o-mini";
  // LiteLLM's "openai/kimi-k2.6" prefix is for LiteLLM routing; the underlying
  // endpoint expects the raw model name.
  const model = rawModel.replace(/^openai\//, "");
  return { apiKey, apiBase, model };
}

function buildChatHistory(context: PersonaContext): Array<{ role: string; content: string }> {
  const messages: Array<{ role: string; content: string }> = [
    { role: "system", content: CUSTOMER_SYSTEM_PROMPT },
  ];
  // Reconstruct the chat as (AI asked, customer answered) pairs so the model
  // has proper turn context.
  const priorLen = Math.min(context.askedSoFar.length - 1, context.answeredSoFar.length);
  for (let i = 0; i < priorLen; i++) {
    messages.push({ role: "user", content: context.askedSoFar[i] });
    messages.push({ role: "assistant", content: context.answeredSoFar[i] });
  }
  messages.push({ role: "user", content: context.latestQuestion });
  return messages;
}

export async function generateCustomerReply(context: PersonaContext): Promise<string> {
  const { apiKey, apiBase, model } = resolveEnv();
  const supportsTemperature = !/^kimi-k/i.test(model);
  const body: Record<string, unknown> = {
    model,
    messages: buildChatHistory(context),
    max_tokens: 220,
  };
  if (supportsTemperature) body.temperature = 0.7;

  const response = await fetch(`${apiBase}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`Customer LLM call failed (${response.status}): ${text.slice(0, 500)}`);
  }
  const parsed = (await response.json()) as {
    choices?: Array<{
      message?: { content?: string | null; reasoning_content?: string | null };
    }>;
  };
  const message = parsed.choices?.[0]?.message;
  const content = (message?.content ?? message?.reasoning_content ?? "").trim();
  if (!content) {
    throw new Error(
      `Customer LLM returned no content (model=${model}); raw=${JSON.stringify(parsed).slice(
        0,
        500
      )}`
    );
  }
  // Occasionally the model wraps the reply in quotes — strip them.
  return content.replace(/^["'`]+|["'`]+$/g, "").trim();
}
