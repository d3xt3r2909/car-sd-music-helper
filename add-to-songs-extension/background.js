const defaultHelperBase = "http://127.0.0.1:8765";

async function helperSettings() {
  const values = await chrome.storage.local.get({
    helperBase: defaultHelperBase,
    helperToken: ""
  });
  return values;
}

async function setBadge(text, color) {
  await chrome.action.setBadgeBackgroundColor({ color });
  await chrome.action.setBadgeText({ text });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }), 1800);
}

function isYouTubeUrl(url) {
  return /(^https?:\/\/)?([^/]+\.)?(youtube\.com|youtu\.be)\//i.test(url || "");
}

function isYouTubeVideoUrl(url) {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace(/^www\./, "");
    return (
      (["youtube.com", "m.youtube.com", "music.youtube.com"].includes(host) && parsed.pathname === "/watch" && parsed.searchParams.has("v")) ||
      (host === "youtu.be" && parsed.pathname.length > 1) ||
      (["youtube.com", "m.youtube.com"].includes(host) && parsed.pathname.startsWith("/shorts/"))
    );
  } catch (_) {
    return false;
  }
}

async function requestJson(path, params = {}) {
  const settings = await helperSettings();
  const target = new URL(path, settings.helperBase || defaultHelperBase);
  Object.entries(params).forEach(([key, value]) => target.searchParams.set(key, value || ""));
  const headers = settings.helperToken ? { "X-Nova-Token": settings.helperToken } : {};
  const response = await fetch(target.toString(), { headers });
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("AUTH");
    }
    throw new Error(`Helper returned ${response.status}`);
  }
  return response.json();
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function openNextAndCloseCurrent(currentTab, next) {
  if (next && next.url) {
    await chrome.tabs.create({
      url: next.url,
      active: true,
      windowId: currentTab.windowId,
      index: currentTab.index + 1
    });
  }

  if (currentTab && currentTab.id) {
    await chrome.tabs.remove(currentTab.id);
  }
}

async function acceptCurrentYouTubeTab() {
  const tab = await activeTab();

  if (!tab || !isYouTubeVideoUrl(tab.url)) {
    await setBadge("NO", "#b91c1c");
    return;
  }

  try {
    const result = await requestJson("/accept", {
      url: tab.url,
      title: tab.title || ""
    });

    await setBadge(result.next && result.next.url ? "OK" : "END", "#0f766e");
    await openNextAndCloseCurrent(tab, result.next);
  } catch (error) {
    await setBadge(error.message === "AUTH" ? "AUTH" : "OFF", "#b91c1c");
  }
}

async function skipCurrentSuggestion() {
  const tab = await activeTab();

  if (!tab || !isYouTubeUrl(tab.url)) {
    await setBadge("NO", "#b91c1c");
    return;
  }

  try {
    const result = await requestJson("/skip");
    await setBadge(result.next && result.next.url ? "SKIP" : "END", "#b45309");
    await openNextAndCloseCurrent(tab, result.next);
  } catch (error) {
    await setBadge(error.message === "AUTH" ? "AUTH" : "OFF", "#b91c1c");
  }
}

chrome.action.onClicked.addListener(acceptCurrentYouTubeTab);

chrome.commands.onCommand.addListener((command) => {
  if (command === "add-current-youtube") {
    acceptCurrentYouTubeTab();
  }
  if (command === "skip-current-suggestion") {
    skipCurrentSuggestion();
  }
});

chrome.runtime.onMessage.addListener((message) => {
  if (message && message.action === "accept") {
    acceptCurrentYouTubeTab();
  }
  if (message && message.action === "skip") {
    skipCurrentSuggestion();
  }
});
