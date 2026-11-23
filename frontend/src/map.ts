import { geoNaturalEarth1, geoPath, geoGraticule10 } from 'd3-geo';
import { feature } from 'topojson-client';
import type { FeatureCollection, Geometry } from 'geojson';
import type { GeometryCollection, Topology } from 'topojson-specification';
import atlas from 'world-atlas/countries-110m.json';
import { band } from './data';

interface Place { name: string }

const topology = atlas as unknown as Topology<{ countries: GeometryCollection<Place> }>;
const geography: FeatureCollection<Geometry, Place> = feature(topology, topology.objects.countries);
const project = geoNaturalEarth1().fitExtent([[24, 16], [876, 426]], {
  type: 'FeatureCollection',
  features: geography.features.filter((country) => country.properties.name !== 'Antarctica'),
});
const path = geoPath(project);
export const countryNames = new Map(geography.features
  .filter((country) => country.id != null && country.properties.name !== 'Antarctica')
  .map((country) => [String(country.id), country.properties.name]));
export const countries = [...countryNames].sort((a, b) => a[1].localeCompare(b[1]));

export function drawMap(container: HTMLElement, selected: string, scores: Map<string, number> | null, select: (id: string) => void) {
  const svg = container.querySelector<SVGSVGElement>('svg')!;
  const layer = svg.querySelector<SVGGElement>('g')!;
  const tooltip = container.querySelector<HTMLElement>('.tooltip')!;
  const ns = 'http://www.w3.org/2000/svg';
  const grid = document.createElementNS(ns, 'path');
  grid.setAttribute('d', path(geoGraticule10()) ?? '');
  grid.setAttribute('class', 'graticule');
  layer.append(grid);
  const paths = geography.features.filter((country) => country.properties.name !== 'Antarctica');
  for (const country of paths) {
    const id = String(country.id);
    const score = scores?.get(id);
    const shape = document.createElementNS(ns, 'path');
    shape.setAttribute('d', path(country) ?? '');
    shape.setAttribute('class', 'country ' + (score === undefined ? '' : band(score).toLowerCase()) + (id === selected ? ' selected' : ''));
    if (country.id != null) shape.dataset.country = id;
    const label = country.properties.name + (scores === null ? '' : ' · ' + (score === undefined ? 'Data unavailable' : 'Synthetic score ' + score + '/100'));
    const title = document.createElementNS(ns, 'title');
    title.textContent = label;
    shape.append(title);
    shape.addEventListener('pointermove', (event) => {
      if (event.pointerType === 'touch') return;
      const bounds = svg.getBoundingClientRect();
      tooltip.hidden = false;
      tooltip.textContent = label;
      tooltip.style.left = Math.max(4, Math.min(event.clientX - bounds.left + 12, bounds.width - tooltip.offsetWidth - 4)) + 'px';
      tooltip.style.top = Math.max(4, event.clientY - bounds.top - 34) + 'px';
    });
    shape.addEventListener('pointerleave', () => { tooltip.hidden = true; });
    layer.append(shape);
  }

  let zoom = 1, x = 0, y = 0;
  let drag: { x: number; y: number; pointer: number } | undefined;
  let moved = false;
  let suppressClick = false;
  const transform = () => {
    x = Math.max(900 * (1 - zoom), Math.min(0, x));
    y = Math.max(440 * (1 - zoom), Math.min(0, y));
    layer.setAttribute('transform', 'translate(' + x + ' ' + y + ') scale(' + zoom + ')');
  };
  const changeZoom = (next: number) => {
    next = Math.max(1, Math.min(6, next));
    x = 450 - (450 - x) * next / zoom;
    y = 220 - (220 - y) * next / zoom;
    zoom = next;
    transform();
  };
  container.querySelector('[data-map="in"]')!.addEventListener('click', () => changeZoom(zoom * 1.4));
  container.querySelector('[data-map="out"]')!.addEventListener('click', () => changeZoom(zoom / 1.4));
  container.querySelector('[data-map="reset"]')!.addEventListener('click', () => changeZoom(1));
  svg.addEventListener('click', (event) => {
    if (suppressClick) { suppressClick = false; return; }
    const id = (event.target as SVGElement).closest<SVGPathElement>('[data-country]')?.dataset.country;
    if (id) select(id);
  });
  svg.addEventListener('pointerdown', (event) => {
    if (event.button !== 0 || drag) return;
    drag = { x: event.clientX, y: event.clientY, pointer: event.pointerId };
    moved = false;
    suppressClick = false;
  });
  svg.addEventListener('pointermove', (event) => {
    if (!drag || drag.pointer !== event.pointerId) return;
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    if (!moved && Math.hypot(dx, dy) < 4) return;
    moved = true;
    svg.setPointerCapture(event.pointerId);
    const scale = Math.min(svg.clientWidth / 900, svg.clientHeight / 440);
    x += dx / scale;
    y += dy / scale;
    drag.x = event.clientX;
    drag.y = event.clientY;
    transform();
    tooltip.hidden = true;
  });
  const endDrag = (event: PointerEvent) => {
    if (drag?.pointer !== event.pointerId) return;
    suppressClick = moved;
    drag = undefined;
  };
  svg.addEventListener('pointerup', endDrag);
  svg.addEventListener('pointercancel', endDrag);
  svg.addEventListener('pointerleave', (event) => { if (!moved) endDrag(event); });
  svg.addEventListener('keydown', (event) => {
    const vectors: Record<string, [number, number]> = { ArrowUp: [0, 40], ArrowDown: [0, -40], ArrowLeft: [40, 0], ArrowRight: [-40, 0] };
    const vector = vectors[event.key];
    if (!vector) return;
    event.preventDefault();
    x += vector[0];
    y += vector[1];
    transform();
  });
  return (id: string) => {
    layer.querySelector('.selected')?.classList.remove('selected');
    layer.querySelector('[data-country="' + CSS.escape(id) + '"]')?.classList.add('selected');
  };
}
