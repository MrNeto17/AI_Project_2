(() => {
    const cfg = window.SIMULATION_CONFIG || { refreshMs: 1000, initialState: {} };
    let state = cfg.initialState || {};
    let timer = null;

    const clockEl = document.getElementById('clockValue');
    const viewSelect = document.getElementById('viewSelect');
    const goMetricsBtn = document.getElementById('goMetricsBtn');

    const columns = {
        faturas: document.getElementById('col-faturas'),
        orders_queue: document.getElementById('col-orders-queue'),
        orders_answered: document.getElementById('col-orders-answered'),
        item_queue: document.getElementById('col-item-queue'),
        item_prep: document.getElementById('col-item-prep'),
        shelf: document.getElementById('col-shelf'),
        trash: document.getElementById('col-trash')
    };

    function _timeFrom(value) {
        if (!value) return '-';
        // value may be like 'dd/mm/yyyy HH:MM' or 'HH:MM' or a datetime-like string
        const s = String(value);
        if (s.indexOf(' ') >= 0) return s.split(' ').pop();
        return s;
    }

    const PROD_COLOR_MAP = {
        'beef_burger': '#f380ba',
        'chicken_burger': '#dc3545',
        'fish_burger': '#1e90ff',
        'vegan_burger': '#28a745',
        'fries': '#ffc107',
        'apple_pie': '#67118c'
    };

    function _makeProdLabel(name) {
        const prod = String(name || '').trim().toLowerCase().replace(/\s+/g, '_');
        const wrapper = document.createElement('span');
        wrapper.className = 'prod-label';
        const dot = document.createElement('span');
        dot.className = 'prod-dot';
        const color = PROD_COLOR_MAP[prod];
        if (color) dot.style.background = color; else dot.style.background = 'transparent';
        const text = document.createElement('span');
        text.className = 'prod-label-text';
        text.textContent = name || '';
        wrapper.appendChild(dot);
        wrapper.appendChild(text);
        return wrapper;
    }

    function _formatInvoice(inv) {
        // inv: [hour, invoice_id, invoice_nr, lines, items]
        const hour = inv[0] || '';
        const invoiceId = inv[1] || '';
        const lines = Array.isArray(inv[3]) ? inv[3] : [];
        const items = Array.isArray(inv[4]) ? inv[4] : [];

        const container = document.createElement('div');
        container.className = 'state-entry';

        const header = document.createElement('div');
        header.className = 'fw-bold';
        header.textContent = `${hour}     ID: ${invoiceId}`;
        container.appendChild(header);

        lines.forEach((ln) => {
            // ln: [line_nr, parent_id, product_id, product_name, quantity, price]
            const lineDiv = document.createElement('div');
            lineDiv.style.whiteSpace = 'pre-wrap';
            const lineNr = ln[0] != null ? ln[0] : '';
            const parent = ln[1] || '';
            const prodId = ln[2] != null ? ln[2] : '';
            const prodName = ln[3] || '';
            const qty = ln[4] != null ? ln[4] : '';
            const price = ln[5] != null ? ln[5] : '';
            const indent = parent ? '    ' : '';
            lineDiv.textContent = `${indent}${lineNr} ${prodId} ${prodName} (${qty}, ${price})`;
            container.appendChild(lineDiv);
        });

        if (items.length) {
            const summary = document.createElement('div');
            summary.className = 'inv-summary';
            const parts = items.map((it) => `${it[0]}(${it[1]})`);
            summary.textContent = `Contains: ${parts.join(', ')}`;
            container.appendChild(summary);
        }

        return container;
    }

    function _formatOrder(order) {
        // order: [name, invoice_id, hora_emissao, hora_recebido, estado, ...]
        const name = order[0] || '';
        const invoiceId = order[1] != null ? order[1] : '';
        const emitted = _timeFrom(order[2]);
        const received = order[3] ? _timeFrom(order[3]) : '-';

        const container = document.createElement('div');
        container.className = 'state-entry';

        const idLine = document.createElement('div');
        idLine.className = 'fw-bold';
        idLine.textContent = `ID: ${invoiceId}`;
        container.appendChild(idLine);

        const nameLine = document.createElement('div');
        const nameLabel = _makeProdLabel(name);
        nameLine.appendChild(nameLabel);
        container.appendChild(nameLine);

        const sentLine = document.createElement('div');
        sentLine.className = 'text-muted';
        sentLine.textContent = `SENT: ${emitted}`;
        container.appendChild(sentLine);

        const delLine = document.createElement('div');
        delLine.className = 'text-muted';
        delLine.textContent = `DELIVERED: ${received}`;
        container.appendChild(delLine);

        return container;
    }

    function _formatItem(item) {
        // item: [name, hora_pronto, hora_prazo, hora_entregue, estado]
        const name = item[0] || '';
        const horaPronto = item[1] ? _timeFrom(item[1]) : '-';
        const horaPrazo = item[2] ? _timeFrom(item[2]) : '-';
        const horaEntregue = item[3] ? _timeFrom(item[3]) : '-';

        const container = document.createElement('div');
        container.className = 'state-entry';

        const nameLine = document.createElement('div');
        nameLine.className = 'fw-bold';
        const nameLabel = _makeProdLabel(name);
        nameLine.appendChild(nameLabel);
        container.appendChild(nameLine);

        const firstReady = document.createElement('div');
        firstReady.className = 'text-muted';
        firstReady.textContent = `FIRST_READY: ${horaPronto}`;
        container.appendChild(firstReady);

        const endShelf = document.createElement('div');
        endShelf.className = 'text-muted';
        endShelf.textContent = `END_SHELF_TIME: ${horaPrazo}`;
        container.appendChild(endShelf);

        const delivered = document.createElement('div');
        delivered.className = 'text-muted';
        delivered.textContent = `DELIVERED: ${horaEntregue}`;
        container.appendChild(delivered);

        return container;
    }

    function renderList(el, items) {
        if (!el) return;
        el.innerHTML = '';
        if (!items || items.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'state-entry text-muted';
            empty.textContent = '(empty)';
            el.appendChild(empty);
            return;
        }

        items.forEach((item) => {
            let node = null;
            if (el === columns.faturas) {
                node = _formatInvoice(item);
            } else if (el === columns.orders_queue || el === columns.orders_answered) {
                node = _formatOrder(item);
            } else {
                // item_queue, item_prep, shelf, trash
                node = _formatItem(item);
            }
            el.appendChild(node);
        });
    }

    function render(newState) {
        state = newState;
        if (clockEl) clockEl.textContent = state.clock || '--:--';

        renderList(columns.faturas, state.faturas);
        renderList(columns.orders_queue, state.orders_queue);
        renderList(columns.orders_answered, state.orders_answered);
        renderList(columns.item_queue, state.item_queue);
        renderList(columns.item_prep, state.item_prep);
        renderList(columns.shelf, state.shelf);
        renderList(columns.trash, state.trash);

        if (state.is_complete) {
            if (goMetricsBtn) goMetricsBtn.classList.remove('d-none');
            if (timer) {
                clearInterval(timer);
                timer = null;
            }
            if (viewSelect) viewSelect.disabled = true;
        }
    }

    async function fetchState() {
        const view = viewSelect ? viewSelect.value : 'GERAL';
        const res = await fetch(`/api/simulation/state?view=${encodeURIComponent(view)}`);
        const data = await res.json();
        if (res.ok) render(data);
    }

    async function tick() {
        const view = viewSelect ? viewSelect.value : 'GERAL';
        const res = await fetch('/api/simulation/tick', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ view })
        });
        const data = await res.json();
        if (res.ok) {
            render(data);
        }
    }

    if (viewSelect) {
        viewSelect.addEventListener('change', () => {
            fetchState();
        });
    }

    render(state);

    if (!state.is_complete) {
        timer = setInterval(() => {
            tick();
        }, Number(cfg.refreshMs || 1000));
    }
})();
