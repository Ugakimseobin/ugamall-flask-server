// UGAMALL custom scripts
document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("search-input");
  const suggestionsBox = document.getElementById("suggestions");

  if (input) {
    input.addEventListener("input", async () => {
      const query = input.value;
      if (query.length < 1) {
        suggestionsBox.innerHTML = "";
        suggestionsBox.classList.add("hidden");
        return;
      }
      const res = await fetch(`/autocomplete?q=${query}`);
      const suggestions = await res.json();
      
      if (suggestions.length > 0) {
        suggestionsBox.innerHTML = suggestions.map(s => `<div class="p-2 hover:bg-gray-100 cursor-pointer">${s}</div>`).join("");
        suggestionsBox.classList.remove("hidden");

        // 클릭 시 입력창에 반영
        suggestionsBox.querySelectorAll("div").forEach(div => {
          div.addEventListener("click", () => {
            input.value = div.textContent;
            suggestionsBox.innerHTML = "";
            suggestionsBox.classList.add("hidden");
          });
        });
      } else {
        suggestionsBox.innerHTML = "";
        suggestionsBox.classList.add("hidden");
      }
    });
  }
});

