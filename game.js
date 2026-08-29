let currentRoom = null;
let currentPlayerId = null;
let pollInterval = null;
let currentStatus = null;

// Elementos DOM
const screens = {
    home: document.getElementById('screen-home'),
    lobby: document.getElementById('screen-lobby'),
    role: document.getElementById('screen-role'),
    clues: document.getElementById('screen-clues'),
    voting: document.getElementById('screen-voting'),
    results: document.getElementById('screen-results')
};

function showScreen(screenName) {
    Object.keys(screens).forEach(key => {
        screens[key].classList.remove('active');
    });
    screens[screenName].classList.add('active');
}

// Event Listeners - Crear y Unirse
document.getElementById('btn-create-room').addEventListener('click', () => {
    const name = document.getElementById('input-name').value.trim();
    if (!name) return showError('Ingresa tu nombre');

    fetch('/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) return showError(data.error);
        currentRoom = data.room;
        currentPlayerId = data.player_id;
        startPolling();
    });
});

document.getElementById('btn-join-room').addEventListener('click', () => {
    const name = document.getElementById('input-name').value.trim();
    const room = document.getElementById('input-room-code').value.trim().toUpperCase();
    if (!name || !room) return showError('Ingresa tu nombre y el código');

    fetch('/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, room })
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) return showError(data.error);
        currentRoom = data.room;
        currentPlayerId = data.player_id;
        startPolling();
    });
});

document.getElementById('btn-start-game').addEventListener('click', () => {
    const category = document.getElementById('select-category').value;
    const impostorCount = document.getElementById('select-impostors').value;

    fetch('/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            room: currentRoom,
            player_id: currentPlayerId,
            category,
            impostor_count: impostorCount
        })
    });
});

document.getElementById('btn-send-clue').addEventListener('click', () => {
    const clue = document.getElementById('input-clue').value.trim();
    fetch('/clue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            room: currentRoom,
            player_id: currentPlayerId,
            clue
        })
    }).then(() => {
        document.getElementById('input-clue').value = '';
    });
});

document.getElementById('btn-new-round').addEventListener('click', () => {
    fetch('/new-round', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            room: currentRoom,
            player_id: currentPlayerId
        })
    });
});

function showError(msg) {
    document.getElementById('home-error').textContent = msg;
}

// Bucle de consulta (Polling cada 800ms)
function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollState();
    pollInterval = setInterval(pollState, 800);
}

function pollState() {
    if (!currentRoom || !currentPlayerId) return;

    fetch(`/state?room=${currentRoom}&player_id=${currentPlayerId}`)
    .then(res => res.json())
    .then(state => {
        if (state.error) return;
        renderGame(state);
    });
}

function renderGame(state) {
    currentStatus = state.status;

    // Alternar visibilidad para el Host
    const hostElements = document.querySelectorAll('.host-only');
    hostElements.forEach(el => {
        if (state.is_host) el.classList.remove('hidden');
        else el.classList.add('hidden');
    });

    const guestMsg = document.getElementById('guest-msg');
    if (state.is_host) guestMsg.classList.add('hidden');
    else guestMsg.classList.remove('hidden');

    // Manejo de Estados
    if (state.status === 'LOBBY') {
        showScreen('lobby');
        document.getElementById('lobby-code-display').textContent = currentRoom;
        const list = document.getElementById('player-list');
        list.innerHTML = state.players.map(p => `<li>${p.name}</li>`).join('');
    } 
    else if (state.status === 'ROLE_REVEAL') {
        showScreen('role');
        document.getElementById('timer-role').textContent = state.time_left;

        const normalCard = document.getElementById('role-box-normal');
        const impostorCard = document.getElementById('role-box-impostor');

        if (state.is_impostor) {
            impostorCard.classList.remove('hidden');
            normalCard.classList.add('hidden');
        } else {
            normalCard.classList.remove('hidden');
            impostorCard.classList.add('hidden');
            document.getElementById('display-word').textContent = state.word;
        }
    } 
    else if (state.status === 'CLUES') {
        showScreen('clues');
        document.getElementById('timer-clues').textContent = state.time_left;

        const currentTurnPlayer = state.players.find(p => p.id === state.current_turn_id);
        document.getElementById('current-turn-name').textContent = currentTurnPlayer ? currentTurnPlayer.name : '---';

        const form = document.getElementById('my-clue-form');
        if (state.current_turn_id === currentPlayerId && !state.clues[currentPlayerId]) {
            form.classList.remove('hidden');
        } else {
            form.classList.add('hidden');
        }

        const cluesList = document.getElementById('clues-list');
        cluesList.innerHTML = state.players.map(p => {
            const clue = state.clues[p.id] || '(Pensando...)';
            return `<li><strong>${p.name}:</strong> ${clue}</li>`;
        }).join('');
    } 
    else if (state.status === 'VOTING') {
        showScreen('voting');
        document.getElementById('timer-voting').textContent = state.time_left;

        const container = document.getElementById('voting-candidates');
        const statusMsg = document.getElementById('vote-status-msg');

        if (state.tie_candidates && state.tie_candidates.length > 0) {
            document.getElementById('voting-subtitle').textContent = "¡Empate! Vota únicamente entre los finalistas:";
        } else {
            document.getElementById('voting-subtitle').textContent = "Elige a quien creas que es el impostor:";
        }

        if (state.has_voted) {
            container.innerHTML = '';
            statusMsg.textContent = "Tu voto ha sido registrado. Esperando a los demás...";
        } else {
            statusMsg.textContent = "";
            let candidates = state.players.filter(p => p.alive && p.id !== currentPlayerId);
            
            if (state.tie_candidates && state.tie_candidates.length > 0) {
                candidates = candidates.filter(p => state.tie_candidates.includes(p.id));
            }

            container.innerHTML = candidates.map(p => 
                `<button class="voting-btn" onclick="sendVote('${p.id}')">Votar por ${p.name}</button>`
            ).join('');
        }
    } 
    else if (state.status === 'RESULTS') {
        showScreen('results');
        
        const title = document.getElementById('winner-title');
        title.textContent = `¡GANAN LOS ${state.winner}!`;
        title.className = state.winner === 'IMPOSTORES' ? 'text-red' : 'text-green';

        document.getElementById('final-word').textContent = state.word;

        const rolesList = document.getElementById('final-roles-list');
        rolesList.innerHTML = state.players.map(p => `
            <li>
                <span>${p.name}</span>
                <strong class="${p.is_impostor ? 'text-red' : 'text-green'}">
                    ${p.is_impostor ? 'IMPOSTOR' : 'NORMAL'}
                </strong>
            </li>
        `).join('');

        const votesList = document.getElementById('final-votes-list');
        if (state.votes) {
            votesList.innerHTML = Object.entries(state.votes).map(([voterId, targetId]) => {
                const voter = state.players.find(p => p.id === voterId);
                const target = state.players.find(p => p.id === targetId);
                return `<li><strong>${voter ? voter.name : 'Alguien'}</strong> votó por <strong>${target ? target.name : 'Nadie'}</strong></li>`;
            }).join('');
        }

        const guestResultsMsg = document.getElementById('guest-results-msg');
        if (state.is_host) guestResultsMsg.classList.add('hidden');
        else guestResultsMsg.classList.remove('hidden');
    }
}

function sendVote(targetId) {
    fetch('/vote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            room: currentRoom,
            player_id: currentPlayerId,
            target_id: targetId
        })
    });
}
