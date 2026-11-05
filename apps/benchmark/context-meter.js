const categories = [
  ['Chat',108.6,'#1bb3ca'], ['Files',46.1,'#3b7df4'], ['Tools',12.8,'#925cf3'],
  ['System',4.2,'#eb4c90'], ['Memory',3.9,'#26c979']
];
const compact = document.querySelector('#compact');
const amount = document.querySelector('#amount');
const legend = document.querySelector('#legend');
const bar = document.querySelector('#bar');
let compacted = false;
let highlighted = -1;
let animation;
let current = 175.6;
function values() {
  return categories.map((entry,i) => compacted && i === 0 ? 30.4 : entry[1]);
}
function render(index) {
  highlighted = index;
  const used = values();
  const total = used.reduce((sum,value) => sum + value,0);
  const target = index < 0 ? total : used[index];
  const start = current;
  const began = performance.now();
  cancelAnimationFrame(animation);
  function tick(now) {
    const t = matchMedia('(prefers-reduced-motion: reduce)').matches ? 1 : Math.min(1,(now-began)/300);
    current = start + (target-start)*(1-(1-t)**3);
    amount.textContent = current.toFixed(1)+'K';
    if(t<1) animation = requestAnimationFrame(tick);
  }
  tick(began);
  document.querySelector('#unit').textContent = index < 0 ? 'of 200K' : categories[index][0];
  [...used,200-total].forEach((value,i) => {
    bar.children[i].style.flex = value+' 1 0px';
    bar.children[i].style.opacity = index < 0 || index === i ? 1 : 0.2;
  });
}
for(const [i,[label,,color]] of categories.entries()) {
  const chip = document.createElement('button');
  chip.style.setProperty('--color',color);
  chip.append(document.createElement('i'),label);
  legend.append(chip);
  const segment = document.createElement('span');
  segment.style.setProperty('--color',color);
  bar.append(segment);
  for(const node of [segment,chip]){
    node.addEventListener('pointerenter',()=>render(i));
    node.addEventListener('pointerleave',()=>render(-1));
  }
  chip.addEventListener('focus',()=>render(i));
  chip.addEventListener('blur',()=>render(-1));
}
const free = document.createElement('span');
free.style.setProperty('--color','#373737');
bar.append(free);
compact.addEventListener('click',()=>{
  compacted = !compacted;
  compact.textContent = compacted ? 'Undo' : 'Compact';
  compact.setAttribute('aria-pressed',String(compacted));
  render(highlighted);
});
render(-1);
