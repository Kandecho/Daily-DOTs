(function () {
  // 明暗：首页和日报共用一个键，在哪一页切换，别的页面下次打开都跟着变。点报头切换。
  var root = document.documentElement, KEY = "newsfmt-theme";
  try { var t = localStorage.getItem(KEY); if (t) root.dataset.theme = t; } catch (e) {}
  function dark() {
    return root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function label() {
    var btn = document.getElementById("theme");
    if (btn) btn.setAttribute("aria-label", dark() ? "切换到亮色" : "切换到暗色");
  }
  function apply(next) {
    root.dataset.theme = next;
    try { localStorage.setItem(KEY, next); } catch (e) {}
    label();
  }
  function toggle() {
    var next = dark() ? "light" : "dark";
    var still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (still || !document.startViewTransition) {
      if (!still) {
        root.classList.add("theme-fade");
        setTimeout(function () { root.classList.remove("theme-fade"); }, 700);
      }
      apply(next);
      return;
    }
    // 夜色从左往右跟着太阳铺开；回到白天时从右往左跟着月亮铺回。
    var vt = document.startViewTransition(function () { apply(next); });
    vt.ready.then(function () {
      root.animate(
        { clipPath: next === "dark" ? ["inset(0 100% 0 0)", "inset(0 0 0 0)"] : ["inset(0 0 0 100%)", "inset(0 0 0 0)"] },
        { duration: 1000, easing: "cubic-bezier(.65, 0, .35, 1)", pseudoElement: "::view-transition-new(root)" });
    }).catch(function () {});
  }
  document.addEventListener("DOMContentLoaded", function () {
    label();
    // 首帧不播动画：页面画好之后再打开过渡。
    requestAnimationFrame(function () { requestAnimationFrame(function () { root.classList.add("ready"); }); });
  });
  document.addEventListener("click", function (e) {
    if (e.target.closest && e.target.closest(".mast")) toggle();
  });
})();
