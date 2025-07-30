(async () => {
  if (typeof populate_configure_modal === "function") {
    await populate_configure_modal();
  }

  const { generate } = await import("https://unpkg.com/lean-qr@2.5.0?module");
  const random = crypto.getRandomValues(new Uint32Array(1))[0];
  const claimCode = random.toString(16).padStart(8, "0");
  const claimURL = `https://origin-beta.doze.dev?claim_code=${claimCode}`;

  const qr = generate(claimURL);
  const canvas = document.getElementById("claim-qr");
  if (canvas) qr.toCanvas(canvas);

  const link = document.getElementById("claim-link");
  if (link) {
    link.href = claimURL;
    link.textContent = claimURL;
  }
})();
