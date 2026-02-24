let slider; // 전역에 선언

document.addEventListener("DOMContentLoaded", function () {
  slider = document.getElementById("price-slider");
  const minInput = document.getElementById("price-min-input");
  const maxInput = document.getElementById("price-max-input");

  if (slider && minInput && maxInput) {
    const minVal = parseInt(minInput.value) || 0;
    const maxVal = parseInt(maxInput.value) || 500000;

    noUiSlider.create(slider, {
      start: [minVal, maxVal],
      connect: true,
      step: 1000,
      range: {
        min: 0,
        max: 500000
      },
      tooltips: [true, true], // 툴팁 반드시 켜기
      format: {
        to: value => Math.round(value),
        from: value => Number(value)
      }
    });

    const handles = slider.querySelectorAll(".noUi-handle .noUi-tooltip");
    handles.forEach(tip => tip.style.opacity = "0");

    let hideTimeout;

    slider.noUiSlider.on("slide", function () {
      clearTimeout(hideTimeout);
      handles.forEach(tip => tip.style.opacity = "1");
    });

    slider.noUiSlider.on("change", function () {
      clearTimeout(hideTimeout);
      hideTimeout = setTimeout(() => {
        handles.forEach(tip => tip.style.opacity = "0");
      }, 1200);
    });

    slider.noUiSlider.on("update", function (values) {
      minInput.value = values[0];
      maxInput.value = values[1];
    });

    minInput.addEventListener("change", function () {
      slider.noUiSlider.set([this.value, null]);
    });
    maxInput.addEventListener("change", function () {
      slider.noUiSlider.set([null, this.value]);
    });
  }
});

document.addEventListener("DOMContentLoaded", function () {
  const applyBtn = document.getElementById("apply-filters");

  if (applyBtn) {
    applyBtn.addEventListener("click", function () {
      const name = document.getElementById("filter-name")?.value || "";
      const category = document.getElementById("filter-category")?.value || "";
      const [priceMin, priceMax] = slider.noUiSlider.get();
      const video = document.getElementById("filter-video")?.checked ? "true" : "false";

      let baseUrl = applyBtn.dataset.baseurl; // 템플릿에서 전달된 URL 사용
      let url = new URL(baseUrl, window.location.origin);

      url.searchParams.set("name", name);
      url.searchParams.set("category", category);
      url.searchParams.set("price_min", priceMin);
      url.searchParams.set("price_max", priceMax);

      if (document.getElementById("filter-video")) {
        url.searchParams.set("video", video);
      }

      window.location.href = url.toString();
    });
  }
});