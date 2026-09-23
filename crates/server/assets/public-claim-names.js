// sales#335 — names the ISO region codes of the public invoice form (`/p/<locator>`) in the
// customer's own language. The module that minted the claim decides which codes a field offers
// (the core has no country list, hub#1407) and marks the select `data-names="region"`; the names
// come from the browser's `Intl.DisplayNames`. An option the module already labelled keeps its
// label. Without this file (or without `Intl.DisplayNames`) the form still works, with the codes
// as labels.
(function () {
  if (typeof Intl === 'undefined' || !Intl.DisplayNames) return;
  var selects = document.querySelectorAll('select[data-names="region"]');
  if (!selects.length) return;
  var lang = document.documentElement.lang || 'es';
  var names;
  try {
    names = new Intl.DisplayNames([lang], { type: 'region', fallback: 'none' });
  } catch (e) {
    return;
  }
  for (var s = 0; s < selects.length; s++) {
    var select = selects[s];
    // The first option is the default the module chose: it stays first.
    var rest = [];
    for (var i = 1; i < select.options.length; i++) {
      var option = select.options[i];
      if (option.value && option.textContent === option.value) {
        // `of` throws on a value that is not a well-formed region code: that option keeps its
        // value as its label and the others are still named.
        var name;
        try {
          name = names.of(option.value);
        } catch (e) {
          name = undefined;
        }
        if (name) option.textContent = name;
      }
      rest.push(option);
    }
    rest.sort(function (a, b) {
      return a.textContent.localeCompare(b.textContent, lang);
    });
    for (var j = 0; j < rest.length; j++) select.appendChild(rest[j]);
  }
})();
