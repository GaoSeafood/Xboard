(() => {
  const settings = window.settings;
  if (!settings) return;

  const assetsPath = String(settings.assets_path || "/assets").replace(/\/$/, "");
  settings.title = "筋斗云";
  settings.description = "米酒出品 · 翻个跟头，连上就走。";
  settings.logo = `${assetsPath}/brand/jindouyun-mijiu-logo-512.webp`;
  settings.theme = { ...(settings.theme || {}), color: "blue" };
  document.title = settings.title;

  const labelLogo = () => {
    const images = document.querySelectorAll('img[src*="jindouyun-mijiu-logo"]');
    images.forEach((image) => {
      if (!image.hasAttribute("alt") || !image.alt) image.alt = "筋斗云";
    });
    return images.length > 0;
  };

  if (!labelLogo() && "MutationObserver" in window) {
    const observer = new MutationObserver(() => {
      if (labelLogo()) observer.disconnect();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }
})();
