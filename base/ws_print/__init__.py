"""``/ws/print``: the print host's channel, the Hub's only WebSocket.

The device next to a printer (the ERPlora app) opens ``wss://<hub>/ws/print`` and drains the print queue of the
printers it reaches: it is told when a job arrives (``wake``), takes it (``claim`` → ``job``), prints it and says
how it went (``done``/``failed`` → ``ack``). The queue is printing's: this channel only calls its operations by
name (``printing.device.get``, ``printing.printer.get``, ``printing.job.claim``, ``printing.job.complete``,
``printing.job.fail``, ``printing.job.list``) with the context of the device's session, the same functions,
permissions and scope as the HTTP doors (``/api/printing/jobs/claim``…), and touches no model itself.

The wire is the old hub's, its messages and fields unchanged, because the native app and its print host are published
and still speak it::

    client                                                      hub
      {"type":"hello","session":…,"deviceId":…,"printers":[…]}  →
                     ← {"type":"ready","deviceId":…,"roles":[…],"heartbeatSeconds":30}
      {"type":"claim","role":"kitchen"}                         →
                     ← {"type":"job","jobId":…,"role":…,"documentType":…,"document":{…},"format":…,"attempts":1,…}
                     ← {"type":"idle","role":"kitchen"}       nothing waiting
      {"type":"done","jobId":…}                                 →  ← {"type":"ack","jobId":…,"confirmed":true}
      {"type":"failed","jobId":…,"error":…}                     →  ← {"type":"ack","jobId":…,"requeued":true}
      {"type":"beat"}                                           →  ← {"type":"beat","refreshed":2,"heartbeatSeconds":30}
                     ← {"type":"wake","role":"kitchen"}       a job was just queued for a role it prints
                     ← {"type":"error","code":…,"message":…}

What the new Hub changed, and nothing else:

- **The credential is the Hub's session cookie of the handshake**, the one every HTTP door takes (the Hub's
  login is the SaaS's and its session an HttpOnly cookie): ``hello.session`` is accepted and not
  read. It is checked at ``hello`` and again at every frame, so a session that ended (a logout) closes the socket
  at the device's next beat at the latest.
- **Who prints is printing's** (``PrintDevice``, the old hub's ``_print_host``, PRINTING-F18): ``hello`` reads the
  device's registration by its ``deviceId`` (``printing.device.get``), and the printers it reaches are the active
  ones of that registration, as in the old hub (``ready``'s roles come from the registry, never from the client). A
  device not set up here (or retired) is refused at its ``hello``. ``printers`` (ids it knows from
  ``printing.printer.list``) is what the session of whoever sets up the printers adds: with it, a device new here
  (never a retired one, refused with any session until it is set up again) or a printer not on its registration is
  taken, and its first claim of that role pairs them (printing's WORKBOOK, «Lo que hace ``base`` con
  ``/ws/print``»); with anybody else's, it changes nothing. The ``roles`` of
  ``ready`` are the functions of those printers (``receipt``, ``kitchen``, ``bar``, ``label``: the old stations),
  and ``claim`` takes the oldest job of that role's printers. A ``beat`` reads the registration again: a device
  retired, or whose printers were switched off, answers ``refreshed: 0`` and prints for nothing.
- **``job`` keeps every old field** and adds the rest of printing's hand-out, camelCased (``kind``,
  ``printerId``, ``target``, ``paperWidth``, ``copyDocument``, ``copies``, ``openDrawer``, ``html``…), which
  the app's print commands take.

Refusals, each with its own code. The fatal ones close the socket with ``4000 +`` their HTTP status; the rest
answer ``error`` and the socket stays:

==============================  =====  ==========================================================================
code                            close  when
==============================  =====  ==========================================================================
``not_found``                   4404   the Host is no hub's (the platform host included)
``base.hub_gone``               4410   the hub ended
``base.hub_preparing``          4503   the hub is still being prepared
``base.hub_suspended``          4402   the business is suspended for an unpaid invoice
``print.not_ready``             4400   a frame before ``hello``, or no ``hello`` within 15 s
``print.frame_too_large``       4413   a frame over 8 KiB (before anything is parsed)
``unauthenticated``             4401   no session, one that is not valid here, or one that ended (all but «no
                                       session» count towards ``base.rate_limited``)
``base.rate_limited``           4429   a session not valid here from a caller (its address, or its IPv6 /64) that
                                       had 10 refused within 5 minutes, until that window ends; a valid session
                                       is never refused for it
``print.device_required``       4400   ``hello`` without ``deviceId``
``print.host_not_registered``   4403   ``hello`` of a device not set up in printing (or retired), or that reaches
                                       no active printer of this hub
``permission_denied``           4403   the user may not print here (a session of another hub's member)
``app_inactive``                4404   printing is not on in this hub
``invalid_payload``             —      a frame that is not JSON, not of this protocol, or with a bad field
``print.role_not_hosted``       —      ``claim`` of a role this device does not print
``internal_error``              —      the hub failed; a job handed out comes back when its lease runs out
==============================  =====  ==========================================================================

A ``done`` or ``failed`` the queue does not take (another device has the job, or it is gone) is a plain
``confirmed: false`` / ``requeued: false``, as in the old hub: the device forgets it. A ``done`` re-sent after a
reconnect is taken from the device that held the job, whatever hand-out it was.

**Tenancy**: the hub is the Host's first label, checked against the registry by the gate the
HTTP doors pass (``base.middleware.HubHostRequiredMiddleware``), and every operation runs in its scope with the
session's user. The gate is heard again before every frame and every wake (the context's refresh,
``base.operations.HostClosed``): a hub that stops serving while the socket is open closes it with the same code. Every
synchronous step after the handshake runs in the hub's database (``use_hub``, ``_sync``) and its
wake in the live executor, which enters the hub itself (``base.operations.HubContextBuilder.enter``). The ``Origin``
must be the hub's own (cross-site WebSocket hijacking): anything else is refused at the handshake (Daphne answers
it 403).

**The wake** opens no ``LISTEN`` of its own: the socket keeps a stream of the process's live broker (the single
``LISTEN`` on the control database that ``/api/live`` uses) with one subscription per role to that role's newest
waiting jobs (``printing.job.list``), re-run after the COMMIT of every change of the queue. The ``wake`` is the old
hub's «a job was just queued for a role you host»: a result showing a job that the last one did not (queued,
retried, or sent back to the queue by another device) wakes the device for that role; one that only lost jobs (a
claim, a confirmation, a cancellation) does not, and neither does the job this device sent back itself with
``failed``, which waits for a retry, another device or the next wake (a printer out of paper would burn its
hand-outs). It runs as the device's user (its permissions re-read every time), on its hub's channel only, and never
carries the document, which travels only in the answer to ``claim``.

**The presence** (the old hub's heartbeat, ``print_hosts::heartbeat``):
the ``hello`` and every ``beat`` of a device that prints for something are news that it is there. The app that keeps
the print hosts says where that news goes with ``print_presence`` on its ``LiveAppConfig``: the name of a command of
its own whose input takes ``device``, which the socket runs with the device's id and context, as every other
operation here (``base.E006`` checks the declaration at start). Without one the socket tells nobody, as before. A
device that beats faster than it is told is told about no more than once every :data:`presence.PRESENCE_SECONDS`; a presence
that fails is logged and the socket goes on (the beat is answered and the device still drains): a write that did not
land costs one beat of news, never the printing.
"""

from . import (
    access as access,
    devices as devices,
    handshake as handshake,
    presence as presence,
    printing as printing,
    protocol as protocol,
    refusals as refusals,
    wake as wake,
)
