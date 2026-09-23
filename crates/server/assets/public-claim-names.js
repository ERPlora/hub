// sales#335 — names the countries of the public invoice form (`/p/<locator>`) in the customer's
// own language. The server lists ISO codes only: the names come from the browser's
// `Intl.DisplayNames`, so no country table lives in the hub. Without this file (or without
// `Intl.DisplayNames`) the form still works, with the codes as labels.
(function () {
  var select = document.getElementById('country');
  if (!select || typeof Intl === 'undefined' || !Intl.DisplayNames) return;
  var lang = document.documentElement.lang || 'es';
  var names;
  try {
    names = new Intl.DisplayNames([lang], { type: 'region', fallback: 'none' });
  } catch (e) {
    return;
  }
  // The first option is the home country, already named by the server and pre-selected.
  var rest = [];
  for (var i = 1; i < select.options.length; i++) {
    var option = select.options[i];
    var name = names.of(option.value);
    if (name) option.textContent = name;
    rest.push(option);
  }
  rest.sort(function (a, b) {
    return a.textContent.localeCompare(b.textContent, lang);
  });
  for (var j = 0; j < rest.length; j++) select.appendChild(rest[j]);
})();
