const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = n => '₡' + Number(n).toLocaleString('es-CR');
let token = sessionStorage.getItem('token');

function say(text, ok = true) {
  const box = $('message');
  box.textContent = text;
  box.className = text ? (ok ? 'ok' : 'error') : '';
}

async function api(path, method = 'GET', body) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = 'Bearer ' + token;
  const response = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && token && path !== '/api/login') { logout(); viewLogin(); }
    const detail = Array.isArray(data.detail) ? data.detail.map(d => d.msg).join(', ') : data.detail;
    throw new Error(detail || 'Ocurrió un error inesperado.');
  }
  return data;
}

const labels = { libros: 'Libros', menu: 'Menú', espacios: 'Espacios', reservar: 'Reservar', admin: 'Administración' };
let current = 'libros';

function go(name) {
  current = name;
  say('');
  $('menu').innerHTML = Object.entries(labels).map(([key, text]) =>
    `<button class="${key === current ? 'active' : ''}" data-view="${key}">${text}</button>`).join('');
  ({ libros: viewLibros, menu: viewMenu, espacios: viewEspacios, reservar: viewReservar, admin: viewAdmin })[name]();
}
$('menu').onclick = event => {
  const button = event.target.closest('button');
  if (button) go(button.dataset.view);
};

async function viewLibros() {
  try {
    const libros = await api('/api/libros');
    $('view').innerHTML = '<h2>Catálogo de libros</h2><p class="hint">Libros disponibles para leer en el local.</p><div class="cards">' +
      libros.map(l => `<article class="card"><h3>${esc(l.titulo)}</h3><p>${esc(l.autor)}</p><p><span class="tag">${esc(l.genero)}</span> ` +
        (l.disponible && l.ejemplares > 0 ? `<span class="tag ok">${l.ejemplares} disponible(s)</span>` : '<span class="tag off">No disponible</span>') +
        '</p></article>').join('') + '</div>';
  } catch (error) { say(error.message, false); }
}

async function viewMenu() {
  try {
    const productos = (await api('/api/productos_menu')).filter(p => p.disponible && p.stock > 0);
    const grupos = {};
    productos.forEach(p => (grupos[p.categoria] ||= []).push(p));
    $('view').innerHTML = '<h2>Menú de repostería</h2>' + Object.entries(grupos).map(([categoria, items]) =>
      `<h3>${esc(categoria)}</h3><div class="cards">` + items.map(p =>
        `<article class="card"><h3>${esc(p.nombre)}</h3><p>${esc(p.descripcion)}</p><p class="price">${money(p.precio)}</p></article>`).join('') + '</div>').join('');
  } catch (error) { say(error.message, false); }
}

async function viewEspacios() {
  try {
    const espacios = await api('/api/espacios');
    $('view').innerHTML = '<h2>Espacios de lectura</h2><div class="cards">' + espacios.map(e =>
      `<article class="card"><h3>${esc(e.nombre)}</h3><p>${esc(e.tipo)} · capacidad ${e.capacidad}</p><p>` +
      (e.estado === 'disponible' ? '<span class="tag ok">Disponible</span>' : '<span class="tag off">En mantenimiento</span>') + '</p></article>').join('') + '</div>';
  } catch (error) { say(error.message, false); }
}

async function viewReservar() {
  try {
    const espacios = (await api('/api/espacios')).filter(e => e.estado === 'disponible');
    const hoy = new Date().toLocaleDateString('en-CA');
    $('view').innerHTML = `<h2>Reservar un espacio</h2>
      <form id="form-reserva" class="form">
        <label>Espacio<select name="id_espacio" required><option value="">Seleccione…</option>${espacios.map(e => `<option value="${e.id_espacio}">${esc(e.nombre)} (${e.capacidad} personas)</option>`).join('')}</select></label>
        <label>Fecha<input type="date" name="fecha" min="${hoy}" required></label>
        <label>Hora de inicio<input type="time" name="hora_inicio" required></label>
        <label>Hora de fin<input type="time" name="hora_fin" required></label>
        <label>Personas<input type="number" name="num_personas" min="1" value="1" required></label>
        <label>Su nombre<input name="nombre" required></label>
        <label>Teléfono<input name="telefono" required></label>
        <label>Correo<input type="email" name="email" required></label>
        <button class="primary">Reservar</button>
      </form>
      <p id="ocupados" class="hint"></p>`;
    const form = $('form-reserva');
    const mostrarOcupados = async () => {
      if (!form.elements.id_espacio.value || !form.elements.fecha.value) return;
      const { ocupados } = await api(`/api/espacios/${form.elements.id_espacio.value}/disponibilidad?fecha=${form.elements.fecha.value}`);
      $('ocupados').textContent = ocupados.length
        ? 'Horarios ya reservados: ' + ocupados.map(f => `${f.hora_inicio}–${f.hora_fin}`).join(', ')
        : 'Este espacio está libre todo el día.';
    };
    form.elements.id_espacio.onchange = mostrarOcupados;
    form.elements.fecha.onchange = mostrarOcupados;
    form.onsubmit = async event => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(form));
      data.id_espacio = Number(data.id_espacio);
      data.num_personas = Number(data.num_personas);
      try {
        await api('/api/reservar', 'POST', data);
        say('¡Reserva registrada! Quedó pendiente de confirmación por el personal.');
        form.reset();
        $('ocupados').textContent = '';
      } catch (error) { say(error.message, false); }
    };
  } catch (error) { say(error.message, false); }
}

function logout() {
  token = null;
  sessionStorage.removeItem('token');
}

function viewAdmin() { token ? viewPanel() : viewLogin(); }

function viewLogin() {
  $('view').innerHTML = `<h2>Acceso del personal</h2>
    <form id="form-login" class="form narrow">
      <label>Correo<input type="email" name="email" required></label>
      <label>Contraseña<input type="password" name="password" required></label>
      <button class="primary">Entrar</button>
    </form>`;
  $('form-login').onsubmit = async event => {
    event.preventDefault();
    try {
      const result = await api('/api/login', 'POST', Object.fromEntries(new FormData(event.target)));
      token = result.token;
      sessionStorage.setItem('token', token);
      say('Bienvenido/a, ' + result.nombre + '.');
      viewPanel();
    } catch (error) { say(error.message, false); }
  };
}

const SI_NO = [[1, 'Sí'], [0, 'No']];
const entities = {
  reservas: {
    label: 'Reservas', pk: 'id_reserva',
    columns: ['id_reserva', 'cliente', 'espacio', 'fecha', 'hora_inicio', 'hora_fin', 'num_personas', 'estado'],
    fields: [
      { name: 'id_cliente', label: 'cliente', ref: 'clientes', num: true },
      { name: 'id_espacio', label: 'espacio', ref: 'espacios', num: true },
      { name: 'fecha', type: 'date' },
      { name: 'hora_inicio', label: 'hora de inicio', type: 'time' },
      { name: 'hora_fin', label: 'hora de fin', type: 'time' },
      { name: 'num_personas', label: 'personas', type: 'number', num: true },
      { name: 'estado', options: [['pendiente', 'Pendiente'], ['confirmada', 'Confirmada'], ['cancelada', 'Cancelada']] }
    ]
  },
  espacios: {
    label: 'Espacios', pk: 'id_espacio',
    columns: ['id_espacio', 'nombre', 'tipo', 'capacidad', 'estado'],
    fields: [
      { name: 'nombre' },
      { name: 'tipo', options: [['mesa', 'Mesa'], ['zona de lectura', 'Zona de lectura'], ['sala privada', 'Sala privada']] },
      { name: 'capacidad', type: 'number', num: true },
      { name: 'estado', options: [['disponible', 'Disponible'], ['mantenimiento', 'En mantenimiento']] }
    ]
  },
  clientes: {
    label: 'Clientes', pk: 'id_cliente',
    columns: ['id_cliente', 'nombre', 'telefono', 'email'],
    fields: [{ name: 'nombre' }, { name: 'telefono', label: 'teléfono' }, { name: 'email', label: 'correo', type: 'email' }]
  },
  libros: {
    label: 'Libros', pk: 'id_libro',
    columns: ['id_libro', 'titulo', 'autor', 'genero', 'ejemplares', 'disponible'],
    fields: [
      { name: 'id_genero', label: 'género', ref: 'generos', num: true },
      { name: 'titulo', label: 'título' },
      { name: 'autor' },
      { name: 'ejemplares', type: 'number', num: true },
      { name: 'disponible', options: SI_NO, num: true }
    ]
  },
  generos: {
    label: 'Géneros', pk: 'id_genero',
    columns: ['id_genero', 'nombre'],
    fields: [{ name: 'nombre' }]
  },
  productos_menu: {
    label: 'Menú', pk: 'id_producto',
    columns: ['id_producto', 'nombre', 'categoria', 'precio', 'stock', 'disponible'],
    fields: [
      { name: 'id_categoria', label: 'categoría', ref: 'categorias_menu', num: true },
      { name: 'nombre' },
      { name: 'descripcion', label: 'descripción' },
      { name: 'precio', type: 'number', step: '0.01', num: true },
      { name: 'stock', type: 'number', num: true },
      { name: 'disponible', options: SI_NO, num: true }
    ]
  },
  categorias_menu: {
    label: 'Categorías del menú', pk: 'id_categoria',
    columns: ['id_categoria', 'nombre'],
    fields: [{ name: 'nombre' }]
  }
};

let tab = 'reservas';
let editing = null;
let rows = [];
let refs = {};

function viewPanel() {
  $('view').innerHTML = `<div class="panel-head"><h2>Panel de administración</h2><button id="logout">Cerrar sesión</button></div>
    <div id="tabs" class="tabs"></div>
    <form id="form" class="form"></form>
    <div class="table-scroll"><table><thead id="head"></thead><tbody id="body"></tbody></table></div>`;
  $('logout').onclick = () => { logout(); say('Sesión cerrada.'); viewLogin(); };
  $('tabs').onclick = event => {
    const button = event.target.closest('button');
    if (button) choose(button.dataset.tab);
  };
  $('body').onclick = event => {
    const button = event.target.closest('button');
    if (!button) return;
    const row = rows[Number(button.dataset.i)];
    if (button.dataset.act === 'edit') edit(row); else removeRow(row);
  };
  choose(tab);
}

async function choose(name) {
  tab = name;
  editing = null;
  $('tabs').innerHTML = Object.entries(entities).map(([key, e]) =>
    `<button class="${key === tab ? 'active' : ''}" data-tab="${key}">${e.label}</button>`).join('');
  try {
    for (const field of entities[tab].fields) {
      if (field.ref) refs[field.ref] = await api('/api/' + field.ref);
    }
    renderForm();
    await load();
  } catch (error) { say(error.message, false); }
}

function fieldHtml(field) {
  const text = field.label || field.name.replaceAll('_', ' ');
  if (field.ref) {
    const pk = entities[field.ref].pk;
    return `<label>${text}<select name="${field.name}" required><option value="">Seleccione…</option>` +
      (refs[field.ref] || []).map(r => `<option value="${r[pk]}">${esc(r.nombre)}</option>`).join('') + '</select></label>';
  }
  if (field.options) {
    return `<label>${text}<select name="${field.name}" required>` +
      field.options.map(([value, name]) => `<option value="${value}">${name}</option>`).join('') + '</select></label>';
  }
  return `<label>${text}<input name="${field.name}" type="${field.type || 'text'}" ${field.step ? `step="${field.step}"` : ''} ${field.type === 'number' ? 'min="0"' : ''} required></label>`;
}

function renderForm() {
  const entity = entities[tab];
  $('form').innerHTML = entity.fields.map(fieldHtml).join('') +
    `<button class="primary">${editing ? 'Actualizar' : 'Crear'}</button>` +
    (editing ? '<button type="button" id="cancel">Cancelar</button>' : '');
  if (editing) {
    for (const field of entity.fields) $('form').elements[field.name].value = editing[field.name];
    $('cancel').onclick = () => { editing = null; renderForm(); };
  }
  $('form').onsubmit = save;
}

async function load() {
  const entity = entities[tab];
  rows = await api('/api/' + tab);
  $('head').innerHTML = '<tr>' + entity.columns.map(c => `<th>${esc(c.replaceAll('_', ' '))}</th>`).join('') + '<th>Acciones</th></tr>';
  $('body').innerHTML = rows.map((row, i) => '<tr>' +
    entity.columns.map(c => `<td>${cell(c, row[c])}</td>`).join('') +
    `<td class="actions"><button data-act="edit" data-i="${i}">Editar</button><button class="danger" data-act="del" data-i="${i}">Borrar</button></td></tr>`).join('');
}

function cell(column, value) {
  if (column === 'disponible') return value ? 'Sí' : 'No';
  if (column === 'precio') return money(value);
  return esc(value);
}

async function save(event) {
  event.preventDefault();
  const entity = entities[tab];
  const data = {};
  for (const field of entity.fields) {
    const value = event.target.elements[field.name].value;
    data[field.name] = field.num ? Number(value) : value;
  }
  try {
    if (editing) await api(`/api/${tab}/${editing[entity.pk]}`, 'PUT', data);
    else await api('/api/' + tab, 'POST', data);
    say('Guardado correctamente.');
    editing = null;
    renderForm();
    await load();
  } catch (error) { say(error.message, false); }
}

function edit(row) {
  editing = row;
  renderForm();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function removeRow(row) {
  if (!confirm('¿Eliminar este registro?')) return;
  try {
    await api(`/api/${tab}/${row[entities[tab].pk]}`, 'DELETE');
    say('Registro eliminado.');
    await load();
  } catch (error) { say(error.message, false); }
}

go('libros');
