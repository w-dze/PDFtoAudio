const pdfInput = document.querySelector("#pdfInput");
const dropZone = document.querySelector("#dropZone");
const uploadButton = document.querySelector("#uploadButton");
const startButton = document.querySelector("#startButton");
const stopButton = document.querySelector("#stopButton");
const fileName = document.querySelector("#fileName");
const message = document.querySelector("#message");
const statusPill = document.querySelector("#statusPill");
const progressFill = document.querySelector("#progressFill");

let selectedFile = null;

function setSelectedFile(file) {
  selectedFile = file;
  fileName.textContent = file ? file.name : "Choose or drop a PDF";
  uploadButton.disabled = !file;
}

function updateFromState(state) {
  statusPill.textContent = state.status.charAt(0).toUpperCase() + state.status.slice(1);
  message.textContent = state.message;

  if (state.fileName) {
    fileName.textContent = state.fileName;
  }

  const hasPdf = Boolean(state.fileName);
  const isReading = state.status === "reading" || state.status === "stopping";
  startButton.disabled = !hasPdf || isReading;
  startButton.textContent = state.status === "paused" ? "Resume" : "Start";
  stopButton.disabled = !isReading;

  if (state.page && state.pages) {
    progressFill.style.width = `${Math.round((state.page / state.pages) * 100)}%`;
  } else if (state.status === "finished") {
    progressFill.style.width = "100%";
  } else {
    progressFill.style.width = "0%";
  }
}

async function refreshStatus() {
  const response = await fetch("/api/status");
  updateFromState(await response.json());
}

async function uploadPdf() {
  if (!selectedFile) {
    message.textContent = "Choose a PDF first.";
    return;
  }

  const formData = new FormData();
  formData.append("pdf", selectedFile);
  message.textContent = "Uploading PDF...";
  uploadButton.disabled = true;

  const response = await fetch("/api/upload", {
    method: "POST",
    body: formData,
  });
  const result = await response.json();

  if (!result.ok) {
    message.textContent = result.message;
    uploadButton.disabled = false;
    return;
  }

  updateFromState(result.state);
}

async function postAction(url) {
  if (url === "/api/stop") {
    stopButton.disabled = true;
    message.textContent = "Stopping audio...";
    statusPill.textContent = "Stopping";
  }

  const response = await fetch(url, { method: "POST" });
  const result = await response.json();
  updateFromState(result.state);
}

pdfInput.addEventListener("change", () => {
  setSelectedFile(pdfInput.files[0] || null);
});

dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("is-dragging");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("is-dragging");
});

dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("is-dragging");
  const file = event.dataTransfer.files[0];
  if (!file || file.type !== "application/pdf") {
    message.textContent = "Please drop a PDF file.";
    return;
  }
  setSelectedFile(file);
});

uploadButton.addEventListener("click", uploadPdf);
startButton.addEventListener("click", () => postAction("/api/start"));
stopButton.addEventListener("click", () => postAction("/api/stop"));

setSelectedFile(null);
refreshStatus();
setInterval(refreshStatus, 1000);
