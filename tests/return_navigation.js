// No browser is launched: exercise only the template's click-handler contract.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../tools/flip.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const listeners = {};
const pages = Array.from({ length: 7 }, () => ({ scrollTop: 80, classList: { contains: () => false } }));
const deck = { children: pages, clientWidth: 390, scrollLeft: 0, addEventListener() {},
  scrollTo({ left }) { this.scrollLeft = left; } };
vm.runInNewContext(script, {
  document: {
    documentElement: { dataset: {} }, body: { classList: { toggle() {} } },
    getElementById: id => id === 'deck' ? deck : { addEventListener() {} },
    addEventListener: (name, callback) => { listeners[name] = callback; }
  },
  localStorage: { getItem() {}, setItem() {} }, matchMedia: () => ({ matches: false }),
  addEventListener() {}, location: { hash: '' }, requestAnimationFrame: callback => callback()
});
function click(id, href) {
  let prevented = false;
  listeners.click({ target: { closest: () => ({ id, getAttribute: () => href }) },
    preventDefault() { prevented = true; } });
  return prevented;
}
assert.equal(click('', '#p3'), true, 'ordinary contents links retain enhanced navigation');
assert.equal(deck.scrollLeft, 1170);
for (let i = 0; i < 2; i++) {
  assert.equal(click('to-toc', '#p0'), false, 'return link must keep its native anchor default');
  assert.equal(pages[0].scrollTop, 0, 'returning resets the contents page scroll position');
}
delete deck.scrollTo;
assert.equal(click('to-toc', '#p0'), false, 'return link must not depend on scrollTo');
console.log('Native return anchor preserved; enhanced contents navigation retained.');
