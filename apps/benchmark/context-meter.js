const categories = [
  {name:'Chat', tokens:108.6, color:'#53afc8'},
  {name:'Files', tokens:46.1, color:'#4b7aeb'},
  {name:'Tools', tokens:12.8, color:'#8f5eed'},
  {name:'System', tokens:4.2, color:'#d75686'},
  {name:'Memory', tokens:3.9, color:'#60c680'}
];
const amount = document.querySelector('#amount');
const unit = document.querySelector('#unit');
const compact = document.querySelector('#compact');
const legend = document.querySelector('#legend');
const bar = document.querySelector('#bar');
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
let previous = '';
let selected = null;
let compacted = false;

function showNumber(value) {
  const next = value.toFixed(1) + 'K';
  if (next === previous) return;
  const old = previous.padStart(next.length);
  amount.replaceChildren();
  Array.from(next).forEach((digit,index) => {
    const slot = document.createElement('span');
    slot.className = 'slot';
    const incoming = document.createElement('span');
    incoming.textContent = digit;
    slot.append(incoming);
    amount.append(slot);
    if (!previous || digit === old[index] || reducedMotion.matches) return;
    const outgoing = document.createElement('span');
    outgoing.textContent = old[index];
    slot.append(outgoing);
    const options = {duration:260 + index * 15, easing:'cubic-bezier(.2,.65,.3,1)'};
    incoming.animate([{transform:'translateY(70%)',opacity:.15,filter:'blur(2px)'},{transform:'none',opacity:1,filter:'none'}],options);
    outgoing.animate([{transform:'none',opacity:1},{transform:'translateY(-70%)',opacity:0,filter:'blur(2px)'}],options).onfinish = () => outgoing.remove();
  });
  previous = next;
}
function render() {
  const sizes = categories.map(c => compacted && c.name === 'Chat' ? 30.4 : c.tokens);
  const total = sizes.reduce((a,b) => a+b,0);
  const value = selected === null ? total : sizes[selected];
  const label = selected === null ? 'of 200K' : categories[selected].name;
  showNumber(value);
  unit.textContent = label;
  document.querySelector('#accessible-reading').value = value.toFixed(1)+'K '+label;
  [...sizes,200-total].forEach((size,i) => {
    bar.children[i].style.flex = size+' 1 0px';
    bar.children[i].style.opacity = selected === null || selected === i ? 1 : .22;
    legend.children[i]?.classList.toggle('active',selected === i);
  });
}
function select(index) { selected = index; render(); }
for (const [index,c] of categories.entries()) {
  const chip = document.createElement('button');
  chip.className = 'chip';
  chip.append(document.createElement('i'),c.name);
  legend.append(chip);
  const segment = document.createElement('div');
  segment.className = 'segment';
  bar.append(segment);
  for (const node of [chip,segment]) {
    node.style.setProperty('--ink',c.color);
    node.addEventListener('pointerenter',() => select(index));
    node.addEventListener('pointerleave',() => select(null));
  }
  chip.addEventListener('focus',() => select(index));
  chip.addEventListener('blur',() => select(null));
}
const remaining = document.createElement('div');
remaining.className = 'segment';
remaining.style.setProperty('--ink','#353535');
bar.append(remaining);
compact.addEventListener('click',() => {
  compacted = !compacted;
  compact.setAttribute('aria-pressed',String(compacted));
  compact.textContent = compacted ? 'Undo' : 'Compact';
  select(null);
});
render();
