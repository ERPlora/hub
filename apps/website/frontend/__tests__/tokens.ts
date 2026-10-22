// HTML as tokens, as the server's tests read it (tests/test_render.py): `<tag a="…">` with its attributes sorted,
// `</tag>`, and each text with its spaces collapsed. Two pieces of markup that give the same tokens are the same page.
const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr']);

export function tokens(nodes: Iterable<Node>): string[] {
  const box = document.createElement('div');
  box.append(...[...nodes].map((node) => node.cloneNode(true)));
  box.normalize();
  const out: string[] = [];
  const walk = (node: Node): void => {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = (node.textContent ?? '').split(/\s+/).filter(Boolean).join(' ');
      if (text) out.push(text);
      return;
    }
    if (!(node instanceof Element)) return;
    const tag = node.tagName.toLowerCase();
    const attributes = [...node.attributes]
      .map((attribute) => `${attribute.name}="${attribute.value}"`)
      .sort((a, b) => a.localeCompare(b));
    out.push(`<${[tag, ...attributes].join(' ')}>`);
    node.childNodes.forEach(walk);
    if (!VOID.has(tag)) out.push(`</${tag}>`);
  };
  box.childNodes.forEach(walk);
  return out;
}

/** The nodes `html` parses to. */
export function fragment(html: string): Node[] {
  const box = document.createElement('div');
  box.innerHTML = html;
  return [...box.childNodes];
}
