(() => {
  const settings = window.settings;
  if (!settings) return;

  const assetsPath = String(settings.assets_path || "/assets").replace(/\/$/, "");
  settings.title = "筋斗云";
  settings.description = settings.title;
  settings.logo = `${assetsPath}/brand/jindouyun-mijiu-logo-512.webp`;
  settings.theme = { ...(settings.theme || {}), color: "blue" };
  document.title = settings.title;

  const labelLogo = () => {
    const images = document.querySelectorAll('img[src*="jindouyun-mijiu-logo"]');
    images.forEach((image) => {
      if (!image.hasAttribute("alt") || !image.alt) image.alt = "筋斗云";
    });

    const loginImage = Array.from(images).find((image) => !image.closest(".n-layout-sider"));
    if (loginImage) {
      const logo = loginImage.parentElement;
      logo?.classList.add("jindouyun-login-logo");
      const title = logo?.nextElementSibling;
      if (title?.tagName === "H5") {
        title.classList.add("jindouyun-login-title");
      }
    }

    return Boolean(loginImage);
  };

  if (!labelLogo() && "MutationObserver" in window) {
    const observer = new MutationObserver(() => {
      if (labelLogo()) observer.disconnect();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }
})();
