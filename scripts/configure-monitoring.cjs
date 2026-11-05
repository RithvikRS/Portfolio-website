const fs = require('node:fs');
const { io } = require('socket.io-client');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const socket = io('http://127.0.0.1:3001', { transports: ['websocket'], reconnection: false });
let monitors = {}, notifications = [];
socket.on('monitorList', value => { monitors = value; });
socket.on('notificationList', value => { notifications = value; });
const call = (event, ...args) => new Promise((resolve, reject) => {
    socket.timeout(20000).emit(event, ...args, (error, result) => {
        if (error || !result?.ok) reject(new Error('Kuma operation failed: ' + event));
        else resolve(result);
    });
});
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
    await new Promise((resolve, reject) => {
        socket.once('connect', resolve);
        socket.once('connect_error', () => reject(new Error('Cannot connect to Kuma')));
    });
    // Kuma registers request handlers after its asynchronous initial info event.
    await sleep(500);
    if (input.bootstrap) {
        // Setup refuses an existing database. Never reset an existing account.
        await call('setup', input.username, input.password).catch(() => {});
    }
    await call('login', { username: input.username, password: input.password, token: '' });
    await call('getMonitorList');
    if (input.action === 'check') {
        const rows = [];
        for (const monitor of Object.values(monitors)) {
            const beats = await call('getMonitorBeats', monitor.id, 1);
            rows.push({ name: monitor.name, active: monitor.active, retries: monitor.maxretries,
                repeat: monitor.resendInterval, interval: monitor.interval, beats: beats.data?.slice(-3).map(b => ({status: b.status, time: b.time})) });
        }
        console.log(JSON.stringify({ monitors: rows, notificationCount: notifications.length }));
        return;
    }
    if (!input.notification) throw new Error('Missing private notification settings');
    const existing = notifications.find(n => n.name === 'Private infrastructure alerts');
    const notification = { name: 'Private infrastructure alerts', type: 'ntfy', isDefault: false,
        applyExisting: false, ntfyAuthenticationMethod: 'usernamePassword', ntfyPriority: 3,
        ntfyserverurl: input.notification.url, ntfytopic: input.notification.topic,
        ntfyusername: input.notification.username, ntfypassword: input.notification.password };
    const saved = await call('addNotification', notification, existing?.id ?? null);
    const defaults = { type: 'http', method: 'GET', interval: 60, retryInterval: 30, maxretries: 2,
        resendInterval: 0, timeout: 10, maxredirects: 0, accepted_statuscodes: ['200'],
        notificationIDList: { [saved.id]: true }, ignoreTls: false, upsideDown: false,
        expiryNotification: false, domainExpiryNotification: false, saveResponse: false,
        saveErrorResponse: false, parent: null, active: true, conditions: [],
        kafkaProducerBrokers: [], kafkaProducerSaslOptions: { mechanism: 'None' }, rabbitmqNodes: [] };
    if (input.action === 'rehearse') {
        // A disposable local endpoint exercises retries and recovery without taking production down.
        let healthy = true;
        const server = require('node:http').createServer((req, res) => { res.writeHead(healthy ? 200 : 503); res.end('monitoring rehearsal'); });
        await new Promise(resolve => server.listen(3099, '127.0.0.1', resolve));
        let id;
        try {
            const result = await call('add', { ...defaults, name: 'Monitoring delivery rehearsal', url: 'http://127.0.0.1:3099', interval: 20, retryInterval: 20 });
            id = result.monitorID;
            await sleep(25000);
            healthy = false;
            await sleep(100000);
            healthy = true;
            await sleep(45000);
            const resultBeats = await call('getMonitorBeats', id, 1);
            const statuses = resultBeats.data.map(b => b.status);
            if (!statuses.includes(0) || statuses.at(-1) !== 1) throw new Error('Outage/recovery rehearsal failed');
            console.log('Controlled outage and recovery completed; verify ntfy delivery counts separately.');
        } finally {
            if (id) await call('deleteMonitor', id);
            await new Promise(resolve => server.close(resolve));
        }
        return;
    }
    if (input.action !== 'configure') throw new Error('Unknown action');
    const settings = (await call('getSettings')).data;
    await call('setSettings', { ...settings, disableAuth: false, keepDataPeriodDays: 30,
        serverTimezone: 'Asia/Kolkata', entryPage: 'dashboard' }, input.password);
    const desired = [
        ['Portfolio HTTPS', 'https://rithvik.ddns.net/', ['200']],
        ['Portfolio backend', 'http://caddy:8081/app', ['200']],
        ['Authelia backend', 'http://caddy:8081/identity', ['200']],
        ['Portainer backend', 'http://caddy:8081/containers', ['200']],
        ['ntfy backend', 'http://caddy:8081/notifications', ['200']],
        ['AMD worker demo', 'http://caddy:8081/worker', ['200']],
        ['Kuma login gate', 'https://uptime.144.24.135.201.sslip.io/', ['302','303','401']],
        ['Portfolio admin gate', 'https://rithvik.ddns.net/admin/', ['302','303','401']],
        ['ntfy browser gate', 'https://ntfy.144.24.135.201.sslip.io/', ['302','303','401']]
    ];
    for (const [name, url, statuses] of desired) {
        const prior = Object.values(monitors).find(m => m.name === name);
        const monitor = { ...defaults, name, url, accepted_statuscodes: statuses,
            expiryNotification: name === 'Portfolio HTTPS' };
        if (prior) await call('editMonitor', { ...(await call('getMonitor', prior.id)).monitor, ...monitor, id: prior.id });
        else await call('add', monitor);
    }
    console.log('Configured nine monitors, 30-day retention, two retries, and no repeated outage reminders.');
})().catch(error => { console.error(error.message); process.exitCode = 1; }).finally(() => socket.disconnect());
