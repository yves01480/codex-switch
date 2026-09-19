(() => {
  const button = document.querySelector("[data-copy-button]");
  const source = document.querySelector("[data-copy-text]");
  const toast = document.querySelector(".toast");
  if (!button || !source || !toast) return;

  let timer;

  const showToast = (message) => {
    toast.textContent = message;
    toast.setAttribute("aria-hidden", "false");
    toast.classList.add("visible");
    clearTimeout(timer);
    timer = setTimeout(() => {
      toast.classList.remove("visible");
      toast.setAttribute("aria-hidden", "true");
    }, 1800);
  };

  const fallbackCopy = (text) => {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  };

  button.addEventListener("click", async () => {
    const text = source.textContent.trim();
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else if (!fallbackCopy(text)) {
        throw new Error("copy failed");
      }
      button.textContent = "已複製";
      showToast("已複製到剪貼簿");
      setTimeout(() => { button.textContent = "複製指令"; }, 1800);
    } catch {
      showToast("無法自動複製，請手動選取指令");
    }
  });
})();
