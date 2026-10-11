"use strict";

// Voice is only an input adapter. Map rendering and selection remain in lab9.js.
const SPOKEN_ALIASES = {
  "usa": "USA",
  "u s a": "USA",
  "us": "USA",
  "hong kong": "HKG",
  "south korea": "KOR",
  "korea": "KOR",
  "russia": "RUS",
  "uae": "ARE",
  "turkey": "TUR",
};

function normalizeSpeech(text) {
  return String(text || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function parseVoiceCommand(transcript, economies) {
  const command = normalizeSpeech(transcript);
  if (!command) return { type: "unknown" };
  if (command === "clear" || command === "clear selection") return { type: "clear-selection" };
  if (command === "reset" || command === "reset map") return { type: "reset-map" };
  if (command === "help" || command === "commands") return { type: "help" };

  const countryMatch = command.match(/^(highlight|select|show)\s+(.+)$/);
  if (!countryMatch) return { type: "unknown" };
  if (!Array.isArray(economies) || economies.length === 0) return { type: "not-ready" };
  const requested = normalizeSpeech(countryMatch[2]);
  const exact = economies.find((economy) => normalizeSpeech(economy.country) === requested);
  const aliasedIso = SPOKEN_ALIASES[requested];
  const alias = aliasedIso && economies.find((economy) => economy.iso3 === aliasedIso);
  const match = exact || alias;
  return match ? { type: "select-country", iso3: match.iso3, country: match.country } : { type: "unknown" };
}

function liveEconomies(select) {
  return Array.from(select.options)
    .filter((option) => option.value)
    .map((option) => ({
      iso3: option.value,
      country: option.textContent.replace(/^\d+\.\s*/, "").trim(),
    }));
}

function initVoiceControl() {
  const voiceButton = document.getElementById("voice-button");
  const status = document.getElementById("voice-status");
  const heard = document.getElementById("voice-heard");
  const action = document.getElementById("voice-action");
  const select = document.getElementById("country-select");
  const clearButton = document.getElementById("clear-selection");
  const resetButton = document.getElementById("reset-map");
  const SpeechRecognition = window.__lab10ForceUnsupported ? undefined : (window.__lab10MockSpeechRecognition || window.SpeechRecognition || window.webkitSpeechRecognition);
  if (!SpeechRecognition) {
    voiceButton.disabled = true;
    status.textContent = "Voice recognition is not supported in this browser.";
    action.textContent = "Use the country selector, mouse, or keyboard controls instead.";
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.lang = "en-US";
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  let sessionError = false;

  function showHelp() {
    action.textContent = "Commands: Highlight Japan, Highlight Singapore, Highlight Hong Kong, Clear selection, or Reset map.";
  }

  function applyCommand(transcript) {
    heard.textContent = `“${transcript}”`;
    const result = parseVoiceCommand(transcript, liveEconomies(select));
    if (result.type === "select-country") {
      select.value = result.iso3;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      action.textContent = `Highlighting ${result.country} in both GDP views.`;
    } else if (result.type === "clear-selection") {
      clearButton.click();
      action.textContent = "Cleared the selected economy in both GDP views.";
    } else if (result.type === "reset-map") {
      resetButton.click();
      action.textContent = "Reset the geographic map to its full-world view.";
    } else if (result.type === "help") {
      showHelp();
    } else if (result.type === "not-ready") {
      action.textContent = "Visualization data are still loading. Try again in a moment.";
    } else {
      action.textContent = "Command not recognized. Try “Highlight Japan”, “Clear selection”, or “Reset map”.";
    }
  }

  function errorMessage(error) {
    const code = error && error.error;
    if (code === "not-allowed" || code === "service-not-allowed") return "Microphone permission was not granted. Use the country selector, mouse, or keyboard controls instead.";
    if (code === "no-speech") return "No speech was detected. Try again or use the country selector, mouse, or keyboard controls.";
    if (code === "audio-capture") return "No microphone was available. Use the country selector, mouse, or keyboard controls instead.";
    if (code === "network") return "Speech recognition had a network error. Use the country selector, mouse, or keyboard controls instead.";
    return "Voice recognition had an error. Use the country selector, mouse, or keyboard controls instead.";
  }

  function startListening() {
    sessionError = false;
    voiceButton.disabled = true;
    status.textContent = "Listening…";
    heard.textContent = "—";
    action.textContent = "Say a supported command.";
    try {
      recognition.start();
    } catch (error) {
      sessionError = true;
      voiceButton.disabled = false;
      status.textContent = "Voice recognition could not start.";
      action.textContent = "Use the country selector, mouse, or keyboard controls instead.";
    }
  }

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    applyCommand(transcript);
    status.textContent = "Command received. Voice control is inactive.";
  };
  recognition.onerror = (event) => {
    sessionError = true;
    status.textContent = "Voice recognition error.";
    action.textContent = errorMessage(event);
  };
  recognition.onend = () => {
    voiceButton.disabled = false;
    if (!sessionError) status.textContent = "Voice control inactive.";
  };
  voiceButton.addEventListener("click", startListening);
  status.textContent = "Voice control inactive. Press Start Voice Control to listen once.";
  action.textContent = "Conventional map controls are always available.";
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  initVoiceControl();
}

if (typeof module !== "undefined") {
  module.exports = { normalizeSpeech, parseVoiceCommand };
}
