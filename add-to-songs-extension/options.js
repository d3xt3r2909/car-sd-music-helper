const helperBase = document.getElementById("helperBase");
const status = document.getElementById("status");

chrome.storage.local.get(
  {
    helperBase: "http://127.0.0.1:8765"
  },
  values => {
    helperBase.value = values.helperBase;
  }
);

document.getElementById("save").addEventListener("click", () => {
  chrome.storage.local.set(
    {
      helperBase: helperBase.value.trim() || "http://127.0.0.1:8765"
    },
    () => {
      status.textContent = "Saved";
      setTimeout(() => {
        status.textContent = "";
      }, 1500);
    }
  );
});
