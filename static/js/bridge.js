/**
 * ERPlora Bridge — WebSocket client for native hardware bridge.
 *
 * Auto-detects the ERPlora Bridge native app running on localhost
 * and provides an API for printing, cash drawer, and barcode scanning.
 *
 * Usage:
 *   - Prints: window.ERPlora.bridge.print(printerId, docType, data)
 *   - Drawer: window.ERPlora.bridge.openDrawer(printerId)
 *   - Status: window.ERPlora.bridge.connected  (boolean)
 *
 * Events dispatched on document.body:
 *   - erplora:bridge:connected
 *   - erplora:bridge:disconnected
 *   - erplora:bridge:barcode      (detail: {value, type})
 *   - erplora:bridge:print:complete (detail: {jobId})
 *   - erplora:bridge:print:error   (detail: {jobId, error})
 */
(function () {
    'use strict';

    window.ERPlora = window.ERPlora || {};

    // Read config injected by base.html (from HubConfig)
    var cfg = (window.ERPlora && window.ERPlora.bridgeConfig) || {};
    var BRIDGE_PORT = cfg.port || 12321;
    var BRIDGE_ENABLED = cfg.enabled !== undefined ? cfg.enabled : false;
    var BRIDGE_URL = 'ws://127.0.0.1:' + BRIDGE_PORT + '/ws';
    var STATUS_URL = 'http://127.0.0.1:' + BRIDGE_PORT + '/status';
    var DETECT_TIMEOUT = 500;       // ms to wait for health check
    var RECONNECT_DELAY = 5000;     // ms between reconnect attempts
    var MAX_RECONNECT_DELAY = 30000;

    // Pending print promises: jobId -> {resolve, reject}
    var pendingJobs = {};

    var bridge = {
        connected: false,
        printers: [],
        _ws: null,
        _reconnectTimer: null,
        _reconnectDelay: RECONNECT_DELAY,
        _intentionalClose: false,

        /**
         * Initialize bridge — detect and connect.
         * Called automatically on DOMContentLoaded.
         */
        init: function () {
            this._detect();
        },

        /**
         * Detect if the bridge native app is running.
         */
        _detect: function () {
            var self = this;
            var controller = new AbortController();
            var timeoutId = setTimeout(function () { controller.abort(); }, DETECT_TIMEOUT);

            fetch(STATUS_URL, { signal: controller.signal })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    clearTimeout(timeoutId);
                    console.log('[Bridge] Detected — v' + data.version + ', ' + data.printers + ' printer(s)');
                    self._connect();
                })
                .catch(function () {
                    clearTimeout(timeoutId);
                    console.log('[Bridge] Not detected — hardware features disabled');
                    self._setConnected(false);
                    self._scheduleReconnect();
                });
        },

        /**
         * Open WebSocket connection to bridge.
         */
        _connect: function () {
            var self = this;

            if (self._ws) {
                try { self._ws.close(); } catch (e) {}
            }

            self._intentionalClose = false;
            var ws = new WebSocket(BRIDGE_URL);

            ws.onopen = function () {
                console.log('[Bridge] WebSocket connected');
                self._reconnectDelay = RECONNECT_DELAY;
                self._setConnected(true);
            };

            ws.onmessage = function (event) {
                self._handleMessage(event.data);
            };

            ws.onclose = function () {
                console.log('[Bridge] WebSocket closed');
                self._ws = null;
                self._setConnected(false);
                if (!self._intentionalClose) {
                    self._scheduleReconnect();
                }
            };

            ws.onerror = function () {
                // onclose will fire after this
            };

            self._ws = ws;
        },

        /**
         * Schedule a reconnection attempt with exponential backoff.
         */
        _scheduleReconnect: function () {
            var self = this;
            if (self._reconnectTimer) return;

            self._reconnectTimer = setTimeout(function () {
                self._reconnectTimer = null;
                self._detect();
                self._reconnectDelay = Math.min(self._reconnectDelay * 1.5, MAX_RECONNECT_DELAY);
            }, self._reconnectDelay);
        },

        /**
         * Update connected state and dispatch events.
         */
        _setConnected: function (connected) {
            var changed = this.connected !== connected;
            this.connected = connected;

            if (changed) {
                var eventName = connected ? 'erplora:bridge:connected' : 'erplora:bridge:disconnected';
                document.dispatchEvent(new CustomEvent(eventName));
            }
        },

        /**
         * Send a JSON message to the bridge.
         */
        _send: function (msg) {
            if (this._ws && this._ws.readyState === WebSocket.OPEN) {
                this._ws.send(JSON.stringify(msg));
                return true;
            }
            return false;
        },

        /**
         * Handle incoming message from bridge.
         */
        _handleMessage: function (raw) {
            var msg;
            try { msg = JSON.parse(raw); } catch (e) { return; }

            var event = msg.event;

            if (event === 'status') {
                this.printers = msg.printers || [];

            } else if (event === 'printers') {
                this.printers = msg.printers || [];
                // Update Alpine store if available
                if (typeof Alpine !== 'undefined' && Alpine.store('bridge')) {
                    Alpine.store('bridge').printers = this.printers;
                }

            } else if (event === 'print_complete') {
                document.dispatchEvent(new CustomEvent('erplora:bridge:print:complete', {
                    detail: { jobId: msg.job_id }
                }));
                // Resolve pending promise
                if (pendingJobs[msg.job_id]) {
                    pendingJobs[msg.job_id].resolve({ jobId: msg.job_id, success: true });
                    delete pendingJobs[msg.job_id];
                }

            } else if (event === 'print_error') {
                document.dispatchEvent(new CustomEvent('erplora:bridge:print:error', {
                    detail: { jobId: msg.job_id, error: msg.error }
                }));
                if (pendingJobs[msg.job_id]) {
                    pendingJobs[msg.job_id].reject(new Error(msg.error));
                    delete pendingJobs[msg.job_id];
                }

            } else if (event === 'barcode') {
                document.dispatchEvent(new CustomEvent('erplora:bridge:barcode', {
                    detail: { value: msg.value, type: msg.type }
                }));

            } else if (event === 'drawer_opened') {
                // Could show a toast or log
                console.log('[Bridge] Cash drawer opened');

            } else if (event === 'error') {
                console.error('[Bridge] Error:', msg.message);
            }
        },

        // ─── Public API ─────────────────────────────────────────────────

        /**
         * Discover all connected printers.
         * @returns {Promise<Array>} List of printer objects
         */
        discoverPrinters: function () {
            var self = this;
            return new Promise(function (resolve, reject) {
                if (!self.connected) {
                    reject(new Error('Bridge not connected'));
                    return;
                }

                // Listen for the printers response
                var handler = function (raw) {
                    var msg;
                    try { msg = JSON.parse(raw.data); } catch (e) { return; }
                    if (msg.event === 'printers') {
                        self._ws.removeEventListener('message', handler);
                        self.printers = msg.printers || [];
                        resolve(self.printers);
                    }
                };
                self._ws.addEventListener('message', handler);

                // Timeout after 10 seconds
                setTimeout(function () {
                    self._ws.removeEventListener('message', handler);
                    reject(new Error('Discovery timeout'));
                }, 10000);

                self._send({ action: 'discover_printers' });
            });
        },

        /**
         * Print a document on the specified printer.
         * @param {string} printerId - Printer ID from discovery
         * @param {string} documentType - 'receipt', 'kitchen_order', etc.
         * @param {object} data - Document data
         * @returns {Promise<{jobId: string, success: boolean}>}
         */
        print: function (printerId, documentType, data) {
            var self = this;
            return new Promise(function (resolve, reject) {
                if (!self.connected) {
                    reject(new Error('Bridge not connected'));
                    return;
                }

                var jobId = self._generateId();
                pendingJobs[jobId] = { resolve: resolve, reject: reject };

                // Timeout after 30 seconds
                setTimeout(function () {
                    if (pendingJobs[jobId]) {
                        pendingJobs[jobId].reject(new Error('Print timeout'));
                        delete pendingJobs[jobId];
                    }
                }, 30000);

                self._send({
                    action: 'print',
                    printer_id: printerId,
                    document_type: documentType,
                    data: data,
                    job_id: jobId,
                });
            });
        },

        /**
         * Open the cash drawer connected to a printer.
         * @param {string} printerId - Printer with connected drawer
         * @returns {Promise<void>}
         */
        openDrawer: function (printerId) {
            var self = this;
            return new Promise(function (resolve, reject) {
                if (!self.connected) {
                    reject(new Error('Bridge not connected'));
                    return;
                }
                self._send({ action: 'open_drawer', printer_id: printerId });
                // Drawer open is fire-and-forget, resolve immediately
                resolve();
            });
        },

        /**
         * Print a test page on the specified printer.
         * @param {string} printerId
         * @returns {Promise<{jobId: string, success: boolean}>}
         */
        testPrint: function (printerId) {
            var self = this;
            return new Promise(function (resolve, reject) {
                if (!self.connected) {
                    reject(new Error('Bridge not connected'));
                    return;
                }

                var jobId = self._generateId();
                pendingJobs[jobId] = { resolve: resolve, reject: reject };

                setTimeout(function () {
                    if (pendingJobs[jobId]) {
                        pendingJobs[jobId].reject(new Error('Test print timeout'));
                        delete pendingJobs[jobId];
                    }
                }, 15000);

                // The bridge will generate its own job_id for test_print
                // but we listen for any print_complete
                self._send({ action: 'test_print', printer_id: printerId });

                // For test_print, bridge sends print_complete with its own jobId
                // so we resolve on any next print_complete
                var handler = function (raw) {
                    var msg;
                    try { msg = JSON.parse(raw.data); } catch (e) { return; }
                    if (msg.event === 'print_complete' || msg.event === 'print_error') {
                        self._ws.removeEventListener('message', handler);
                        if (pendingJobs[jobId]) {
                            if (msg.event === 'print_complete') {
                                pendingJobs[jobId].resolve({ jobId: msg.job_id, success: true });
                            } else {
                                pendingJobs[jobId].reject(new Error(msg.error));
                            }
                            delete pendingJobs[jobId];
                        }
                    }
                };
                self._ws.addEventListener('message', handler);
            });
        },

        /**
         * Get bridge status.
         * @returns {Promise<object>}
         */
        getStatus: function () {
            var self = this;
            return new Promise(function (resolve, reject) {
                if (!self.connected) {
                    reject(new Error('Bridge not connected'));
                    return;
                }

                var handler = function (raw) {
                    var msg;
                    try { msg = JSON.parse(raw.data); } catch (e) { return; }
                    if (msg.event === 'status') {
                        self._ws.removeEventListener('message', handler);
                        resolve(msg);
                    }
                };
                self._ws.addEventListener('message', handler);

                setTimeout(function () {
                    self._ws.removeEventListener('message', handler);
                    reject(new Error('Status timeout'));
                }, 5000);

                self._send({ action: 'get_status' });
            });
        },

        /**
         * Send an OS-level notification via the bridge.
         * @param {string} title - Notification title
         * @param {string} body - Notification body text
         * @param {object} options - Optional: {icon, sound, urgency}
         * @returns {Promise<void>}
         */
        sendNotification: function (title, body, options) {
            var self = this;
            return new Promise(function (resolve, reject) {
                if (!self.connected) {
                    reject(new Error('Bridge not connected'));
                    return;
                }
                var sent = self._send({
                    action: 'send_notification',
                    title: title,
                    body: body || '',
                    options: options || {}
                });
                if (sent) resolve();
                else reject(new Error('Send failed'));
            });
        },

        /**
         * Disconnect from bridge.
         */
        disconnect: function () {
            this._intentionalClose = true;
            if (this._reconnectTimer) {
                clearTimeout(this._reconnectTimer);
                this._reconnectTimer = null;
            }
            if (this._ws) {
                this._ws.close();
            }
        },

        _generateId: function () {
            return 'job_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        }
    };

    window.ERPlora.bridge = bridge;

    // ─── HX-Trigger listener for server-side print routing ──────────────

    document.body.addEventListener('bridgePrint', function (e) {
        var detail = e.detail || {};
        if (bridge.connected && detail.printer_id) {
            bridge.print(detail.printer_id, detail.document_type, detail.data)
                .then(function () {
                    if (typeof showToast === 'function') {
                        showToast('Printed successfully', 'success');
                    }
                })
                .catch(function (err) {
                    console.error('[Bridge] Print failed:', err);
                    if (typeof showToast === 'function') {
                        showToast('Print error: ' + err.message, 'error');
                    }
                });
        } else {
            // Fallback: browser print
            console.log('[Bridge] Not connected — falling back to window.print()');
            window.print();
        }
    });

    // ─── Barcode event: dispatch as input to focused element ────────────

    document.addEventListener('erplora:bridge:barcode', function (e) {
        var value = e.detail.value;
        // If there's a focused input with data-barcode attribute, fill it
        var active = document.activeElement;
        if (active && (active.tagName === 'INPUT' || active.hasAttribute('data-barcode-target'))) {
            active.value = value;
            active.dispatchEvent(new Event('input', { bubbles: true }));
            active.dispatchEvent(new Event('change', { bubbles: true }));
        }
        // Also dispatch a custom HTMX-compatible event
        document.body.dispatchEvent(new CustomEvent('barcodeScan', {
            detail: { value: value, type: e.detail.type }
        }));
    });

    // ─── Auto-init on DOM ready (only if bridge is enabled) ─────────────

    if (BRIDGE_ENABLED) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function () { bridge.init(); });
        } else {
            bridge.init();
        }
    }
})();
