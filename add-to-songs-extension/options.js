const helperBase = document.getElementById("helperBase");
const helperToken = document.getElementById("helperToken");
const status = document.getElementById("status");

chrome.storage.local.get(
  {
    helperBase: "http://127.0.0.1:8765",
    helperToken: ""
  },
  values => {
    helperBase.value = values.helperBase;
    helperToken.value = values.helperToken;
  }
);

document.getElementById("save").addEventListener("click", () => {
  chrome.storage.local.set(
    {
      helperBase: helperBase.value.trim() || "http://127.0.0.1:8765",
      helperToken: helperToken.value.trim()
    },
    () => {
      status.textContent = "Saved";
      setTimeout(() => {
        status.textContent = "";
      }, 1500);
    }
  );
});
