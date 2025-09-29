document.addEventListener("DOMContentLoaded", () => {
  const slides = document.querySelectorAll(".ad-slide");
  let current = 0;

  function updateSlides() {
    slides.forEach((slide, i) => {
      slide.classList.remove("left", "center", "right", "hidden");

      if (i === current) {
        slide.classList.add("center");
      } else if (i === (current - 1 + slides.length) % slides.length) {
        slide.classList.add("left");
      } else if (i === (current + 1) % slides.length) {
        slide.classList.add("right");
      } else {
        slide.classList.add("hidden");
      }
    });
  }

  // 초기 상태
  updateSlides();

  // 오른쪽 이미지 클릭 → 다음으로 이동
  slides.forEach((slide, i) => {
    slide.addEventListener("click", () => {
      if (slide.classList.contains("right")) {
        current = (current + 1) % slides.length;
        updateSlides();
      }
      if (slide.classList.contains("left")) {
        current = (current - 1 + slides.length) % slides.length;
        updateSlides();
      }
    });
  });
});
