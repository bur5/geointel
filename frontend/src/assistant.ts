// Site assistant: a chat that answers questions about the figures on the site. The page sends
// a compact summary of the selected country; the server (Cloudflare Worker) holds the key.
import type { Lang } from './data';

export const ASSISTANT_URL = 'https://geointel-assistant.futureshsoutreach.workers.dev';

interface Turn { role: 'user' | 'assistant'; text: string }
const history: Turn[] = [];
let busy = false;

const T = {
  ru: {
    title: 'Спросить ИИ-помощника',
    lead: 'Помощник объясняет цифры сайта простыми словами и отвечает на вопросы о выбранной стране. Он видит только данные сайта: если данных нет, он так и скажет.',
    placeholder: 'Например: что значит 12% за год? Безопасно ли ехать в мае?',
    send: 'Спросить', thinking: 'Думаю…', clear: 'Новый разговор',
    about: (c: string) => `Контекст: ${c}`,
    suggestions: ['Что значит уровень опасности этой страны?', 'Где в стране опаснее всего?', 'Что будет через 5 лет?', 'Можно ли сюда переехать на год?'],
    note: 'Ответы — не юридический и не медицинский совет. Перед поездкой сверяйтесь с рекомендациями МИД.',
    fail: 'Не удалось получить ответ. Попробуйте ещё раз позже.',
  },
  en: {
    title: 'Ask the AI assistant',
    lead: 'The assistant explains the figures in plain words and answers questions about the selected country. It sees only the site data and says so when data is missing.',
    placeholder: 'For example: what does 12% a year mean? Is it safe to travel in May?',
    send: 'Ask', thinking: 'Thinking…', clear: 'New conversation',
    about: (c: string) => `Context: ${c}`,
    suggestions: ['What does this danger level mean?', 'Where in the country is it most dangerous?', 'What about 5 years from now?', 'Could I move here for a year?'],
    note: 'Answers are not legal or medical advice. Check foreign-ministry advice before travelling.',
    fail: 'Could not get an answer. Please try again later.',
  },
};

export function assistantPanel(lang: Lang, countryLabel: string, esc: (s: string) => string, compact = false) {
  const t = T[lang];
  const log = history.map((h) => `<div class="chat-msg ${h.role}">${h.role === 'assistant' ? formatAnswer(h.text, esc) : esc(h.text)}</div>`).join('');
  return `<section class="assistant${compact ? ' compact' : ''}" id="assistant">
    <div class="section-head"><h2>${t.title}</h2>${compact ? '' : `<p>${t.lead}</p>`}</div>
    <p class="muted-text small">${esc(t.about(countryLabel))}</p>
    <div class="chat-log" aria-live="polite">${log}</div>
    ${history.length ? '' : `<div class="chat-suggest">${t.suggestions.map((s) => `<button type="button" data-ask="${esc(s)}">${esc(s)}</button>`).join('')}</div>`}
    <form class="chat-form" data-chat><textarea name="q" rows="2" maxlength="800" placeholder="${esc(t.placeholder)}" required></textarea>
      <div class="chat-actions"><button type="submit" class="button">${t.send}</button>${history.length ? `<button type="button" class="link-button" data-chat-clear>${t.clear}</button>` : ''}</div></form>
    <p class="muted-text small">${t.note}</p></section>`;
}

function formatAnswer(text: string, esc: (s: string) => string) {
  return esc(text).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').split(/\n{2,}/).map((p) => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('');
}

export function clearChat() { history.length = 0; }

export async function ask(question: string, lang: Lang, context: unknown, rerender: () => void) {
  if (busy || !question.trim()) return;
  busy = true;
  history.push({ role: 'user', text: question.trim() });
  history.push({ role: 'assistant', text: T[lang].thinking });
  rerender();
  try {
    const response = await fetch(ASSISTANT_URL, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, lang, context, history: history.slice(0, -2).slice(-6) }),
    });
    const data = await response.json() as { answer?: string };
    history[history.length - 1] = { role: 'assistant', text: data.answer || T[lang].fail };
  } catch {
    history[history.length - 1] = { role: 'assistant', text: T[lang].fail };
  } finally {
    busy = false;
    rerender();
  }
}
