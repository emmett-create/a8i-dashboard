/**
 * A8I — Internal Gmail Inbox Labeler (no CASA / no a8i backend required)
 *
 * Runs entirely inside ONE Gmail inbox as a Google Apps Script. Classifies
 * each new, not-yet-processed thread with Claude and applies a real Gmail
 * label — same classification categories as a8i's own backend (app.py's
 * _classify()) so the taxonomy stays consistent if this ever needs to feed
 * into the real a8i dashboard later.
 *
 * WHY THIS AVOIDS CASA: GmailApp's only scope is https://mail.google.com/ —
 * Google's broadest restricted scope, same tier as a8i's own OAuth app.
 * The verification requirement is waived only when the script's owner and
 * the inbox it's running against are accounts in the SAME Google Workspace
 * domain/customer (a true "internal" app in Google's eyes) — NOT just
 * because it's small or unshared. Set this up by opening script.google.com
 * while logged into an account that belongs to THAT SAME client's own
 * Workspace domain. If Agency Eight's own account runs this against a
 * separate client's inbox instead, that's cross-domain and loses the
 * exemption entirely — same CASA review a8i needs.
 *
 * ── One-time setup ──────────────────────────────────────────────────────
 * 1. While logged into the target inbox's own Google account, go to
 *    script.google.com → New project. Paste this whole file in, replacing
 *    the default Code.gs content.
 * 2. Project Settings (gear icon, left sidebar) → Script Properties →
 *    add one property: ANTHROPIC_API_KEY = <the real key>. Never hardcode
 *    the key in this file — anyone who opens the script can read it.
 * 3. Run `setup` once from the editor's function dropdown + Run button.
 *    This is what triggers the one-time Google authorization prompt
 *    (Review Permissions → Allow) and installs the recurring trigger.
 * 4. Done — `labelNewThreads` now runs automatically every 10 minutes.
 *    Nothing else to open or check; the labels just appear in Gmail.
 *
 * To stop it: Triggers (clock icon, left sidebar) → delete the trigger.
 */

// ── Config ───────────────────────────────────────────────────────────────
const ANTHROPIC_MODEL = "claude-haiku-5-5"; // same model a8i's own backend uses for this exact task — cheap, fast, plenty for short-reply classification
const PROCESSED_LABEL = "A8I/Processed";
const MAX_THREADS_PER_RUN = 25; // bounds one run's time/quota use; a big backlog just finishes over several 10-minute runs instead of one long one
const CATEGORY_LABELS = {
  "Agree": "A8I/Agree",
  "Decline": "A8I/Decline",
  "Asks For Paid": "A8I/Asks For Paid",
  "Asks About Posting": "A8I/Asks About Posting",
  "Needs Human Review": "A8I/Needs Human Review",
};

// Identical taxonomy to app.py's _classify() — keep these in sync if that
// prompt ever changes, so a thread would get the same label whichever
// system touched it.
const CLASSIFY_SYSTEM_PROMPT =
  "You're sorting a reply email into exactly one category:\n" +
  "- Agree: a clear, unconditional yes, with no open question blocking next steps.\n" +
  "- Decline: a clear no / pass, with no counter-proposal or condition attached.\n" +
  "- Asks For Paid: explicitly says they only do paid partnerships, or asks what " +
  "the budget/rate would be for creating content.\n" +
  "- Asks About Posting: otherwise willing, and the ONLY open question is " +
  "whether posting/content is required or guaranteed (e.g. \"is there a posting " +
  "obligation?\", \"can you guarantee social coverage?\").\n" +
  "- Needs Human Review: anything else — hedged or non-committal (\"might\", " +
  "\"will circle back\"), out-of-office, a pure follow-up/bump with nothing new, " +
  "something unrelated to gifting outreach entirely, or bundling any other request " +
  "or question. When in doubt, pick Needs Human Review.\n" +
  "Reply with ONLY the category name, nothing else.";

/**
 * Run this once from the editor to authorize the script and install the
 * recurring trigger. Safe to re-run — clears any existing trigger for
 * labelNewThreads first so you never end up with duplicates.
 */
function setup() {
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === "labelNewThreads") ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger("labelNewThreads")
    .timeBased()
    .everyMinutes(10)
    .create();
  getOrCreateLabels_(); // creates all labels up front so they're visible in Gmail immediately, not just on first match
  Logger.log("Setup complete — labelNewThreads will now run every 10 minutes.");
}

/**
 * The recurring job. Finds inbox threads that haven't been processed yet,
 * classifies the latest message in each, applies the matching label plus
 * the Processed marker so it's never reconsidered.
 */
function labelNewThreads() {
  const apiKey = PropertiesService.getScriptProperties().getProperty("ANTHROPIC_API_KEY");
  if (!apiKey) {
    Logger.log("ANTHROPIC_API_KEY isn't set in Script Properties — see setup instructions at the top of this file.");
    return;
  }

  const labels = getOrCreateLabels_();
  const threads = GmailApp.search(`in:inbox -label:"${PROCESSED_LABEL}"`, 0, MAX_THREADS_PER_RUN);

  threads.forEach(thread => {
    try {
      const messages = thread.getMessages();
      const last = messages[messages.length - 1];
      const text = `Subject: ${thread.getFirstMessageSubject()}\n\n${last.getPlainBody()}`.slice(0, 6000);

      const category = classifyWithClaude_(text, apiKey);
      const label = labels[category] || labels["Needs Human Review"];
      thread.addLabel(label);
      thread.addLabel(labels[PROCESSED_LABEL]);
    } catch (err) {
      // One bad thread (e.g. a malformed message, a transient API error)
      // never blocks the rest of the batch — it's just left unlabeled and
      // retried on the next run since it never got the Processed label.
      Logger.log(`Skipped thread "${thread.getFirstMessageSubject()}": ${err}`);
    }
  });
}

function classifyWithClaude_(messageText, apiKey) {
  const res = UrlFetchApp.fetch("https://api.anthropic.com/v1/messages", {
    method: "post",
    contentType: "application/json",
    headers: {
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
    },
    payload: JSON.stringify({
      model: ANTHROPIC_MODEL,
      max_tokens: 300, // room to think AND answer — a bare few tokens can get eaten entirely by a thinking block on some replies
      system: CLASSIFY_SYSTEM_PROMPT,
      messages: [{ role: "user", content: messageText }],
    }),
    muteHttpExceptions: true,
  });

  if (res.getResponseCode() !== 200) {
    throw new Error(`Claude API error ${res.getResponseCode()}: ${res.getContentText().slice(0, 300)}`);
  }
  const data = JSON.parse(res.getContentText());
  const textBlock = (data.content || []).find(b => b.type === "text");
  return textBlock ? textBlock.text.trim() : "Needs Human Review";
}

/**
 * Creates (or fetches, if they already exist) every label this script
 * uses, keyed the same way CATEGORY_LABELS is, plus the Processed marker
 * under its own key. Gmail treats "A8I/Agree" as a nested label under a
 * parent "A8I" label automatically — no separate parent-creation step
 * needed.
 */
function getOrCreateLabels_() {
  const names = Object.values(CATEGORY_LABELS).concat([PROCESSED_LABEL]);
  const byName = {};
  names.forEach(name => {
    byName[name] = GmailApp.getUserLabelByName(name) || GmailApp.createLabel(name);
  });
  // Re-key by category name (not label string) for easy lookup in labelNewThreads.
  const byCategory = { [PROCESSED_LABEL]: byName[PROCESSED_LABEL] };
  Object.keys(CATEGORY_LABELS).forEach(cat => { byCategory[cat] = byName[CATEGORY_LABELS[cat]]; });
  return byCategory;
}
