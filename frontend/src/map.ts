import { geoMercator, geoNaturalEarth1, geoPath, geoGraticule10 } from 'd3-geo';
import { feature } from 'topojson-client';
import type { FeatureCollection, Geometry } from 'geojson';
import type { GeometryCollection, Topology } from 'topojson-specification';
import atlas from 'world-atlas/countries-110m.json';

interface Place { name: string }

const topology = atlas as unknown as Topology<{ countries: GeometryCollection<Place> }>;
const geography: FeatureCollection<Geometry, Place> = feature(topology, topology.objects.countries);
const project = geoNaturalEarth1().fitExtent([[24, 16], [876, 426]], {
  type: 'FeatureCollection',
  features: geography.features.filter((country) => country.properties.name !== 'Antarctica'),
});
const path = geoPath(project);
// Map shape key: ISO numeric id, or the shape name when the atlas has no id (e.g. Kosovo).
const shapeKey = (country: { id?: string | number; properties: Place }) =>
  country.id != null ? String(country.id) : 'name:' + country.properties.name;
export const shapeNames = new Map(geography.features
  .filter((country) => country.properties.name !== 'Antarctica')
  .map((country) => [shapeKey(country), country.properties.name]));

export function drawMap(
  container: HTMLElement,
  selected: string,
  classOf: (key: string) => string,
  labelOf: (key: string, name: string) => string,
  select: (key: string) => void,
) {
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
    const id = shapeKey(country);
    const shape = document.createElementNS(ns, 'path');
    shape.setAttribute('d', path(country) ?? '');
    shape.setAttribute('class', 'country ' + classOf(id) + (id === selected ? ' selected' : ''));
    shape.dataset.country = id;
    const label = labelOf(id, country.properties.name);
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

export interface MapPoint { lat: number; lon: number; cls: string; title: string }

/** Zoomed map of one country with event locations; returns false if the shape is unknown. */
export function drawCountryMap(svg: SVGSVGElement, key: string, points: MapPoint[]): boolean {
  const target = geography.features.find((country) => shapeKey(country) === key);
  if (!target) return false;
  const ns = 'http://www.w3.org/2000/svg';
  const extent = {
    type: 'FeatureCollection',
    features: [target, ...(points.length ? [{
      type: 'Feature', properties: {}, geometry: { type: 'MultiPoint', coordinates: points.map((p) => [p.lon, p.lat]) },
    }] : [])],
  };
  type Extent = Parameters<ReturnType<typeof geoMercator>['fitExtent']>[1];
  const projection = geoMercator().fitExtent([[16, 16], [584, 324]], extent as unknown as Extent);
  const draw = geoPath(projection);
  svg.replaceChildren();
  for (const country of geography.features) {
    const shape = document.createElementNS(ns, 'path');
    shape.setAttribute('d', draw(country) ?? '');
    shape.setAttribute('class', shapeKey(country) === key ? 'cm-target' : 'cm-land');
    svg.append(shape);
  }
  for (const point of points) {
    const xy = projection([point.lon, point.lat]);
    if (!xy) continue;
    const dot = document.createElementNS(ns, 'circle');
    dot.setAttribute('cx', String(xy[0]));
    dot.setAttribute('cy', String(xy[1]));
    dot.setAttribute('r', point.cls.includes('red') ? '6' : '4.5');
    dot.setAttribute('class', 'cm-point ' + point.cls);
    const title = document.createElementNS(ns, 'title');
    title.textContent = point.title;
    dot.append(title);
    svg.append(dot);
  }
  return true;
}
