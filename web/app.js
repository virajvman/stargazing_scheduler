/* Stargazing Scheduler --- browser front end.
 *
 * All the astronomy and all the scheduling happen in Python: this file loads
 * Pyodide, hands code.py the config from the form, and renders what comes back.
 * That is the whole point --- the notebook and this page run the same code.py,
 * so there is no second implementation to keep in step.
 */

'use strict';

const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.28.3/full/';

const el = (id) => document.getElementById(id);

const state = {
  pyodide: null,
  models: [],
  classes: [],
  counts: {},
  groupSettings: {},
  lastResult: null,
};

/* The two ways visitors move through the observatory. Defaults come straight
   from the reasoning in target_lists.py: both groups stay varied within
   themselves, the portables because visitors see them all at once, the domes
   because the 24-inch and the 0.7 m are good at different things. */
const GROUPS = [
  { name: 'Dome telescopes', kind: 'dome', coupling: 'diverse' },
  { name: 'Portable telescopes', kind: 'portable', coupling: 'diverse' },
];

const COUPLING_LABELS = {
  match: 'matched',
  diverse: 'varied',
  none: 'independent',
};

const COUPLING_OPTIONS = {
  diverse: 'Varied — different categories at once',
  match: 'Matched — same category at once',
  none: 'Independent',
};

/* ---------------------------------------------------------------- utilities */

function setStatus(text) {
  el('status').textContent = text || '';
}

function showError(message) {
  const node = el('error-message');
  node.textContent = message;
  node.hidden = false;
}

function clearError() {
  el('error-message').hidden = true;
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/* Tonight, or still "last night" if it is the small hours. */
function defaultDate() {
  const now = new Date();
  if (now.getHours() < 6) now.setDate(now.getDate() - 1);
  const pad = (n) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function catDot(cls) {
  const dot = document.createElement('span');
  dot.className = `cat cat-${cls}`;
  return dot;
}

function cell(text, cls) {
  const td = document.createElement('td');
  if (cls) td.className = cls;
  td.textContent = text;
  return td;
}

/* ------------------------------------------------------------ python set-up */

async function bootPython() {
  setStatus('Fetching Python and astropy (once, then cached)…');

  state.pyodide = await loadPyodide({ indexURL: PYODIDE_URL });
  await state.pyodide.loadPackage(['numpy', 'pandas', 'astropy', 'pytz']);

  setStatus('Starting the scheduler…');

  // cache-bust so an edited code.py is picked up rather than served stale
  const stamp = `?v=${Date.now()}`;
  const [codePy, targetsPy, bridgePy, catalogText] = await Promise.all([
    fetch('code.py' + stamp).then((r) => r.text()),
    fetch('target_lists.py' + stamp).then((r) => r.text()),
    fetch('web/bridge.py' + stamp).then((r) => r.text()),
    fetch('web/catalog.json' + stamp).then((r) => r.text()),
  ]);

  const fs = state.pyodide.FS;
  fs.writeFile('/home/pyodide/code.py', codePy);
  fs.writeFile('/home/pyodide/target_lists.py', targetsPy);
  fs.writeFile('/home/pyodide/bridge.py', bridgePy);
  fs.writeFile('/home/pyodide/catalog.json', catalogText);

  await state.pyodide.runPythonAsync(`
import importlib.util, json, sys

# Keep astropy offline. Its bundled IERS tables are far more precise than
# altitude scheduling needs, and there is no network in here anyway.
from astropy.utils.iers import conf as _iers_conf
_iers_conf.auto_download = False
_iers_conf.auto_max_age = None
from astropy.coordinates import solar_system_ephemeris
solar_system_ephemeris.set('builtin')

# code.py shadows the standard library's "code" module, so append rather than
# insert (target_lists is ours either way) and load it under its own name.
sys.path.append('/home/pyodide')

_spec = importlib.util.spec_from_file_location('stargazing', '/home/pyodide/code.py')
stargazing = importlib.util.module_from_spec(_spec)
sys.modules['stargazing'] = stargazing
_spec.loader.exec_module(stargazing)

import bridge

with open('/home/pyodide/catalog.json') as _f:
    _catalog = json.load(_f)
stargazing.register_coordinates(_catalog['objects'])
_catalog_generated = _catalog.get('generated', '')
`);

  const info = JSON.parse(state.pyodide.runPython('json.dumps(bridge.describe_models())'));
  state.models = info.models;
  state.classes = info.classes;

  const generated = state.pyodide.runPython('_catalog_generated');
  if (generated) {
    el('catalog-stamp').textContent = `Coordinates ${generated}`;
  }
}

/* --------------------------------------------------------------- form build */

function resetToDefaults() {
  state.counts = {};
  for (const m of state.models) state.counts[m.model] = m.default_count;
  state.groupSettings = {};
  for (const g of GROUPS) {
    // null = let the scheduler recommend a count from the window and the sky
    state.groupSettings[g.name] = { coupling: g.coupling, num_slots: null };
  }
  renderTelescopes();
  renderGroups();
}

function renderTelescopes() {
  const host = el('telescope-list');
  host.textContent = '';

  for (const m of state.models) {
    const n = state.counts[m.model] ?? 0;

    const chip = document.createElement('div');
    chip.className = 'scope' + (n === 0 ? ' is-off' : '');
    chip.title = `${m.total_targets} targets in its list`;

    const name = document.createElement('span');
    name.className = 'scope-name';
    name.textContent = m.display;
    chip.append(name);

    if (m.max_altitude !== null) {
      const cap = document.createElement('span');
      cap.className = 'cap';
      cap.textContent = `≤${m.max_altitude}°`;
      cap.title = 'Kept away from the zenith, where this mount tracks poorly';
      chip.append(cap);
    }

    const stepper = document.createElement('div');
    stepper.className = 'stepper';

    const step = (delta, symbol, disabled, label) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = symbol;
      b.disabled = disabled;
      b.setAttribute('aria-label', label);
      b.addEventListener('click', () => {
        state.counts[m.model] = Math.min(m.max_count, Math.max(0, n + delta));
        renderTelescopes();
        renderGroups();
      });
      return b;
    };

    const out = document.createElement('output');
    out.textContent = String(n);

    stepper.append(
      step(-1, '−', n <= 0, `One fewer ${m.display}`),
      out,
      step(+1, '+', n >= m.max_count, `One more ${m.display}`),
    );

    chip.append(stepper);
    host.append(chip);
  }
}

/* Mirrors target_lists.instance_labels: one keeps the bare name, several get numbered. */
function instanceLabels(model, count) {
  if (count <= 0) return [];
  if (count === 1) return [model];
  return Array.from({ length: count }, (_, i) => `${model}_${i + 1}`);
}

function groupMembers(group) {
  const labels = [];
  for (const m of state.models) {
    if (m.kind !== group.kind) continue;
    labels.push(...instanceLabels(m.model, state.counts[m.model] ?? 0));
  }
  return labels;
}

function renderGroups() {
  const host = el('group-list');
  host.textContent = '';

  for (const g of GROUPS) {
    const members = groupMembers(g);
    const settings = state.groupSettings[g.name];

    const row = document.createElement('div');
    row.className = 'group' + (members.length === 0 ? ' is-empty' : '');

    const name = document.createElement('span');
    name.className = 'group-name';
    name.textContent = g.name;

    const select = document.createElement('select');
    for (const key of ['diverse', 'match', 'none']) {
      const opt = document.createElement('option');
      opt.value = key;
      opt.textContent = COUPLING_OPTIONS[key];
      opt.selected = settings.coupling === key;
      select.append(opt);
    }
    select.disabled = members.length < 2;
    select.setAttribute('aria-label', `${g.name} category rule`);
    select.addEventListener('change', () => { settings.coupling = select.value; });

    const slotsLabel = document.createElement('label');
    slotsLabel.append(document.createTextNode('targets each'));
    const slots = document.createElement('input');
    slots.type = 'number';
    slots.min = '1';
    slots.max = '20';
    slots.placeholder = 'auto';
    slots.value = settings.num_slots === null ? '' : String(settings.num_slots);
    slots.disabled = members.length === 0;
    slots.title = 'Leave blank to have one suggested from the window length, how ' +
                  'long each telescope needs per object, and what is actually up';
    slots.addEventListener('change', () => {
      const parsed = parseInt(slots.value, 10);
      settings.num_slots = Number.isFinite(parsed) && parsed > 0 ? parsed : null;
      slots.value = settings.num_slots === null ? '' : String(settings.num_slots);
    });
    slotsLabel.prepend(slots);

    row.append(name, select, slotsLabel);
    host.append(row);
  }
}

/* ------------------------------------------------------------------ running */

function buildConfig() {
  const groups = GROUPS
    .map((g) => ({
      name: g.name,
      telescopes: groupMembers(g),
      coupling: state.groupSettings[g.name].coupling,
      num_slots: state.groupSettings[g.name].num_slots,
    }))
    .filter((g) => g.telescopes.length > 0);

  return {
    date: el('date').value,
    start_time: el('start-time').value,
    end_time: el('end-time').value,
    min_altitude: parseFloat(el('min-altitude').value),
    counts: state.counts,
    groups,
  };
}

async function generate() {
  clearError();
  const config = buildConfig();

  if (!config.date) { showError('Pick a date first.'); return; }
  if (config.groups.length === 0) {
    showError('Every telescope is set to zero — add at least one.');
    return;
  }

  el('generate').disabled = true;
  setStatus('Working out what is up…');

  // let the browser paint before Python takes the thread
  await new Promise((r) => requestAnimationFrame(() => setTimeout(r, 0)));

  try {
    state.pyodide.globals.set('_config_json', JSON.stringify(config));
    const result = JSON.parse(state.pyodide.runPython('bridge.run_schedule(_config_json)'));

    if (!result.ok) {
      el('results').hidden = true;
      showError(result.error);
      setStatus('');
      return;
    }

    state.lastResult = result;
    renderResults(result);
    setStatus('');
  } catch (err) {
    el('results').hidden = true;
    showError(String(err && err.message ? err.message : err));
    setStatus('');
  } finally {
    el('generate').disabled = false;
  }
}

/* ---------------------------------------------------------------- rendering */

function renderResults(result) {
  const pretty = new Date(`${result.date}T12:00:00`).toLocaleDateString(undefined, {
    weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
  });
  el('results-title').textContent =
    `${pretty}, ${result.start_time}–${result.end_time}`;

  renderTimelines(result);
  renderTables(result);
  el('results').hidden = false;
}

function renderTimelines(result) {
  const host = el('timelines');
  host.textContent = '';

  for (const group of result.groups) {
    const scopes = group.telescopes.map((l) => result.telescopes[l]);
    if (scopes.length === 0) continue;

    const block = document.createElement('div');
    block.className = 'group-block';

    const check = (result.checks || []).find((c) => c.group === group.name);
    const h3 = document.createElement('h3');
    h3.textContent = group.name;

    //say what it settled on, and let the tooltip explain why
    const bits = [`${group.num_slots} targets each, ~${group.minutes_per_target} min`];
    if (check) {
      bits.push(check.achieved === check.total
        ? `${COUPLING_LABELS[group.coupling]} throughout`
        : `${COUPLING_LABELS[group.coupling]} in ${check.achieved} of ${check.total}`);
    }

    const note = document.createElement('span');
    note.textContent = ` — ` + bits.join(` · `);
    if (group.auto_slots && group.recommendation) {
      note.title = `Suggested: ${group.recommendation.reason}. ` +
                   'Set a number under Options to override.';
    }
    h3.append(note);

    const scroll = document.createElement('div');
    scroll.className = 'scroll';

    const table = document.createElement('table');
    table.className = 'timeline';

    const thead = document.createElement('thead');
    const hrow = document.createElement('tr');
    hrow.append(document.createElement('th'));
    for (const row of scopes[0].rows) {
      const th = document.createElement('th');
      th.textContent = `${row.start}–${row.end}`;
      hrow.append(th);
    }
    thead.append(hrow);

    const tbody = document.createElement('tbody');
    for (const scope of scopes) {
      const tr = document.createElement('tr');
      const th = document.createElement('th');
      th.scope = 'row';
      th.textContent = scope.display;
      tr.append(th);

      for (const row of scope.rows) {
        const td = document.createElement('td');

        if (row.object === null) {
          const blank = document.createElement('span');
          blank.className = 'blank';
          blank.textContent = '—';
          blank.title = 'Nothing in reach; operator’s choice';
          td.append(blank);
        } else {
          const obj = document.createElement('span');
          obj.className = 'obj';
          obj.append(catDot(row.cls), document.createTextNode(row.name));

          const sub = document.createElement('span');
          sub.className = 'sub';
          sub.textContent = `${row.elev}° ${row.path}` + (row.repeat ? ' · again' : '');

          td.append(obj, sub);
        }
        tr.append(td);
      }
      tbody.append(tr);
    }

    table.append(thead, tbody);
    scroll.append(table);
    block.append(h3, scroll);

    const notes = [...new Set([
      ...(check ? check.blockers || [] : []),
      ...scopes.flatMap((s) => s.notes || []),
    ])];
    for (const text of notes) {
      const p = document.createElement('p');
      p.className = 'note';
      p.textContent = text;
      block.append(p);
    }

    host.append(block);
  }

  const legend = document.createElement('p');
  legend.className = 'legend';
  for (const c of state.classes) {
    const span = document.createElement('span');
    span.append(catDot(c.key), document.createTextNode(c.display));
    legend.append(span);
  }
  host.append(legend);
}

function renderTables(result) {
  const host = el('tables');
  host.textContent = '';

  for (const group of result.groups) {
    for (const label of group.telescopes) {
      const scope = result.telescopes[label];

      const card = document.createElement('details');

      const summary = document.createElement('summary');
      summary.append(document.createTextNode(scope.display));

      const file = document.createElement('span');
      file.className = 'file';
      file.textContent = `catalog_${label}.csv`;
      summary.append(file);

      const spacer = document.createElement('span');
      spacer.className = 'spacer';
      summary.append(spacer);

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'link';
      btn.textContent = 'Download';
      btn.addEventListener('click', (ev) => {
        ev.preventDefault();
        downloadBlob(new Blob([scope.csv], { type: 'text/csv;charset=utf-8' }),
                     `catalog_${label}.csv`);
      });
      summary.append(btn);

      const table = document.createElement('table');
      table.className = 'detail';

      const thead = document.createElement('thead');
      const hrow = document.createElement('tr');
      for (const h of ['Time', 'Object', 'Type', 'Alt', 'Moving', 'Catalog']) {
        const th = document.createElement('th');
        th.textContent = h;
        hrow.append(th);
      }
      thead.append(hrow);

      const tbody = document.createElement('tbody');
      for (const row of scope.rows) {
        const tr = document.createElement('tr');
        if (row.object === null) {
          tr.append(cell(`${row.start}–${row.end}`, 'num'));
          const td = document.createElement('td');
          td.colSpan = 5;
          td.className = 'blank';
          td.textContent = '— nothing in reach';
          tr.append(td);
        } else {
          const objCell = document.createElement('td');
          objCell.append(catDot(row.cls), document.createTextNode(row.name));
          tr.append(
            cell(`${row.start}–${row.end}`, 'num'),
            objCell,
            cell(row.type),
            cell(`${row.elev}°`, 'num'),
            cell(row.path),
            cell(row.object),
          );
        }
        tbody.append(tr);
      }

      if (scope.alternates.length) {
        const head = document.createElement('tr');
        head.className = 'alt-head';
        const td = document.createElement('td');
        td.colSpan = 6;
        td.textContent = 'Alternates';
        head.append(td);
        tbody.append(head);

        for (const alt of scope.alternates) {
          const tr = document.createElement('tr');
          tr.className = 'alt';
          const objCell = document.createElement('td');
          objCell.append(catDot(alt.cls), document.createTextNode(alt.name));
          tr.append(
            cell(alt.when, 'num'),
            objCell,
            cell(alt.type),
            cell(`${alt.elev}°`, 'num'),
            cell('peak'),
            cell(alt.object),
          );
          tbody.append(tr);
        }
      }

      table.append(thead, tbody);
      card.append(summary, table);
      host.append(card);
    }
  }
}

/* ---------------------------------------------------------------- downloads */

function downloadAll() {
  if (!state.lastResult) return;
  state.pyodide.globals.set('_result_json', JSON.stringify(state.lastResult));
  const b64 = state.pyodide.runPython('bridge.zip_bundle(_result_json)');
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  downloadBlob(new Blob([bytes], { type: 'application/zip' }),
               `stargazing_${state.lastResult.date}.zip`);
}

/* ----------------------------------------------------------------- start-up */

async function main() {
  el('date').value = defaultDate();

  el('config-form').addEventListener('submit', (ev) => {
    ev.preventDefault();
    generate();
  });
  el('download-zip').addEventListener('click', downloadAll);
  el('print-view').addEventListener('click', () => window.print());
  el('advanced-toggle').addEventListener('click', () => {
    const panel = el('advanced');
    panel.hidden = !panel.hidden;
    el('advanced-toggle').textContent = panel.hidden ? 'Options' : 'Hide options';
  });

  try {
    await bootPython();
  } catch (err) {
    setStatus('');
    el('generate').textContent = 'Unavailable';
    showError('Could not start Python in this browser: ' +
              String(err && err.message ? err.message : err));
    return;
  }

  resetToDefaults();
  el('generate').textContent = 'Make schedule';
  el('generate').disabled = false;
  setStatus('');
}

main();
