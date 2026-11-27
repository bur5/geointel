// Interface building blocks: themes, country search, the event picker and pinned countries.
import type { Lang } from './data';

export type Theme = 'light' | 'dark' | 'newyear';
const THEMES: Theme[] = ['light', 'dark', 'newyear'];
const safeGet = (k: string) => { try { return localStorage.getItem(k); } catch { return null; } };
const safeSet = (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } };

export function currentTheme(): Theme {
  const saved = safeGet('geointel.theme') as Theme | null;
  if (saved && THEMES.includes(saved)) return saved;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta) meta.content = theme === 'light' ? '#f3f5f7' : theme === 'dark' ? '#0e141b' : '#0b1426';
}

export function nextTheme(theme: Theme): Theme {
  const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
  safeSet('geointel.theme', next);
  return next;
}

const THEME_LABEL = {
  ru: { light: 'Светлая тема', dark: 'Тёмная тема', newyear: 'Новогодняя тема' },
  en: { light: 'Light theme', dark: 'Dark theme', newyear: 'New Year theme' },
};
const ICON: Record<Theme, string> = {
  light: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/></svg>',
  dark: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/></svg>',
  newyear: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2v20M3.3 7l17.4 10M3.3 17L20.7 7M9.5 3.8 12 6l2.5-2.2M9.5 20.2 12 18l2.5 2.2"/></svg>',
};

export function themeButton(theme: Theme, lang: Lang) {
  const label = THEME_LABEL[lang][theme];
  return `<button type="button" class="icon-button" data-theme-cycle title="${label}" aria-label="${label}">${ICON[theme]}</button>`;
}

// ------------------------------------------------------------------ country search
export interface SearchItem { iso3: string; name: string; level?: number }

export function searchBox(lang: Lang) {
  const ph = lang === 'ru' ? 'Найти страну' : 'Find a country';
  return `<div class="search">
    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>
    <input id="country-search" type="search" autocomplete="off" spellcheck="false" placeholder="${ph}" aria-label="${ph}"
      role="combobox" aria-expanded="false" aria-controls="search-list" aria-autocomplete="list">
    <ul id="search-list" class="search-list" role="listbox" hidden></ul></div>`;
}

export function wireSearch(root: HTMLElement, items: () => SearchItem[], pick: (iso3: string) => void, lang: Lang) {
  const input = root.querySelector<HTMLInputElement>('#country-search');
  const list = root.querySelector<HTMLUListElement>('#search-list');
  if (!input || !list) return;
  let active = 0;
  let found: SearchItem[] = [];
  const norm = (s: string) => s.toLowerCase().replace(/ё/g, 'е');
  const show = () => {
    const q = norm(input.value.trim());
    found = q ? items().filter((i) => norm(i.name).includes(q) || i.iso3.toLowerCase() === q)
      .sort((a, b) => Number(!norm(a.name).startsWith(q)) - Number(!norm(b.name).startsWith(q))).slice(0, 8) : [];
    active = 0;
    list.innerHTML = found.length ? found.map((i, n) => `<li role="option" id="opt-${i.iso3}" data-pick-country="${i.iso3}" aria-selected="${n === active}">
      <span>${i.name.replace(/[&<>"]/g, '')}</span>${i.level ? `<i class="dot d-${i.level}" aria-hidden="true"></i>` : ''}</li>`).join('')
      : q ? `<li class="empty">${lang === 'ru' ? 'Ничего не найдено' : 'Nothing found'}</li>` : '';
    list.hidden = !q;
    input.setAttribute('aria-expanded', String(!list.hidden));
  };
  const mark = () => list.querySelectorAll('[role=option]').forEach((el, n) => el.setAttribute('aria-selected', String(n === active)));
  input.addEventListener('input', show);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { active = Math.min(active + 1, found.length - 1); mark(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { active = Math.max(active - 1, 0); mark(); e.preventDefault(); }
    else if (e.key === 'Enter' && found[active]) { e.preventDefault(); pick(found[active].iso3); }
    else if (e.key === 'Escape') { input.value = ''; show(); }
  });
  list.addEventListener('mousedown', (e) => {
    const iso = (e.target as HTMLElement).closest<HTMLElement>('[data-pick-country]')?.dataset.pickCountry;
    if (iso) { e.preventDefault(); pick(iso); }
  });
  input.addEventListener('blur', () => setTimeout(() => { list.hidden = true; input.setAttribute('aria-expanded', 'false'); }, 120));
}

// ------------------------------------------------------------------ event picker
export interface PickItem { key: string; label: string; disabled?: boolean; note?: string }
export interface PickGroup { label: string; items: PickItem[] }

export function picker(caption: string, current: string, groups: PickGroup[]) {
  const all = groups.flatMap((g) => g.items);
  const selected = all.find((i) => i.key === current);
  return `<div class="picker">
    <span class="picker-caption">${caption}</span>
    <button type="button" class="picker-button" data-picker-toggle aria-haspopup="true" aria-expanded="false">
      <span>${selected?.label ?? ''}</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button>
    <div class="picker-panel" hidden>${groups.map((g) => `<div class="picker-group"><p>${g.label}</p><div class="picker-items">${g.items.map((i) =>
      `<button type="button" data-pick="${i.key}"${i.key === current ? ' aria-current="true"' : ''}${i.disabled ? ' disabled' : ''}>${i.label}${i.note ? `<small>${i.note}</small>` : ''}</button>`).join('')}</div></div>`).join('')}</div>
  </div>`;
}

export function togglePicker(root: HTMLElement, open?: boolean) {
  const panel = root.querySelector<HTMLElement>('.picker-panel');
  const button = root.querySelector<HTMLElement>('[data-picker-toggle]');
  if (!panel || !button) return;
  const show = open ?? panel.hidden;
  panel.hidden = !show;
  button.setAttribute('aria-expanded', String(show));
  if (show) panel.querySelector<HTMLElement>('[aria-current="true"], button:not([disabled])')?.focus();
}

// ------------------------------------------------------------------ pinned countries
export function pins(): string[] {
  try { return JSON.parse(safeGet('geointel.pins') ?? '[]') as string[]; } catch { return []; }
}
export function togglePin(iso3: string): boolean {
  const list = pins();
  const on = !list.includes(iso3);
  safeSet('geointel.pins', JSON.stringify(on ? [...list, iso3].slice(-12) : list.filter((x) => x !== iso3)));
  return on;
}
