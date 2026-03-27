
(function () {
  const frame = document.getElementById("persistent-frame");
  let currentSignature = "";

  function send(type, extra) {
    const message = { isStreamlitMessage: true, type: type };
    if (extra) {
      Object.keys(extra).forEach(function (key) {
        message[key] = extra[key];
      });
    }
    window.parent.postMessage(message, "*");
  }

  function setFrameHeight(height) {
    send("streamlit:setFrameHeight", { height: height });
  }

  function applyRender(args) {
    const height = Math.max(120, Number((args || {}).height || 0));
    const html = String((args || {}).html || "");
    const signature = String((args || {}).signature || "");
    frame.style.height = height + "px";
    if (signature !== currentSignature) {
      frame.srcdoc = html;
      currentSignature = signature;
    }
    setFrameHeight(height + 8);
  }

  send("streamlit:componentReady", { apiVersion: 1 });
  setFrameHeight(8);

  window.addEventListener("message", function (event) {
    const data = event.data;
    if (!data) {
      return;
    }
    if (data.type === "streamlit:render") {
      applyRender(data.args || {});
      return;
    }
    if (event.source === frame.contentWindow) {
      try {
        window.parent.postMessage(data, "*");
      } catch (err) {
      }
    }
  });
})();
