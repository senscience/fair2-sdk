// The search box of the dataset card: filters its record sets, fields and other files.
// Inlined in the card by the template, with CARD_ID defined before it. The script creates the box:
// where it doesn't run (GitHub, untrusted notebooks, which also drop `hidden` attributes), the card
// has no box that would do nothing, and shows everything.
(() => {
  const card = document.getElementById(CARD_ID);
  const sections = card ? [...card.querySelectorAll("details[data-fair2-section]")] : [];
  if (!sections.length) return;
  const box = document.createElement("div");
  box.className = "fair2-search";
  box.innerHTML = `<label>Search</label><input type="search" placeholder="Record sets, fields and files">
    <button type="button" class="fair2-search-clear" hidden>Clear</button>
    <span class="fair2-search-count" aria-live="polite"></span>`;
  const input = box.querySelector("input");
  input.id = `${CARD_ID}-search`;
  box.querySelector("label").htmlFor = input.id;
  const count = box.querySelector(".fair2-search-count");
  const clear = box.querySelector(".fair2-search-clear");
  // Above the record sets.
  sections[0].before(box);
  const groups = [...card.querySelectorAll("details[data-fair2-group]")];
  // Case and accents don't matter: "duracion" finds "Duración".
  const fold = (text) => text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  // What was open before searching, restored when the search is cleared.
  let opened = null;

  const search = () => {
    const query = fold(input.value.trim());
    clear.hidden = !input.value;
    if (query && !opened) opened = [...sections, ...groups].map((d) => [d, d.open]);
    let recordSets = 0, fields = 0, files = 0;

    for (const row of card.querySelectorAll("tr[data-fair2-row]")) {
      const match = !query || fold(row.textContent).includes(query);
      row.hidden = !match;
      if (match && query) row.dataset.fair2Row === "record-set" ? recordSets++ : files++;
    }
    // The fields of a record set: all of them when its name or description matches.
    for (const group of groups) {
      const own = query && fold(group.dataset.fair2Text).includes(query);
      let matches = 0;
      for (const row of group.querySelectorAll("tr[data-fair2-field]")) {
        const match = !query || own || fold(row.textContent).includes(query);
        row.hidden = !match;
        if (match) matches++;
      }
      group.hidden = Boolean(query) && matches === 0;
      if (query) {
        group.open = matches > 0;
        fields += matches;
      }
    }

    if (query) {
      // Unfold the sections with a match, fold the others.
      for (const section of sections) {
        section.open = Boolean(
          section.querySelector("tr[data-fair2-row]:not([hidden]), details[data-fair2-group]:not([hidden])"),
        );
      }
      count.textContent = `${plural(recordSets, "record set")}, ${plural(fields, "field")}, ${plural(files, "other file")}`;
    } else {
      for (const [details, open] of opened ?? []) details.open = open;
      opened = null;
      count.textContent = "";
    }
  };
  // Clearing (the button, or Escape in the box) shows the card as it was before the search.
  const reset = () => {
    input.value = "";
    search();
    input.focus();
  };
  input.addEventListener("input", search);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && input.value) {
      event.preventDefault();
      reset();
    }
  });
  clear.addEventListener("click", reset);
})();
