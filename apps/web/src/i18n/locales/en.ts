// Shell (chrome) strings in English. Mirrors es.ts key-for-key. Covers shell navigation, the
// topbar and the sidebar footer only — not per-view copy (that migrates screen by screen).
// One fact, one sentence (hub#1693). The connect screen wrote this line for hub#1689; the import,
// export and blueprint screens hit the SAME failure, so they say the SAME words. Declared once and
// referenced, not copied, so the two never drift apart.
const CLOUD_UNREACHABLE = 'Your hub could not reach erplora.com. Check the connection and try again.';

export default {
  // Language name shown in the Settings selector (rendered as-is). Required in every locale.
  _meta: { name: 'English' },
  nav: {
    general: 'General',
    account: 'Account',
    home: 'Home',
    employees: 'Employees',
    files: 'Files',
    // hub#365 — the money door, in the first person of the business. «Billing» names the ledger the
    // SaaS keeps; from inside the till what the owner asks is which plan they are on. One label for
    // two surfaces: this sidebar entry and the title of the page it opens.
    billing: 'My plan',
    apps: 'Apps',
    system: 'System',
    settings: 'Settings',
    apiDocs: 'API',
    // Account management, not a storefront (hub#479): the label names the task, never a price
    // or an offer, and it lands on THIS hub's plan page — the customer's own account.
    upgradePlan: 'Upgrade plan',
    upgradePlanError: 'We could not open your browser. Go to erplora.com to manage your plan.',
  },
  apiDocs: {
    title: 'API documentation',
    introTitle: 'Hub public API',
    introBody:
      'This documentation lists the available endpoints of the installed modules. To call them, create an API key in Users → API keys and paste it as a Bearer in “Authorize”.',
    loading: 'Loading documentation…',
    errorTitle: 'Could not load the documentation',
    errorBody: 'The API spec could not be fetched. Sign in and try again.',
    retry: 'Retry',
  },
  topbar: {
    back: 'Back',
    apps: 'My apps',
    appsEmpty: 'Your apps will show up here. Tap Apps to add the ones your business needs.',
    appsClose: 'Close',
    assistant: 'Assistant',
    // The way out to management (hub#364). It crosses a product boundary, so it names the
    // destination: `manageShort` is what is READ on the button, `manage` is the whole sentence the
    // accessible name reads out (hub#1400 — the entry used to be icon-only at the till). The short
    // one is the BRAND, so it is the same word in every language.
    manageShort: 'erplora.com',
    manage: 'Manage your business at erplora.com',
    manageError: 'We could not open your browser. Go to erplora.com to manage your business.',
    notifications: 'Notifications',
    noNotifications: 'All caught up. No notifications.',
    deadLettersTitle: 'Failed events',
    // Plurals via vue-i18n (`singular | plural`, picked by the `count`/`n` option): «1 event(s)» (hub#2212).
    deadLettersBody:
      '{count} event the relay could not deliver. Review and resend it. | {count} events the relay could not deliver. Review and resend them.',
    // Undrained printing (hub#987). It names the station because "printing is stuck" sends the
    // owner to look at four printers; "the kitchen is stuck" sends them to one.
    printingStalledTitle: 'Nothing is printing “{station}”',
    printingStalledBody:
      '{count} document waiting for {minutes} min. Check the till that prints there is on. | {count} documents waiting for {minutes} min. Check the till that prints there is on.',
    // Name of the overflow menu the toolbar folds into on a phone. It is icon-only, so this is the
    // only thing a screen reader has to announce it with.
    more: 'More options',
    configure: 'Configure',
    menu: 'Open menu',
    collapseMenu: 'Collapse menu',
    expandMenu: 'Expand menu',
  },
  sidebar: {
    profile: 'Profile',
    signOut: 'Sign out',
  },
  // Shell-of-the-installed-app copy. «Switch business» (hub#447): the app remembers ONE business
  // and this is the user's own door to another — an owner with two venues and one tablet, a till
  // being reassigned. Spoken as BUSINESS, never "hub": the reader owns a bar.
  shell: {
    changeHub: 'Switch business',
    changeHubTitle: 'Switch business?',
    changeHubBody:
      'This device will sign out of this business and show your list of businesses.',
    changeHubCancel: 'Cancel',
    changeHubConfirm: 'Switch',
  },
  // hub#1736 — the two buttons Ionic puts on EVERY selection dialog (`ion-select`). Its own
  // defaults are these same English literals, hardcoded in the library; the shell localizes them
  // once for the whole app, modules included (`lib/ionic-select-text.ts`).
  selectDialog: {
    ok: 'OK',
    cancel: 'Cancel',
  },
  // Feedback of the CSV buttons every `ok-data-table` carries (inventory#90). The import one talks
  // about the FILE being read, never about rows created: when it fires the module has not written
  // anything yet — it is about to show its preview, and its own report is what says what went in.
  // Plural via vue-i18n (`singular | plural`): the `n` in the options picks the branch.
  actionFeedback: {
    csvExported: 'CSV exported',
    csvExportedRows: 'CSV exported · {n} row | CSV exported · {n} rows',
    csvImported: 'CSV file read',
    csvImportedRows: 'CSV file read · {n} row | CSV file read · {n} rows',
  },
  // hub#1518 — a screen whose code never arrived (the connection dropped, or the file went stale
  // after a deploy). Said in plain words: nobody at a till knows what a "chunk" or a "module" is.
  viewLoad: {
    failedToast: 'That section could not be opened. Check your connection and try again.',
    blockedTitle: 'ERPlora could not finish opening',
    blockedBody:
      'The connection dropped while this screen was loading. Check your connection and try again.',
    blockedAction: 'Try again',
    // hub#1524 — the other cause of the same blank page: the screen's own code threw. Its own
    // words on purpose: telling someone the connection dropped when it did not sends them off to
    // restart a router that is working fine.
    brokenTitle: 'This screen could not be opened',
    brokenBody:
      'Something inside ERPlora failed while this screen was opening. Try again, and if it keeps happening, close ERPlora and open it again.',
    brokenAction: 'Try again',
    // hub#1590 — the same code failure, but with the hub already open. There is nothing blank to
    // rescue here, so it gets a toast and not the wall of text: covering a live till would lose
    // sight of the order being taken. Its own words for the same reason as `broken*` above.
    brokenToast: 'That section could not be opened. Something inside ERPlora failed — try again.',
  },
  // hub#1723 — an address this hub does not have. NOT an error the person made something wrong
  // with: nine times out of ten it is an old link or a guess at the name of an app, so the words
  // point at the address and then at the way out, without blaming anybody.
  notFound: {
    title: 'This page does not exist',
    body: 'The address you opened is not part of this hub. It may be an old link, or a guess at the name of an app — your apps open from the menu or from Home.',
    action: 'Go to Home',
  },
  // The installed app is older than the one we publish (hub#400). It is called ERPlora, never
  // "the app": "apps" is already the word for the things you add to your business (ADR-0254), and
  // one noun for two things is how a cashier ends up uninstalling the till.
  installQr: {
    title: 'Open on your phone',
    hint: 'Scan the code. To keep it there, add it to your home screen from your browser menu.',
  },
  appUpdate: {
    available: 'Update ERPlora ({version})',
    confirmTitle: 'Update ERPlora',
    confirmBody:
      'Your browser opens to download version {version}. Nothing installs on its own: finish serving, then close ERPlora and open what you downloaded.',
    action: 'Download',
    cancel: 'Not now',
    failed: 'We could not open your browser. Go to erplora.com to get the new version.',
    android: {
      confirmBody:
        'The ERPlora listing opens on Google Play. Google Play installs version {version}: there is no file to download or open.',
      action: 'Open Google Play',
      failed: 'We could not open Google Play. Search for ERPlora there to get the new version.',
    },
  },
  assistant: {
    confirmTitle: 'The assistant wants to run an action',
    confirmCancel: 'Cancel',
    confirmRun: 'Run it',
    title: 'Assistant',
    empty: 'Ask me about your sales, your inventory or anything about your business.',
    emptySetup: 'Review how your business is set up. Pick an option or type your question.',
    suggestWhatsMissing: 'What needs configuring?',
    suggestHowTo: 'How do I set up',
    goTo: 'Go to',
    placeholder: 'Type a message…',
    send: 'Send',
    stop: 'Stop',
    close: 'Close',
    noReply: '(no reply)',
    error: 'Could not reach the assistant.',
    // hub#1738 — the assistant service ANSWERED and turned the turn down (in PRE, with no LLM
    // credential configured). Saying «could not reach» there sends the owner to check a network
    // that is fine and to report a problem that is not theirs: nothing on their side is broken,
    // and nothing they do changes it.
    unavailable: 'The assistant is not available right now. Try again in a few minutes.',
    // saas#1540 — running out of messages is a PLAN state, not an outage. Saying «could not
    // reach» turns the one conversion moment of the free tier into a product failure.
    quotaTitle: 'You have used all your assistant messages',
    quotaUsed: 'Plan {tier} — {used} of {limit} messages this month.',
    quotaCta: 'See plans',
    includedInPlan: 'Included in your {plan} plan.',
    includedInHubPlan: 'Included in your plan.',
    upgradeHubPlan: 'Upgrade your plan',
    planOpenFailed: 'Your plan page could not be opened in your browser. Try again.',
    // hub#1183 — knowing the limit only once it is spent is knowing it at the worst possible
    // moment. From 80% on, the drawer says what is left and when it comes back.
    quotaRemaining: 'Plan {tier} — {remaining} of {limit} messages left this month.',
    quotaResets: 'They come back on {date}.',
    // hub#1259 — contracting the plan is the admin door (hub#1254). A cashier who presses this
    // button only gets a 403 and a generic error: worse than not seeing it, and worse than
    // reading who to ask.
    quotaAskAdmin: 'Ask the owner of the business to upgrade the assistant plan.',
    quotaManagedInAccount: "The assistant's plan is upgraded from your ERPlora account at erplora.com.",
    plansTitle: 'Choose a plan',
    plansConfirm: 'Go to payment',
    planOption: '{name} — {price} €/month',
    plansUnavailable: 'There are no plans to upgrade to right now.',
    checkoutOpenFailed: 'The payment page could not be opened in your browser. Try again, and if it keeps failing, update the ERPlora app.',
    attach: 'Attach file',
    attachRemove: 'Remove attachment',
    attachImage: 'image',
    attachTooLarge: 'The file is too large.',
    mic: 'Dictate by voice',
    micStop: 'Stop recording',
    micDenied: 'Microphone access was denied. Allow it in your browser to dictate.',
    micUnsupported: 'This browser cannot record audio.',
    micFailed: 'The audio could not be transcribed.',
    report: 'Report an issue',
    reportTitle: 'Report this response',
    reportHint:
      'If this assistant response seems inappropriate or harmful, send it to us and we will review it.',
    reportPlaceholder: 'Comment (optional)',
    reportConfirm: 'Report',
    reportSent: 'Thank you, we received your report.',
    reportError: 'The report could not be sent. Please try again.',
    // hub#1038/#1039/#1048 — said by the RUNTIME, never by the model: the turn's receipts did
    // not back what the answer claimed. Shown as a notice on the message itself.
    claimedWithoutEffect:
      'The assistant said it made a change, but no action was carried out. Nothing has been modified.',
    unsourcedId:
      'This answer shows an identifier the assistant did not actually read. Do not rely on it.',
    unknownRoute: 'This answer points at a screen that does not exist here.',
    // hub#1040 — when the app cannot name its own action we say so, rather than filling the
    // gap with the internal command name (hub#363: that is our vocabulary, not the counter's).
    confirmUnnamedAction: 'An action this app cannot name',
    // hub#1042 — destructive actions ask for more than a click. Typing the COUNT is what
    // forces reading the sentence that says how many are about to go.
    confirmDestructive: 'This cannot be undone from the screen. Type {expected} to confirm.',
    confirmDestructiveWord: 'DELETE',
    confirmBulkAffected: 'You are about to delete {count} record. | You are about to delete {count} records.',
    confirmBulkUnknown:
      'I cannot tell how many records this would delete, so I will not do it from here. Open the screen, where you can see them.',
  },
  // What the user is told after pressing «download», wherever they pressed it (hub#480). Inside the
  // installed app there is no download shelf and no notification, so if we say nothing, nothing is
  // said at all.
  // hub#988 — the badge read off the device's own NFC reader. Two sentences, because only these
  // two are worth interrupting for: a device with no reader says nothing at all (the USB reader
  // keeps working exactly as before, so there is nothing for the user to do about it).
  badge: {
    nfcDisabled: 'NFC is switched off on this device. Turn it on to read cards by tapping them.',
    nfcRandomUid:
      'This card gives a different number every time it is read, so it cannot be used as a badge. Try another card.',
  },
  download: {
    savedTo: 'Saved to {path}',
    noPlaceToSave: 'This app cannot save files on a phone or tablet. Open your business in a browser to download it.',
    failed: 'The file could not be downloaded.',
  },
  files: {
    // hub#1776 — the stable codes the media doors send (`crates/server/src/media.rs`). The shared
    // `runtimeErrors` already says `cloud_unreachable`, `cloud_rejected`, `cloud_unreadable` and
    // `hub_not_enrolled`; these are the reasons that belong to Files. Only the ones that retrying
    // can fix say to try again.
    errors: {
      unauthorized: 'Your session has expired. Sign in again and retry.',
      forbidden: 'Only an owner or an administrator can change the files.',
      not_found: 'That file or folder no longer exists. Refresh the list.',
      media: {
        no_files: 'No file was selected to upload.',
        busy: 'Too many files are being handled right now. Try again in a moment.',
        too_large: 'That file is too large to open here. Download it instead.',
        invalid_name: 'That name is not valid. Use a name without slashes or dots on their own.',
        missing_path: 'Choose a file or folder first.',
        same_path: 'The file is already in that folder.',
        move_into_itself: 'A folder cannot be moved inside itself.',
        read_only_folder: 'This folder belongs to an app that does not allow changing its files.',
      },
    },
    title: 'Files',
    subtitle: "Everything stored in the media folder: app attachments, logs and activity.",
    upload: 'Upload file',
    import: 'Import',
    search: 'Search files…',
    folders: 'Folders',
    space: 'Space',
    empty: 'No files',
    download: 'Download',
    delete: 'Delete',
    open: 'Open',
    newFolder: 'New folder',
    folderName: 'Folder name',
    createFolder: 'Create folder',
    cancel: 'Cancel',
    retry: 'Retry',
    loadErrorTitle: 'Files could not be loaded',
    loadErrorBody: 'Check the connection and try again.',
    permissionDenied: 'Only an administrator can modify files.',
    uploadSuccess: 'Files uploaded.',
    uploadError: 'Files could not be uploaded.',
    openError: 'The file could not be opened.',
    deleteTitle: 'Delete file',
    deleteBody: 'You are about to delete “{name}”. This cannot be undone.',
    deleteSuccess: 'File deleted.',
    deleteError: 'The file could not be deleted.',
    folderCreated: 'Folder created.',
    folderError: 'The folder could not be created.',
    rename: 'Rename',
    newName: 'New name',
    renameSuccess: 'Renamed.',
    renameError: 'It could not be renamed. This folder may be read-only.',
    deleteFolderTitle: 'Delete folder',
    deleteFolderBody: 'You are about to delete “{name}” and everything inside it. This cannot be undone.',
    // hub#2197 — the move toast names the folder the file went to; `{folder}` is its last segment.
    moveSuccess: 'Moved to “{folder}”.',
    moveError: 'It could not be moved. The destination folder may be read-only.',
    // The rest of the labels `ok-file-manager` renders; without them it shows its built-in Spanish.
    move: 'Move to…',
    renameFolder: 'Rename folder',
    deleteFolder: 'Delete folder',
    noLimit: 'No limit',
    close: 'Close',
    previewZoomIn: 'Zoom in',
    previewZoomOut: 'Zoom out',
    previewErrorTitle: 'The file could not be opened',
    previewErrorBody: 'The file contents did not come back. Check the connection and try again.',
    previewUnsupportedTitle: 'No preview available',
    previewUnsupportedBody: 'This file type cannot be shown here. Download it to open it with an app on your device.',
    previewPdfTruncated: 'Showing the first {shown} of {total} pages. Download the file to read it in full.',
  },
  // The configuration checklist — the dashboard surface of `hub.setup.status` (hub#372).
  // `items.<key>` covers the CORE items only: a core item's key IS its i18n key, while a module's
  // title travels in English inside its manifest and is used as-is (setup-status.md §7).
  // hub#1743 — the shell-wide band for «there is no network right now». Says the CONSEQUENCE, not
  // the state: «offline» on its own reads as a setting somebody turned on. Nothing here names a
  // module or a screen, because the outage is not about any of them.
  // hub#2143 — painted before the shell mounts, when the hub did not answer its boot context.
  boot: {
    unreachable: {
      title: 'We cannot connect to your business',
      body: 'ERPlora is not answering. Check that this device is connected to the internet and try again. If it keeps happening, the problem may be on our side.',
      retry: 'Try again',
    },
  },
  offline: {
    title: 'No internet connection',
    body: 'Anything that needs the internet — loading screens, syncing, sending invoices — will not work until it is back. This notice disappears on its own.',
    // hub#2085 — the browser says it has a network, but ERPlora does not answer. Names what is
    // known and both places the fault can be; never claims «no internet», which may be false here.
    hubTitle: 'ERPlora is not responding',
    hubBody: 'Your device seems to be online, but ERPlora is not answering: it may be your internet connection or a problem on our side. Anything that needs it — loading screens, syncing, sending invoices — will not work until it is back. This notice disappears on its own.',
  },
  setup: {
    title: 'Finish setting up your business',
    progress: '{done} of {total} done',
    viewAll: 'View all',
    viewLess: 'Show less',
    configure: 'Set up',
    review: 'Ask the assistant',
    doneLabel: 'Done',
    // The three levels. Only the ⛔ one may name a refusal, because it is the only one with a
    // dispatcher behind it (`enforce_fiscal_precondition`, ADR-0203) — and the refusal it names is
    // the INVOICE: a sale without the fiscal identity still closes. 🔴 is a module saying its own
    // configuration matters, which the core never lets become a condition for selling, so it says
    // how much it matters and stops there (hub#1726). Guard: `i18n/setup-level-copy.test.ts`.
    levelLegal: 'Needed to invoice',
    levelFunctional: 'Important',
    levelRecommended: 'Recommended',
    // The third state: OUR breakdown, not the user's task. It must not read as a chore.
    unavailableLabel: 'Not available yet',
    unavailableHint: 'This one is on us: there is nothing on your side to do yet. We are on it.',
    // A wall that is not yours to bring down (hub#435). It says WHO can — not the name of a
    // permission — because a blocker with no owner leaves the user with nowhere to go.
    delegatedHint: 'An administrator has to set this up.',
    inheritedHint: 'It came from the template you used. Worth a look — your room and your prices are your own.',
    // hub#1905 — the item is pending on a switch in Settings → Permissions, not on its own settings.
    missingPermissionHint: 'This app needs a permission you have not granted yet. Without it, it cannot do its job.',
    grantPermission: 'Grant permission',
    completeTitle: 'Your business is ready',
    completeBody: 'Everything on the checklist is done.',
    // The hero card of a business with no apps yet (hub#368). Its whole job is the FIRST choice, so
    // it says what one press does AND what it leaves for the owner: a template brings the apps and
    // the catalogue of a trade, never the details of THIS business (ADR-0195 §4/§5).
    hero: {
      title: 'Start from a business like yours',
      body: 'Pick the closest one and we set up its apps and its catalogue in one go. You will still have to add your own details afterwards.',
      use: 'Use this one',
      more: 'See all templates',
      // The way out of the offer (hub#1120). The card outlives the business being empty, so
      // it has to be closable from the offer itself — «not now», never «no thanks»: the
      // catalogue is still one tap away in Settings › Data.
      dismiss: 'Not now',
      working: 'Setting up «{name}»…',
      readyTitle: 'Your apps and your catalogue are in',
      readyBody: 'What is left is what only you can answer: the details of your business. You have them on the list below.',
      // hub#535 — a template also brings SAMPLE data (customers, appointments). Said BEFORE the
      // click, because after it the agenda is full of bookings that are not the owner's; and said
      // AGAIN after, pointing at the door that already removes them (undo an import, ADR-0170).
      // What we do NOT do is write a relative-date engine so the sample bookings are always in the
      // future: expensive, small problem, and already solved by that door.
      sampleData: 'It also brings sample data — customers, appointments — so you can see how everything works.',
      sampleDataUndo: 'The sample data is there for you to look around. You can remove it whenever you like from Settings › Data.',
      partialTitle: 'Almost: something did not go in',
      // A purchase decision, never a breakage (ADR-0060, hub#409): it names what to add and says
      // where, instead of painting a red error over a plan the owner simply has not bought.
      blocked: 'These have to be added to your plan first: {apps}',
      failed: 'Something else did not go in. You can see the detail and try again in Settings › Data.',
      // hub#751 — the card already knows WHICH apps broke, so it names them: «something else» sent
      // a hairdresser to hunt for a needle. The generic line above is left for the case where the
      // failure is not an app and no name would mean anything to her.
      failedApps: 'These did not go in: {apps}. You can see the detail and try again in Settings › Data.',
      // hub#899 — the other half of the same complaint. When what broke was a SECTION of the
      // template there was no app to name, so the card fell back to «something else did not go in»:
      // two «somethings» in one card, at the minute she is checking whether her business is inside.
      // She could not tell a missing service from a missing till, so she could not decide whether to
      // start working or import again. Each part is named below, in her words and never by our key.
      failedParts: 'This did not go in: {parts}. You can see the detail and try again in Settings › Data.',
      failedAppsAndParts:
        'These did not go in: {apps}. Nor did {parts}. You can see the detail and try again in Settings › Data.',
      // The parts of the hub a template carries, as the owner would name them. They read inside a
      // sentence («This did not go in: the images»), which is why they are lower case and not the
      // table headings the full report uses.
      partSettings: 'the settings of the business',
      partTeam: 'the people',
      partRoles: 'the roles and what each one may do',
      partFiscal: 'the tax details',
      partMedia: 'the images',
      // `modules/<id>` is the app's DATA — its catalogue, its services, its prices — and the app
      // itself may be installed and running. Saying the app did not go in would send her to
      // reinstall something that is already there.
      partAppData: 'the data of {app}',
      notStartedTitle: 'That template could not be opened',
      notStartedBody: 'Nothing changed in your business. Try again, or load it from Settings › Data.',
      interruptedTitle: 'The set-up did not finish',
      // We do NOT claim it changed nothing: half of it may already be in, and saying otherwise
      // would send the owner to press again on top of it.
      interruptedBody: 'Part of it may already be in. Check it in Settings › Data before trying again.',
      continue: 'Continue',
      retry: 'Try again',
      // hub#763 — the door to the report the sentences above name. The report survives navigation
      // now, so this button leads somewhere instead of to an empty template catalogue.
      seeReport: 'See the report',
    },
    // The blocking strip (hub#374): the surface for the screens the checklist is not on. It says the
    // CONSEQUENCE, not the severity — ⛔ means the runtime refuses the document, so that is what it
    // announces. It never says "error": nothing is broken, something is missing.
    blocking: {
      title: 'You cannot issue invoices yet',
      body: 'No ticket or invoice can be issued until this is set up:',
    },
    items: {
      apps: {
        title: 'Your apps',
        description: 'Install at least one business app so your till has something to sell.',
      },
      business_identity: {
        title: 'Your business details',
        description: 'Legal name and tax id: without them you cannot issue an invoice.',
      },
      printer: {
        title: 'Set up your printer',
        description: "Register the device that prints your customers' receipts, so the first sale comes out on paper.",
      },
      team: {
        title: 'Your team',
        description: 'Add the people who will use the till, each with their own way in.',
      },
    },
  },
  dashboard: {
    // Contextual greeting by time of day (zone 1 — header). It stands in for the BUSINESS NAME
    // while the hub has none yet, so nobody is interpolated: greeting a person here is what put an
    // account address in the `<h1>` (hub#366).
    greetingMorning: 'Good morning',
    greetingAfternoon: 'Good afternoon',
    greetingEvening: 'Good evening',
    // Today label; the full date is formatted by the browser locale.
    todayLabel: 'Today',
    loading: 'Loading…',
    tabSummary: 'Summary',
    tabActivity: 'Activity',
    activityDate: 'Date',
    activitySale: 'Sale',
    activityCustomer: 'Customer',
    activityMethod: 'Method',
    activityAmount: 'Amount',
    activityStatus: 'Status',
    activitySearchPlaceholder: 'Search activity…',
    // Status badge of an activity row; it agrees with «sale» — the row is a sale (hub#863).
    activityStatusCompleted: 'Completed',
    activityStatusPending: 'Pending',
    widgets: 'Widgets',
    loadingWidgets: 'Loading widgets…',
    customizePanel: 'Customize panel',
    closePanel: 'Close',
    presetsTitle: 'Start from a preset',
    activeWidgets: 'Active · drag to reorder',
    availableWidgets: 'Available',
    emptyPanel: 'Empty panel. Tap ⋮ to add widgets.',
    noWidgets: 'No installed app offers widgets yet.',
    widgetEmpty: 'No data',
    widgetError: 'Unavailable',
    // «My apps» card (hub#367): the launcher of the panel. Its title reuses `topbar.apps` — same
    // name for the same thing on both surfaces.
    appsAdd: 'Add apps',
    appsEmpty: 'Your apps will show up here. Add the ones your business needs.',
    // hub#894 — said INSTEAD of `appsEmpty` when the list could not be loaded. It never claims the
    // hub is empty, and it names reloading as the move, because the apps are still installed.
    appsLoadError: 'Could not load your apps. Reload the page; if it keeps failing, sign in again.',
    // hub#1722 — the skeleton tiles are decorative, so this is the sentence a visually hidden status
    // line beside the grid carries for anyone not looking at it: the placeholders say it on screen.
    appsLoading: 'Loading your apps…',
    blueprintTitle: 'Set up your business',
    blueprintBody: 'Load a template for your business or restore a backup to get started.',
    blueprintCta: 'Set up',
    // Zone 4 — what the hub says about itself. The badge's own copy lives in `system.health.*`
    // (hub#375); «System connected/disconnected» is gone on purpose — it was a verdict about
    // everything drawn from a probe that only ever knew about the printer host.
    openSystem: 'View system',
    // hub#1197 — on a phone the grid folds after two rows; this is the tile that leads to the rest,
    // the same catalogue ＋ Add apps already opens (`/apps`).
    appsViewAll: 'View all apps',
  },
  profile: {
    title: 'My profile',
    subtitle: 'Your identity and personal preferences in this business.',
    accountTitle: 'Account details',
    preferencesTitle: 'Preferences',
    name: 'Name',
    firstName: 'First name',
    lastName: 'Last name',
    email: 'Email address',
    role: 'Role in this business',
    accountType: 'Account type',
    cloudAccount: 'erplora.com account',
    cloudAccountError: 'Your account page could not be opened in your browser. Go to erplora.com to manage it.',
    localAccount: 'Local user of this business',
    unavailable: 'Unavailable',
    defaultRole: 'User',
    roleOwner: 'Owner',
    roleAdmin: 'Administrator',
    roleManager: 'Manager',
    roleEmployee: 'Employee',
    language: 'Language',
    languageDesc: 'Saved for you. If you do not pick one, the business language is used.',
    appearance: 'Appearance',
    appearanceDesc: 'Choose the mode and palette you prefer.',
    useHubLanguage: 'Use the business language',
    useHubAppearance: 'Use the business appearance',
    changePhoto: 'Change photo',
    removePhoto: 'Remove',
    saveProfile: 'Save my details',
    saving: 'Saving…',
    saved: 'Profile saved',
    saveError: 'Could not save the profile',
    loadError: 'Could not load the profile',
    photoSaved: 'Photo updated',
    photoError: 'Could not save the photo. Use a JPG, PNG or WebP up to 2 MB.',
    manageTitle: 'Account management',
    manageCloud:
      'You can edit your own details here. It is still your erplora.com account.',
    manageLocal:
      'This identity belongs to this business only. Other businesses are neither known nor shown here.',
    manageInSaas: 'Manage account at erplora.com',
    pinTitle: 'PIN',
    pinDesc: 'The PIN you use at the till. Change it whenever you want — nobody else needs to.',
    pinSetupDesc: 'You do not have a PIN yet. Set one to be able to sign in at the till too.',
    currentPin: 'Current PIN',
    newPin: 'New PIN',
    confirmPin: 'Repeat the new PIN',
    changePin: 'Change PIN',
    setPin: 'Set PIN',
    pinSaved: 'PIN updated',
    pinMismatch: 'The two PINs do not match.',
  },
  // hub#358 — «this device»: whether this terminal asks who is using it. The copy says the
  // CONSEQUENCE of each mode, never its technical name: the owner of a bar has to be able to tell,
  // from the sentence alone, that one of the two means "whoever picks this up is already signed in
  // as me". Source language; `es.ts` carries the translation.
  deviceMode: {
    title: 'This device',
    intro: 'How this device asks who is using it. Each device in your business decides separately.',
    shared: 'Shared — a till or tablet several people use',
    sharedConsequence:
      'It asks for a PIN when somebody signs in and forgets it at the end of the shift, so every sale is attributed to whoever made it.',
    personal: 'Personal — a device only you use',
    personalConsequence:
      'It stays signed in and never asks for a PIN: anyone who picks it up is already you. Only choose this for a device nobody else touches, and change it back if you lose it.',
    adminOnly: 'Only an administrator can change how this device signs people in.',
    saveError: 'This device could not be changed. Check the connection and try again.',
  },
  // hub#455 — the "somebody walked off with the tablet" screen. Two rules the copy follows: it says
  // WHEN the cut-off takes effect (right away — the owner has just reported a theft and needs to
  // know), and it does not promise more than the hub delivers (removing a device is not a ban:
  // anybody with an account can sign in on it again). No "hub" anywhere — ADR-0254.
  devices: {
    // hub#1697 — the door answers a stable code next to English prose written for the log
    // (`devices.rs`). The code is what the person gets a sentence for; the prose stays in the log.
    errors: {
      device_name_too_long: 'That name is too long. Use a shorter one and save again.',
      device_not_found: 'That device is no longer registered here. Refresh the list.',
      // hub#1702 — the door's auth refusals. A dead session is fixed by signing in again; a role
      // without the permission is not, so the second sentence never suggests it.
      unauthorized: 'Your session has expired. Sign in again and retry.',
      forbidden: 'Only an owner or an administrator can manage the devices.',
    },
    title: 'Devices',
    intro:
      'The devices somebody has signed in on. If you lose one, remove it here: its session closes right away and it can no longer sign in with a PIN.',
    thisDevice: 'The one you are using',
    unnamed: 'Unnamed device',
    rename: 'Name this device',
    nameLabel: 'Name it after where it is: Counter, Kitchen, Office laptop',
    save: 'Save',
    lastSignedInBy: 'Last signed in by {who}',
    renameError: 'This device could not be renamed. Check the connection and try again.',
    empty: 'Nobody has signed in on a device yet.',
    inUse: 'In use right now',
    lastUsed: 'Last used {when}',
    neverUsed: 'Added {when}, never used since',
    openUntil: 'Its session stays open until {when}',
    modeShared: 'Asks for a PIN',
    modePersonal: 'Stays signed in',
    revoke: 'Remove this device',
    cancel: 'Keep it',
    confirm: 'Remove this device?',
    confirmCurrent:
      'This is the device you are using: removing it closes your session and you will have to sign in again.',
    consequence:
      'Its session closes right away. To use it again, somebody has to sign in on it with their account.',
    adminOnly: 'Only an administrator can remove a device.',
    loadError: 'The devices could not be loaded. Check the connection and try again.',
    revokeError: 'This device could not be removed. Check the connection and try again.',
  },
  // hub#359 — the dial the OWNER turns, on top of the device mode above. Every option says what it
  // does to the business, never what it is called: "never" means nothing to a shopkeeper, "whoever
  // opened the till is the name on every sale" does. The hour and the twelve hours are spelled out
  // because the hub really does enforce them, and a promise it cannot keep would be worse than no
  // setting at all.
  pinPolicy: {
    lengthTitle: 'PIN length',
    lengthDigits: '{n} digits',
    lengthConsequence: 'Everybody types the same number of digits, which is what lets the keypad sign you in on the last one instead of asking you to confirm. PINs already in use keep working until their owner changes them.',
    title: 'PIN pad',
    intro:
      'Whether the PIN pad is shown and asks who is at the till. It applies to the whole business — each device also decides for itself, above.',
    showPinpad: 'Show PIN pad',
    onConsequence:
      'Staff pick their name and type their PIN, so every sale carries the name of whoever made it.',
    offConsequence:
      'Nobody types a PIN. Whoever opened the till in the morning is the name on every sale until the shift ends, whoever actually made them — so you cannot tell who sold what, or who gave a discount. Staff who only have a PIN and no account will not be able to sign in.',
    idleTitle: 'Ask again after inactivity',
    idleMinutes: '{n} min',
    idleUntilSignOut: 'Until you sign out',
    idleMinutesConsequence:
      'A till nobody has touched for {n} minute signs the user out and shows the PIN pad, so the next sale carries the next person’s name. | A till nobody has touched for {n} minutes signs the user out and shows the PIN pad, so the next sale carries the next person’s name.',
    idleUntilSignOutConsequence:
      'The till never locks itself for inactivity: the session stays open until whoever signed in signs out, or until the device says it expires.',
    adminOnly: 'Only an administrator can change whether it asks.',
    saveError: 'This could not be changed. Check the connection and try again.',
  },
  // El otorgamiento de representación (hub#817): la pantalla donde el cliente FIRMA que ERPlora
  // puede remitir sus registros VERI*FACTU en su nombre. El TEXTO del Anexo I no está aquí: lo
  // sirve el runtime, que es quien lo archiva — una copia en el bundle sería el mismo documento
  // diciendo dos cosas. Y va en español pase lo que pase: es un instrumento dirigido a la AEAT.
  settings: {
    hubWide: 'General settings',
    currency: 'Currency',
    currencyDesc: 'Your business currency for prices and totals',
    hubLanguage: 'Business language',
    hubLanguageDesc: 'Default language for anyone who has not picked their own',
    saved: 'Settings saved',
    saveError: 'Could not save settings',
    // A refusal the runtime explains, keyed by its STABLE error code (hub#684). The runtime's own
    // message is written in English for the log; what the person in front of the screen reads has
    // to be their language, so the code — not the message — is what travels.
    saveRefused: {
      demo_fiscal_environment_locked:
        'A demo always stays in the tax authority’s test environment. Create your own business at erplora.com to file for real.',
      business_tax_id_frozen:
        'The tax id can no longer be changed: this business has already issued under it.',
      hub_country_frozen:
        'The country can no longer be changed: this business already files under its tax rules. Get in touch with us if the business really did move.',
      // hub#1088: one per refusal reason — a mistyped control character is retyped; "this is
      // no official shape at all" is a different conversation.
      invalid_tax_id_type: 'The tax id must be text.',
      tax_id_too_long:
        'The tax id is too long: the tax authority’s own limit is 20 characters.',
      invalid_tax_id_format: 'That is not shaped like a tax id: DNI (12345678Z), NIE (X1234567L), CIF (B12345674), or a foreign identifier with its country prefix (FR123456789).',
      invalid_tax_id_control: 'The tax id’s control letter or digit is not the right one: check it and type it again.',
    },
    timezone: 'Timezone',
    timezoneDesc: 'Timezone for dates and times',
    timezoneAuto: 'Automatic (from the country)',
    timezoneAutoNow: 'Automatic · {zone}, {time}',
    timezoneOptionNow: '{zone} · {time}',
    country: 'Country',
    countryDesc: 'Country for regional settings',
    countrySpain: 'Spain',
    countryPortugal: 'Portugal',
    theme: 'Theme',
    themeDesc: 'Interface appearance mode',
    themeSystem: 'System (auto)',
    themeLight: 'Light',
    themeDark: 'Dark',
    themePalette: 'Theme palette',
    paletteFollowHub: 'Use the business palette',
    hubPalette: 'Default palette',
    hubPaletteDesc: 'The palette seen by users who have not picked their own',
    saveChanges: 'Save changes',
    showApiDocs: 'Show API documentation',
    showApiDocsDesc: 'Adds an internal page with the API reference (Swagger) for integrations',
    hardware: 'Hardware',
    // The counter's hardware, said as what it is. `bridgeDesc` named «ERPlora Bridge», an app
    // ADR-0196 deleted, and sat next to a hardcoded «Disabled» that was wrong inside the app.
    // Named after the CAPABILITY, not after one vertical's kit: an ERP without a till has no cash
    // drawer, and «Printer and cash drawer» reads as «not for me» to everyone who is not a shop.
    hardwareTitle: 'Local and network access',
    hardwareDesc: 'Printers, scanners and other devices on this computer or its network',
    hardwareReady: 'Available here',
    hardwareAppOnly: 'Only from the installed app',
    // «Start on login» (ADR-0204 §7, hub#389). Desktop app only; the OS keeps the state.
    startOnLogin: 'Start on login',
    startOnLoginDesc:
      'Open ERPlora when you sign in to this computer, so tickets always have somewhere to print',
    startOnLoginError: 'Could not change the start on login setting',
    disabled: 'Disabled',
    fiscalIdentity: 'Business details',
    fiscalIdentityDesc: 'Taxpayer identity (used by invoices and the fiscal apps).',
    fiscalNif: 'Tax ID (NIF/VAT)',
    fiscalName: 'Legal name',
    businessStreet: 'Street',
    businessStreetNumber: 'Number',
    businessPostalCode: 'Postal code',
    businessCity: 'City',
    businessAddressLegacy: 'Current address: {address}. Fill in the fields above to replace it.',
    fiscalAddress: 'Fiscal address',
    shareWithErplora: 'Use these details for my ERPlora invoice too',
    shareWithErploraDesc: 'Sends your legal name, tax id and address to ERPlora so its invoices to you carry them. Your business keeps invoicing its own customers with these same details — nothing else is shared.',
    shareWithErploraDone: 'Details shared with ERPlora.',
    shareWithErploraError: 'Could not share the details with ERPlora.',
    shareWithErploraNeedsTaxId: 'Fill in the tax id first.',
    // One question, two EXCLUSIVE answers (ADR-0320 §1 — hub#1314): either the business files with
    // its own certificate, or ERPlora files on its behalf with the signed grant. Never both.
    defaultVat: 'Default VAT',
    defaultVatDesc: 'Rate applied to new products',
    vatGeneral: '21% (standard)',
    vatReduced: '10% (reduced)',
    vatSuperReduced: '4% (super-reduced)',
    taxRegime: 'Tax regime',
    taxRegimeDesc: 'Invoicing regime',
    regimeGeneral: 'General regime',
    regimeEquivalence: 'Equivalence surcharge',
    receiptTemplate: 'Printers and receipt',
    receiptTemplateDesc: 'Add your printer and set up the printed and digital receipt',
    receiptTemplateMissing: 'Install the Printing app to add your printer and set up your receipt',
    tabHub: 'General',
    tabBusiness: 'Business',
    tabTickets: 'Receipts',
    tabPermissions: 'Permissions',
    tabData: 'Data & backups',
    dataImport: 'Import',
    dataExport: 'Export',
    // Reset del hub (ADR-0170). Inglés = idioma canónico del Hub (ADR-0055).
    dataReset: 'Reset',
    resetIntro:
      'Permanently deletes the data you select. This cannot be undone — export a backup first if in doubt.',
    resetExportFirst: 'Export a backup first',
    resetImportsTitle: 'Undo an import',
    resetImportsHint: 'Removes only what that blueprint brought in. Anything you created afterwards is kept.',
    resetSectionsTitle: 'Or delete by section',
    resetUndo: 'Undo',
    resetUndoTitle: 'Undo “{name}”',
    resetUndoBody:
      '{n} row brought in by this blueprint will be deleted. What you created afterwards is kept. | {n} rows brought in by this blueprint will be deleted. What you created afterwards is kept.',
    resetUndoEdited: 'You changed {areas} after importing. Undoing keeps only your changes there: what this blueprint replaced will not come back.',
    resetUndoNotRestored: 'In {areas} only your own changes were kept: what the blueprint had replaced did not come back. Check that screen.',
    // Pluralización vue-i18n (`singular | plural`): sin ella, una sección con 1 elemento leía
    // «1 rows» (hub#765). El `n` que pasa la llamada elige la forma.
    resetRows: '{n} row | {n} rows',
    resetSubmit: 'Reset the business',
    resetDeleted: '{n} row deleted | {n} rows deleted',
    resetConfirmTitle: 'This cannot be undone',
    resetConfirmBody: '{n} row will be permanently deleted: | {n} rows will be permanently deleted:',
    resetConfirmPlaceholder: 'business name',
    resetCancel: 'Cancel',
    resetConfirm: 'Delete permanently',
    reset_hub_settings: 'General settings',
    reset_hub_users: 'Employees',
    reset_media: 'Files and images',
    reset_fiscal: 'Tax configuration',
    reset_roles: 'Active roles',
    reset_print_queue: 'Print queue',
    permissionsTitle: 'App permissions',
    permissionsDesc: 'Grant or revoke the permissions each app asks for (internet access, certificate, printer, notifications, manage automations). For safety, everything is denied until you grant it.',
    permissionsAdminOnly: 'Only an administrator can change permissions.',
    permissionsNoModules: 'No installed app asks for permissions.',
    permissionsModuleNone: 'This app asks for no permissions.',
    permissionsLoadError: 'Could not load permissions.',
    permissionGranted: '{cap} granted to {app}.',
    permissionRevoked: '{cap} revoked from {app}.',
    permissionSaveError: 'Could not change the permission.',
    // Responsible declaration inside the product (art. 13.2 RRSIF — hub#528). The element names
    // (`NombreRazon`, `IdSistemaInformatico`…) are NOT translated: they are the ones of the
    // invoicing record and the screen exists to be read next to one.
    // WHICH signed text covers this release (`v1`, `v2`…), next to the link — hub#1510. Art. 13.3
    // RRSIF lets several declarations coexist, so the link alone does not identify the text.
    // hub#1174 — what STOPS WORKING while the switch is off. Default-deny (ADR-0079) is right; an
    // invisible consequence is not. One sentence per capability id; the catalogue in
    // `lib/module-capabilities.ts` names the key and the card only translates it. The action that
    // fixes it is the toggle in the same row (hub#800 §3).
    capabilityBreaks: {
      network: 'Without this, the app cannot go online: whatever it syncs, sends or checks over the internet stays undone.',
      certificate: 'Without this, your invoices are not signed and never reach the tax authority.',
      printer: 'Without this, receipts and kitchen orders pile up in the print queue and nothing comes out.',
      notify: 'Without this, no reminder or confirmation reaches your customers by email, SMS or WhatsApp.',
      manage_flows: 'Without this, the app cannot create or edit your automations, so the ones it needs never run.',
      // A capability this shell does not know yet: say something true rather than nothing.
      unknown: 'Without this, the part of the app that needs this permission will not work.',
    },
  },
  // Print coverage (hub#800): who is printing each kind of ticket, and who is NOT. The runtime
  // sends facts (`role`, `waiting`, `liveHosts`); the sentence the owner reads lives here — the
  // API comment in `crates/server/src/print.rs` says so explicitly.
  print: {
    coverageTitle: 'Printing status',
    coverageDesc: 'Which devices are taking each kind of ticket out right now.',
    // The four conventional roles get a human name; an unknown role shows its raw name.
    roleReceipt: 'Sale receipts',
    roleKitchen: 'Kitchen orders',
    roleBar: 'Bar orders',
    roleLabel: 'Labels',
    // THE alarm (the issue's headline, per role): work is piling up and no device takes it out.
    stalled: 'Nobody is printing these — {n} ticket waiting | Nobody is printing these — {n} tickets waiting',
    // Lost coverage: a device WAS registered for this role and stopped reporting.
    unattended: 'The device that printed these is not responding',
    // Reassurance: who is on it. Without it the screen could only ever show problems.
    ready: 'Printing on {hosts}',
    // What to DO about it — a warning with no action next to it is a reproach (hub#800 §3).
    hostHint: 'Open the ERPlora app on the device connected to this printer.',
    // Never green, no call to action: our failed probe is not the owner's homework (hub#375).
    coverageError: 'Could not check who is printing right now.',
    // The two warnings the till hears when paper does not come out (hub#1731). They are DIFFERENT
    // facts and the words say so: the first one lost the paper, the second one only lacks a
    // printer set up — the job is safe in the queue and comes out on its own once there is one.
    // Naming what to do next matters more than naming the fault: «did not print» sends the
    // cashier hunting for a jam that is not there.
    ticketFailed: 'The receipt did NOT print: {error}',
    ticketWaitingForPrinter:
      'The receipt is waiting: no printer is set up yet. Set one up and it will print on its own.',
    // hub#1921: the receipt itself could not be prepared (the sales app did not compose it), so
    // nothing went to the printer. The way out is the print button on the receipt screen.
    ticketNotComposed:
      'The receipt could not be prepared and did NOT print. Print it from the receipt screen.',
    // hub#1867: the receipt came out, but Hacienda's QR was not ready within the wait (a slow AEAT),
    // so the customer's copy lacks it. The receipt screen prints the complete one.
    ticketWithoutFiscal:
      'The receipt came out before its VeriFactu QR was ready. Print it again from the receipt screen to give the customer the complete one.',
    comandaFailed: 'The kitchen order for {label} ({role}) did not print: {error}',
    comandaWaitingForPrinter:
      'The kitchen order for {label} ({role}) is waiting: no printer is set up for that station yet.',
    // The system notice when a kitchen order comes in (hub#2171): `comandaNoticeFor` names the
    // floor label («Table 4», «Bar») when the order has one; the body is the order number and the
    // line count, pluralised by `n`.
    comandaNotice: 'New kitchen order',
    comandaNoticeFor: 'New kitchen order · {label}',
    comandaNoticeLines: '{n} line | {n} lines',
    // A docket with no label of its own: takeaway, or a hub with no table plan. It still has to be
    // named in the warning, or the sentence reads «the order for ()».
    comandaDefaultLabel: 'the floor',
  },
  // The system notices for a booking or a cancellation that did NOT come from a till (hub#2168):
  // a salon's twin of the kitchen order's notice above. `createdFor`/`cancelledFor` name the
  // customer when the event brought one; the plain `created`/`cancelled` cover the rest so the
  // title never leaves a hole. `when` is the day and hour, already resolved in the business's own
  // timezone by the appointments module (appointments#151) — this file only places it in a sentence.
  appointmentNotice: {
    created: 'New booking',
    createdFor: 'New booking · {customer}',
    cancelled: 'Booking cancelled',
    cancelledFor: 'Booking cancelled · {customer}',
    when: '{date} at {time}',
  },
  // hub#365 — this screen is the far end of the apps door, so it speaks the noun hub#367 chose:
  // «apps», never «modules». The KEYS keep saying module (`colModule`, `moduleInstalled`): they are
  // the manifest's word and renaming them would break nothing here and everything elsewhere.
  // «Connect WhatsApp» — the block the WhatsApp module embeds as <erp-whatsapp-connect> (hub#1600).
  // The owner connects the number of the business from here: Meta's popup, a QR scanned with the
  // WhatsApp Business app. Errors are sentences a person can act on, keyed by the SaaS's code.
  whatsappConnect: {
    intro: 'Connect the WhatsApp number of your business. You will sign in with Facebook and scan a QR code with the WhatsApp Business app on your phone.',
    connect: 'Connect WhatsApp',
    connected: 'Connected',
    businessApp: 'WhatsApp Business app',
    connectedHelp: 'Messages from your customers arrive in the Inbox, and the automations answer them.',
    // hub#1626: the permission WhatsApp gives to write for a business lasts 60 days and runs out on
    // its own. When Meta refuses to renew it, only the owner can fix it — so the sentence names what
    // stopped working (both directions) and what to do, and never the word «token».
    // NOT a bare «Disconnected»: hub#375 took that word out of the catalogues on purpose, because
    // one word next to a heading reads as a verdict about the whole machine, and `system-health`
    // guards it. This badge names the ONE thing the owner has to do instead.
    reconnectBadge: 'Reconnect needed',
    reconnectNeeded:
      'WhatsApp has withdrawn the permission to write on behalf of your business. Your customers’ messages are not arriving and nothing you answer is going out. Connect your number again to get the channel back.',
    reconnect: 'Reconnect WhatsApp',
    disconnect: 'Disconnect',
    disconnectConfirm: 'Disconnect this number? Messages will stop arriving here.',
    adminOnly: 'Only an owner or an administrator can connect the WhatsApp number.',
    loading: 'Opening the WhatsApp connection…',
    connecting: 'Connecting your number…',
    retry: 'Retry',
    errors: {
      cancelled: 'The connection was cancelled before finishing.',
      no_phone_number: 'No phone number was added. Open the connection again and add or choose a number.',
      no_business_account: 'Facebook did not return a WhatsApp Business account. Try again and pick your business in the window.',
      not_configured: 'WhatsApp is not available on this hub yet. Contact support.',
      sdk_unavailable: 'The Facebook window could not open. Allow pop-ups for this site and try again.',
      // The runtime's own code when the call never got through (hub#1689). Same fact as
      // `unreachable`, which the browser raises when ITS fetch fails: for whoever is
      // connecting, the difference between the two is not actionable.
      cloud_unreachable: CLOUD_UNREACHABLE,
      unreachable: CLOUD_UNREACHABLE,
      forbidden: 'Only an owner or an administrator can connect the WhatsApp number.',
      // hub#1624: the codes erplora.com sends next to its prose (saas#1902). `meta_unreachable` is the
      // only one where trying again helps, so it is the only one that says so.
      meta_unreachable: 'WhatsApp is not answering right now. Try again in a few minutes.',
      meta_api_error: 'WhatsApp refused the connection because of a problem on our side. Contact support.',
      no_access_token: 'Facebook did not give the permission to connect. Open the connection again and accept the permissions.',
      missing_code: 'The Facebook window closed before finishing. Open the connection again and complete every step.',
      hub_not_found: 'erplora.com does not recognise this hub. Contact support.',
      number_not_found: 'That number is no longer connected.',
      internal_error: 'erplora.com could not finish the connection. Contact support if it keeps happening.',
      default: 'Something went wrong while connecting. Try again in a minute.',
    },
  },
  apps: {
    searchInstalled: 'Search your apps…',
    searchCatalog: 'Search apps to add…',
    tabMine: 'My apps',
    // The same words as the ＋ tile on the panel (`dashboard.appsAdd`): one door, one name.
    tabCatalog: 'Add apps',
    tabPaid: 'Paid',
    emptyInstalled: 'You have no apps yet. Open “Add apps” to install your first one.',
    // hub#770: «you have no apps» is a fact about the hub, so it is only ever said about an
    // answer that came back and said so. These two are the other two things the screen can know.
    loadingInstalled: 'Loading your apps…',
    installedLoadError:
      'We could not read your apps. There was no answer, or this session is no longer valid — sign in again if it keeps happening.',
    emptyCatalog: 'No apps match your search.',
    // hub#1129: and the catalogue gets the same three sentences as the installed list above.
    // «Nothing matches your search» was also being said while it loaded and after it failed — on
    // the one screen whose whole job is to let a brand-new business install its first app.
    loadingCatalog: 'Loading the catalog…',
    catalogLoadError:
      'The catalog could not be loaded. Check the connection or this device registration.',
    retryCatalog: 'Retry',
    demoCatalogReadOnly: 'You are browsing the real catalog in demo mode. Connect a real business to install apps.',
    adminOnly: 'You can browse the apps, but only an administrator can install, activate or uninstall them.',
    colModule: 'App',
    colVersion: 'Version',
    colStatus: 'Status',
    colCategory: 'Category',
    colDescription: 'Description',
    colPrice: 'Price',
    statusActive: 'Active',
    statusInactive: 'Inactive',
    statusInactiveAuto: 'Inactive (cascaded)',
    stateInstalled: 'Installed',
    stateAvailable: 'Available',
    stateUnavailable: 'Unavailable',
    stateNeedsNewerHub: 'Needs ERPlora {version}',
    // hub#2082: installed, and its next version needs a newer ERPlora than this one runs.
    stateUpdateNeedsNewerHub: 'Version {version} needs ERPlora {floor}',
    stateInstalling: 'Installing…',
    // hub#516: installed, but a newer version is published. Names the version — «there is an
    // update» without saying which one is a nag, not information.
    stateUpdatable: 'Update to {version}',
    phaseResolving: 'Resolving version…',
    phaseDownloading: 'Downloading…',
    phaseVerifying: 'Verifying integrity…',
    phaseInstalling: 'Applying migrations…',
    phaseDependency: 'Dependency {name} — {phase}',
    actionToggle: 'Activate/Deactivate',
    actionUninstall: 'Uninstall',
    actionInstall: 'Install',
    actionUpdate: 'Update',
    actionSeeHubUpdates: 'See your ERPlora version and updates',
    // Icon-only like every action (Ioan 2026-07-16 on ADR-0133): okdt puts this in `aria-label`
    // and `title`, never on the face of the button.
    actionOpen: 'Open',
    priceFree: 'Free',
    priceMonthly: '€{price}/month',
    priceYearly: '€{price}/year',
    priceOneTime: '€{price}',
    priceOnRequest: 'On request',
    priceIncludedInPlan: 'Included in your plan',
    alreadyInstalled: '{name} is already installed.',
    installing: 'Installing {name}…',
    installSuccess: '{name} installed successfully.',
    // hub#1130: the install-plan closure (ADR-0060) dragged dependencies in — the owner asked for
    // ONE app and got several; naming them in the SAME confirmation is the reverse of hub#1101's
    // `409 has_dependents`, which already names what an uninstall would break.
    installSuccessWithDependencies: '{name} installed successfully. Also installed: {names}.',
    installError: 'Could not start installation of {name}.',
    // ADR-0060: the install plan needs modules this hub has not purchased. Nothing was installed.
    installBlocked: '{name} needs apps you have not subscribed to yet: {missing}. Nothing has been installed.',
    // hub#516 — the update button. `updateError` says the one thing that matters: the module did
    // NOT end up half-updated; it keeps running the version it had.
    updating: 'Updating {name}…',
    updateSuccess: '{name} updated: {from} → {to}.',
    // hub#935 — a custom element can only be registered once per document, so this page cannot show
    // the new build of the app it just updated. Saying that the screen is about to reload beats
    // reloading it out of the blue, and beats leaving it showing the previous version in silence.
    updateSuccessReloading: '{name} updated: {from} → {to}. Reloading to use the new version…',
    updateUpToDate: '{name} is already on the latest version.',
    updateError: 'Could not update {name}. It keeps running the version it had.',
    updateBlocked: 'The new version of {name} needs apps you have not subscribed to yet: {missing}. Nothing has changed and nothing has been charged.',
    // Version picker (hub#675). Only shown when there is more than one option; the latest comes
    // first and preselected, so choosing another one is deliberate.
    versionPickTitle: 'Choose a version',
    versionPickBody: 'The latest one is selected. Pick another only if support asked you to.',
    versionPickConfirm: 'Continue',
    versionLatest: '{version} (latest)',
    // Names the place, does not open it (hub#479). `purchaseInBrowser`/`purchaseOpenError` went
    // with the button that opened the SaaS checkout.
    needsSubscription: '{name} needs a subscription. Subscribe from your ERPlora account at erplora.com and it will install here.',
    deactivated: '{name} deactivated.',
    activated: '{name} activated.',
    cascadeOffMsg: 'These will also be deactivated (they depend on {name}):',
    cascadeOnMsg: 'These will also be activated ({name} needs them):',
    cascadeCancel: 'Cancel',
    // The switch on an app card is the SAME pictogram for on and for off (hub#773), so the
    // question it opens is the only place a person is told which way the press goes. Title names
    // the app and the direction; the body says what changes on the till.
    toggleOffTitle: 'Deactivate {name}',
    toggleOffBody: '{name} disappears from the till and its screens stop opening. Nothing is deleted: switching it back on leaves it as it was.',
    toggleOffConfirm: 'Deactivate',
    toggleOnTitle: 'Activate {name}',
    toggleOnBody: '{name} comes back to the till, with the data it already had.',
    toggleOnConfirm: 'Activate',
    uninstallTitle: 'Uninstall {name}',
    // What the old text said was what is KEPT. This is the half it left out: the apps that need
    // this one stop working, and unlike deactivating, there is no switching them back on.
    uninstallBreaks: 'These apps need {name} and will stop working:',
    uninstallBody: 'The app will no longer be available. Its data and files will be kept for a later reinstall.',
    uninstallConfirm: 'Uninstall',
    toggleError: 'Could not change the status of {name}.',
    uninstalled: '{name} uninstalled.',
    uninstallError: 'Could not uninstall {name}.',
    // hub#1101: the runtime refused because other installed apps declare this one. Only reachable
    // when the list the dialog was drawn with had gone stale (another tab, another admin), so it
    // names the apps the RUNTIME sent, not the ones we happened to have loaded.
    uninstallBlocked: '{name} was not uninstalled: these apps need it — {apps}. Uninstall them first.',
    moduleInstalledNamed: '{name} installed.',
    moduleInstalled: 'App installed.',
    consentTitle: 'Requested permissions',
    consentIntro: 'This app requests these permissions. You can review them later in Settings → Permissions.',
    consentInstallGrant: 'Install and grant',
    consentCancel: 'Cancel',
    installedButNoPermissions: '"{name}" was installed, but its permissions could not be granted. It will not work without them: turn them on in Settings → Permissions.',
    goToPermissions: 'Go to Permissions',
    // ADR-0380 (hub#1134). The marketplace closed the OFFER, never the supply: the app keeps
    // working and keeps updating. Both strings say that, because a chip that only says «Retired»
    // reads as «broken» and the first thing anybody would do is uninstall a healthy app.
    publicationRetired: 'Retired',
    retiredNotice: 'No longer in the catalog: {apps}. They keep working here and keep receiving updates — they are just not offered any more, so you will not find them to install somewhere else.',
  },
  employees: {
    searchEmployee: 'Search user…',
    searchRole: 'Search role…',
    tabStaff: 'People',
    tabRoles: 'Roles',
    tabApiKeys: 'API keys',
    tabApprovals: 'Approvals',
    colEmployee: 'User',
    colEmail: 'Email',
    colRole: 'Role',
    colAccess: 'Access',
    // hub#463 — this address looks fine and administers nothing: their baja revokes no membership
    // and their next sign-in lands on a different row. Each reason names the way OUT, because the
    // two are different decisions and only a human can take them.
    accessEmailConflict: {
      badge: 'Needs a decision',
      another_row_answers_for_it:
        'Somebody else already signs in with this address, so removing this person revokes nothing. Change the address on one of the two.',
      two_profiles_claim_it:
        'Two people hold this address, and nothing says which one is them. Removing this person revokes nothing. Remove the duplicate, or give one of them their own address.',
    },
    colStatus: 'Status',
    colCreatedAt: 'Joined',
    colMembers: 'Members',
    colPermissions: 'Permissions',
    actionEdit: 'Edit',
    actionDeactivate: 'Deactivate',
    access: {
      pin: 'Local PIN',
      pin_badge: 'PIN + badge',
      badge: 'Badge',
      cloud: 'Online account',
      // Exists as a person in the business, but cannot sign in to the Hub.
      none: 'No sign-in',
    },
    roles: {
      owner: 'Owner',
      admin: 'Administrator',
      manager: 'Manager',
      employee: 'Employee',
      cashier: 'Cashier',
    },
    emptyStaff: 'Nobody else has access to this Hub yet.',
    emptyRoles: 'No roles available yet.',
    loadErrorTitle: 'Staff could not be loaded',
    loadErrorBody: 'The Hub did not return the list of users. Please try again.',
    retry: 'Retry',
    saveError: 'Changes could not be saved.',
    created: 'User created.',
    updated: 'User updated.',
    deactivated: 'User deactivated.',
    deleteError: 'The user could not be deactivated.',
    deactivateTitle: 'Deactivate user',
    deactivateBody: 'You are about to deactivate “{name}”. They lose access to the Hub, but their history is kept.',
    deactivateBlocked: 'You cannot deactivate yourself or leave the Hub without an administrator.',
    ownerRowBlocked: 'Only the account owner can change their own record. To hand the business over, transfer the account in ERPlora.',
    active: 'Active',
    inactive: 'Deactivated',
  },
  // Role catalogue (hub#352/hub#353): base roles ∪ what the installed modules declare ∪ what
  // somebody still carries. The administrator switches on the ones this business actually needs.
  roleCatalog: {
    intro:
      'These are the roles this Hub can hand out. The built-in ones are always available; the ones a module brings in are yours to switch on when your business needs them.',
    colSource: 'Comes from',
    colActive: 'Available',
    sourceCore: 'Built in',
    sourceModule: '{module}',
    sourceInUse: 'Module removed',
    alwaysOn: 'Always on',
    // Va DENTRO de la celda, al lado del interruptor: tiene que caber en una línea.
    notDeclared: 'No app brings it in',
    adminOnly: 'Only an administrator can switch roles on or off.',
    activated: '“{role}” can now be assigned.',
    deactivated: '“{role}” can no longer be assigned.',
    toggleError: '“{role}” could not be switched.',
    loadError: 'The role catalogue could not be loaded.',
  },
  apiKeys: {
    // The sentences this panel reads when its door refuses (hub#1697, reachable since hub#1700).
    //
    // Written in hub#1697 and dead until hub#1700, because `/api/keys*` answered
    // `{"ok":false,"error":"<flat string>"}` with no `code` at all: every refusal came out as the
    // panel's own «check your connection» line. The four handlers now answer the shared envelope
    // (`err_response` / `auth_rejected`), so `localDoorSentence` finds these.
    //
    // `rate_limited` is the one that is still NOT reachable from here, and that is a fact about
    // the door, not an omission: the quota lives on the `auth:api-key` data surface a THIRD PARTY
    // calls (`external_principal`), and this admin door has none. The sentence stays because it is
    // the right one for that code the day this door gets a quota; nothing paints it meanwhile.
    errors: {
      not_found: 'That key no longer exists. Refresh the list and try again.',
      rate_limited: 'Too many attempts in a row. Wait a moment and try again.',
      unauthorized: 'Your session has expired. Sign in again and retry.',
      forbidden: 'Only an owner or an administrator can manage API keys.',
      // The code is namespaced by the module that raised it, so the catalogue nests it.
      api_key: {
        system_key: 'ERPlora issued this key to itself. It cannot be rotated or deleted.',
      },
    },
    // List
    searchKey: 'Search API key…',
    empty: 'No API keys yet. Create one so an external system can read or write Hub data.',
    loadError: 'Could not load your API keys. Try again in a moment.',
    newKey: 'New API key',
    colName: 'Name',
    colPrefix: 'Token',
    colScope: 'Permissions',
    colStatus: 'Status',
    colCreated: 'Created',
    colLastUsed: 'Last used',
    colRateLimit: 'Limit',
    colActions: 'Actions',
    never: 'Never',
    statusActive: 'Active',
    statusRevoked: 'Revoked',
    actionRotate: 'Rotate',
    actionRevoke: 'Revoke',
    short: { read: 'R', write: 'W' },
    // Create
    newTitle: 'New API key',
    name: 'Name',
    namePlaceholder: 'e.g. Accountant — invoices',
    rateLimit: 'Requests per minute',
    rateLimitHint: 'Between 1 and 10,000. Enforced before command execution.',
    perMinute: '{count}/min',
    // hub#504 — qué puede hacer una key (mismo modelo que el rol de un usuario)
    accessTitle: 'What this key may do',
    accessHint: 'The blanket modes cover every app of your business, including ones installed later.',
    access: {
      full: 'Full access',
      read_only: 'Read only',
      write_only: 'Write only',
      custom: 'Per app',
    },
    systemKeyBadge: 'Issued by ERPlora',
    systemKeyHint: 'ERPlora reads your live changes with this key. It cannot be rotated or deleted.',
    scopeTitle: 'Permissions per module',
    scopeHint: 'Toggle read and/or write for each installed module.',
    colModule: 'Module',
    colRead: 'Read',
    colWrite: 'Write',
    toggleAllRead: 'Read on all modules',
    toggleAllWrite: 'Write on all modules',
    readOf: 'Read {module}',
    writeOf: 'Write {module}',
    loadingModules: 'Loading installed apps…',
    noModulesTitle: 'No modules installed',
    noModulesHint: 'Install modules from Apps to grant a key access to them.',
    noApiModulesTitle: 'No module exposes an API yet',
    noApiModulesHint: 'Only modules with public API operations can be included in a key. None of the installed ones expose one yet.',
    cancel: 'Cancel',
    create: 'Create key',
    createError: 'Could not create the API key.',
    // Secret (one time)
    secretTitle: 'API key created',
    secretWarnTitle: 'Copy the token now',
    secretWarnBody: 'This is the only time the full secret is shown. Store it somewhere safe; it will not be shown again.',
    copy: 'Copy',
    copied: 'Copied',
    copyError: 'Could not copy to clipboard.',
    done: 'Done',
    // Rotate / revoke
    rotateError: 'Could not rotate the API key.',
    revokeTitle: 'Revoke API key',
    revokeBody: 'You are about to revoke “{name}”. Any system using this token will lose access immediately. This cannot be undone.',
    revoked: '“{name}” revoked.',
    revokeError: 'Could not revoke the API key.',
  },
  // PIN approvals (hub#512, ADR-0265): the record of every approval a manager spent, and the only
  // place a business owner can read it without a SQL session against their own database. The words
  // name PEOPLE and ACTIONS, never the machinery: nobody behind a counter knows what an "elevation"
  // or a "permission scope" is, and this is the screen somebody opens on a bad day.
  approvals: {
    intro:
      'Every action that needed a manager’s PIN: who asked for it, who approved it, and what it was used for. This record is kept for as long as your business is with ERPlora, and nobody — not even an administrator — can edit or delete it.',
    search: 'Search by person or action…',
    colWhen: 'When',
    colApprovedBy: 'Approved by',
    colRequestedBy: 'Asked by',
    colAction: 'Action',
    colLevel: 'Level',
    // The fingerprint of the exact payload: it is what tells one €4 refund from another. Named for
    // what it is FOR, because "fingerprint" reads as a threat and "hash" as nothing at all.
    colFingerprint: 'Reference',
    colRequestedById: 'Asked by (id)',
    colApprovedById: 'Approved by (id)',
    // Their receipt outlives them: the row stays, and it says why the name is missing.
    userGone: 'Deleted user',
    empty: 'Nobody has had to approve anything on this Hub yet.',
    loadError: 'The approval record could not be loaded.',
  },
  employeeForm: {
    titleEdit: 'Edit user',
    titleNew: 'New user',
    fullName: 'Full name',
    email: 'Email',
    role: 'Role',
    pin: 'Local PIN',
    pinHelp: '{n} digits. Leave blank to sign in with an online account.',
    pinSetHelp: 'Type a new PIN to change it; leave blank to keep the current one.',
    clearPin: 'Remove PIN',
    // hub#658 — the badge, sibling of the PIN. Both words matter: «badge» is what the sector calls
    // the card, and «remove» (not «reset») says what the button does — the PIN is untouched.
    badge: 'Badge',
    badgeHelp:
      'Swipe the card and it fills in on its own — no need to click here first. You can also type the number, for a key fob or an engraved tag.',
    badgeSetHelp:
      'They already carry a badge. Swipe a new card to replace it, or leave this blank to keep the current one.',
    // hub#988 — shown INSTEAD of the two above where the device can read a card by itself. Only
    // there: promising a tap on a machine with no reader is worse than not mentioning it.
    badgeNfcHelp:
      'Tap the card on this device — or swipe it on the reader — and it fills in on its own. You can also type the number, for a key fob or an engraved tag.',
    badgeNfcSetHelp:
      'They already carry a badge. Tap or swipe a new card to replace it, or leave this blank to keep the current one.',
    clearBadge: 'Remove badge',
    localUser: 'Local user',
    localUserHelp:
      'Works this hub with a PIN only: no email and no ERPlora account. Turn it off to give them an account later, keeping their history.',
    localPinHelp: '{n} digits. Required: it is how this person signs in.',
    accountEmailHelp:
      'We email them an invitation to this hub. They choose their own password — you never see it.',
    accountPinHelp:
      'Optional: {n} digits. Only needed if they also work a shared till in this hub.',
    // Motivo del rechazo del alta, por su código estable del runtime (`hub.users.*`).
    errors: {
      // hub#1697 — the guards of the local `/api/hub/users` door (`hub_users.rs`). Their own
      // message is prose written into the runtime; these are the sentences the person reads.
      last_admin: 'You cannot deactivate the last administrator. Name another owner or administrator first.',
      // hub#1705 — the gate of the people and roles doors. A dead session is fixed by signing in
      // again; a role without the permission is not, so the second sentence never suggests it.
      unauthorized: 'Your session has expired. Sign in again and retry.',
      forbidden: 'Only an owner or an administrator can manage staff and roles.',
      self_deactivation: 'You cannot deactivate your own account. Ask another administrator to do it.',
      self_badge_enrollment: 'Nobody enrols their own badge. Ask another administrator to do it.',
      not_found: 'That person is no longer on this hub. Refresh the list.',
      local_needs_pin: 'A local user signs in with a PIN: without one, nobody could use this account.',
      account_needs_email: 'An account user signs in with their ERPlora account, so an email is required. Tick «Local user» to create somebody who works this hub with a PIN.',
      account_role_not_grantable: 'An ERPlora account can only be invited as admin, manager or employee. Roles a module adds belong to local staff.',
      email_taken: 'This hub already knows that email. Edit that user — reinstate them if they were deactivated — instead of inviting a second identity.',
      // hub#1685 — the seat cap of the plan. No number in the sentence on purpose: this screen
      // calls `t(`employeeForm.errors.${key}`)` with no params for every key, and the cap lives in
      // the entitlement, not in the rejection. «Plan y límites» is where the exact «n / cap» is.
      user_limit_reached: 'Your plan has every seat taken. Deactivate somebody who no longer works here, or move to a plan with more seats.',
      role_above_inviter: 'You cannot hand out a role above your own: only somebody who administers this hub can grant administration.',
      // hub#1429 — the account owner's record is theirs alone. Every other administrator sees it,
      // nobody else edits it, and ownership changes in the ERPlora account, not on this screen.
      owner_row: 'This is the account owner’s record, and only they can change it — their PIN included. To hand the business over, transfer the account in ERPlora.',
      invalid_email: 'Enter a valid email.',
      pin_length: 'The PIN must be {n} digits.',
      pin_too_simple: 'That PIN is too easy to guess: avoid repeated digits (1111) and straight runs (1234).',
      pin_in_use: 'Another active user already has this PIN. A PIN says who is at the till, so no two people can share one.',
      // hub#1430 — self-service rotate («Mi perfil»): the CURRENT PIN did not match. The remedy is
      // the same «try again» a wrong password gets anywhere else, never a hint about what the
      // current one actually is.
      pin_current_mismatch: 'That is not your current PIN. Enter it correctly to set a new one.',
      local_cannot_administer: 'A local user cannot administer the hub: administration comes from an ERPlora account, never from a PIN.',
      local_has_email: 'A local user has no email. Turn off «Local user» to invite them as an account user.',
      name_taken: 'This hub already knows somebody by that name. Edit that user — reinstate them if they were deactivated — instead of creating a second identity.',
      badge_shape: 'A badge is between 4 and 64 characters: letters, digits, «-» and «_».',
      badge_in_use: 'Another active user already carries this badge. A badge says who is at the till, so no two people can share one.',
      // hub#658 — the badge may never be somebody's ONLY way in: a lost card would lock them out
      // of their own till (Square does not allow it either, and Lightspeed L-Series is why).
      badge_without_fallback: 'A badge cannot be their only way in: a lost card would lock them out. Keep their PIN, give them an account, or remove the badge as well.',
      // hub#1214 — the OTHER half of an alta/baja: the record is saved on this hub, but who can
      // sign in is administered in the Cloud (ADR-0157 §7). Four codes and not one bucket, because
      // each asks something different of whoever is saving: wait, fix the address, retry, or call
      // support. Before this, the raw body of the Cloud («el SaaS respondió 429: {"detail":…}») was
      // painted here verbatim.
      cloud_rate_limited: 'Too many changes in a short time, so the invitation has not gone out yet. Wait a few minutes and save again — nothing else was lost.',
      cloud_rejected: 'The invitation for that email could not be created. Check the address and try again; if it keeps failing, contact support.',
      cloud_unreachable: 'We could not reach ERPlora to send the invitation. The user is saved here: try saving again in a moment.',
      not_enrolled: 'This hub cannot send invitations yet. The user is saved here; contact support so they can finish setting it up.',
    },
    activeUser: 'Active user',
    required: 'Required field',
    invalidEmail: 'Enter a valid email',
    loadErrorTitle: 'The user could not be opened',
    loadErrorBody: 'The record is unavailable or you do not have permission to view it.',
    notFound: 'User not found.',
    unsavedTitle: 'Unsaved changes',
    unsavedBody: 'If you leave now you will lose your changes.',
    keepEditing: 'Keep editing',
    discard: 'Discard changes',
    cancel: 'Cancel',
    save: 'Save',
    create: 'Create',
    saving: 'Saving…',
  },
  system: {
    // hub#1697 — when the door gave no code we can turn into a sentence, saying so beats
    // pasting the line the runtime left for the log.
    reasonUnknown: 'the reason could not be read',
    // hub#1697 — stable codes of the dead-letter door (`outbox_admin.rs`). Its own prose mixes
    // Spanish and English and was written for whoever debugs, not for whoever runs the shop.
    //
    // FRAGMENTS, not sentences (rv-1699): every one of these is read INSIDE `retryFailed` /
    // `discardFailed`, which already announce the failure. A whole sentence here says it twice
    // («Could not resend: This message cannot be sent again: …»), so they start lowercase and
    // continue the frame — same register as `reasonUnknown` above. There is a test on it.
    errors: {
      not_found: 'that message is no longer in the queue; refresh the list.',
      invalid_payload: 'that message is missing the data it needs to be sent again.',
      // Nested, not `'flow.release_revoked'` as a flat key: `vue-i18n` reads a dot in a key as
      // NESTING, so a flat dotted key is unreachable through `t()`. The runtime's code maps onto
      // the path exactly.
      flow: {
        release_revoked: 'the permission that produced it was withdrawn; grant it again and run the automation.',
      },
      module: {
        capability_denied: 'the app that produced it no longer has permission for it.',
      },
    },
    database: 'Database',
    memory: 'Memory',
    connections: 'Connections',
    // The printer card's headline, status word and status sentence used to live here, naming a
    // process («Bridge») instead of the thing on the counter. They now come from `system.health.*`
    // (hub#375). What is left below is the INSTALL flow, which is still about a piece of software
    // and says so on purpose.
    recheck: 'Recheck',
    // One product, one name (hub#500). «Download ERPlora Bridge» followed by «install ERPlora» were
    // two names for the same thing, and one of them belonged to an app ADR-0196 deleted — «Bridge»
    // is platform jargon, the side ADR-0254 keeps out of the hub's screens.
    downloadApp: 'Download the ERPlora app',
    downloadAppHint: 'The ERPlora app is what talks to your printers, cash drawer and scanners. Choose your system to continue.',
    stepDownload: 'Download',
    stepInstall: 'Install',
    stepPair: 'Pair',
    stepConfigure: 'Configure',
    updatesCloudHint: 'This web Hub is updated automatically as part of service deployments.',
    // What we changed on this hub, and from which version (hub#564, ADR-0269 §3.5). We update
    // without asking, so the least we owe is that the owner can find out WHAT changed. Every
    // sentence below names an app the way they know it and a version they can compare — never a
    // digest, never «the image», and never a changelog we made up.
    updateHistory: "What we've updated",
    updatesRunning: 'Running {version}',
    noUpdates: 'Nothing has changed',
    noUpdatesHint: "We haven't updated anything on this hub recently. When we do, it will show up here.",
    today: 'Today',
    yesterday: 'Yesterday',
    // A rollback is an entry of its own and says so in those words: which version it went back to.
    // The error behind it is deliberately not shown — it is written for us, not for whoever is
    // opening the shop.
    rolledBackTo: 'Went back to {version}: the new one did not start',
    updateLost: 'This app is not running: we are on it',
    documents: 'Documents',
    noDocuments: 'No documents',
    noDocumentsBucket: "This hub's storage bucket is empty.",
    searchDocument: 'Search document…',
    loadErrorTitle: 'System information is unavailable',
    loadErrorBody: 'Metrics and logs are unavailable right now. You can try again.',
    retry: 'Try again',
    eventLog: 'Event log',
    noEvents: 'No events',
    noEventsHint: "The runtime hasn't reported any recent events.",
    searchEvent: 'Search event…',
    tabResources: 'Resources',
    tabPlan: 'Plan & limits',
    tabUpdates: 'Updates',
    tabLogs: 'Logs',
    tabEvents: 'Failed events',
    deadEvents: 'Failed events',
    deadEventsHint: 'Fix the cause (permission, a module that was down…) and resend. The content is never edited: if the cause persists, the event dies again and reappears here.',
    deadEventNotRetryable: 'This one cannot be resent: the authorisation behind it was withdrawn and the recipient is no longer in the row. Grant the permission again and run the flow.',
    noDeadEvents: 'All clear',
    noDeadEventsHint: 'No failed events. The event queue lives in the database: a restart never loses it.',
    deadEventsLoadError: 'Could not load the failed-event queue. Check the connection and retry.',
    attempts: 'attempts',
    retryAll: 'Resend all',
    retryDone: 'Event resent to the relay.',
    retryAllDone: '{count} event resent to the relay. | {count} events resent to the relay.',
    retryFailed: 'Could not resend: {reason}',
    discardDone: 'Event discarded (kept for audit).',
    discardFailed: 'Could not discard: {reason}',
    discardConfirm: 'Discard this event for good? The row is kept (auditable), but the relay will never redeliver it. Use only if the event must not be recorded.',
    resourcesCloud: 'Cloud resources',
    resourcesSystem: 'System resources',
    sourceCloud: 'Cloud',
    // Usage-series range selector (saas#1511). The contract stops at 3 days on purpose.
    usageRange3h: '3 h',
    usageRange24h: '24 h',
    usageRange3d: '3 days',
    usageRangeLabel3h: 'Last 3 hours',
    usageRangeLabel24h: 'Last 24 hours',
    usageRangeLabel3d: 'Last 3 days',
    // A metric close to / past the plan's limit (hub#1922) — worded by the hub, from the codes.
    usageNearLimit: 'At {pct}% of your plan\'s limit.',
    usageOverLimit: 'At {pct}% of your plan\'s limit — the hub may slow down.',
    planPressure: 'Your plan is running short on resources. A bigger plan gives this hub more room.',
    databaseShared: 'Shared database',
    colTime: 'Time',
    colLevel: 'Level',
    colEvent: 'Event',
    toastDownloadingApp: 'Downloading ERPlora for {os}…',
    // What the hub says about itself, to the person who owns the bar (hub#375). Every sentence
    // names a thing they recognise —the printer— and, when there is something to do, what to do.
    // The third state is the honest one: we could not check. It is never dressed up as "fine".
    health: {
      printerTitle: 'Your printer',
      printerReady: 'Printer ready',
      printerReadyDetail: 'Receipts come out on their own when you charge.',
      printerOffline: 'Printer not connected',
      printerOfflineDetail:
        'You can keep charging: the receipt opens on this screen and you print it from here.',
      printerAction: 'Set up printing',
      printerUnknown: "We couldn't check the printer",
      printerUnknownDetail:
        "We don't know whether it is connected — nothing else is affected. We will check again on our own.",
      // hub#1629 — WhatsApp that stopped on its own (expired permission, revoked by Meta, unlinked).
      whatsappDown: 'WhatsApp stopped working',
      whatsappDownDetail:
        "Customer messages aren't coming in and your replies aren't going out until you connect it again.",
      whatsappAction: 'Connect WhatsApp again',
      notMeasured: "We couldn't read this",
    },
    // hub#1886 — the button on the two blocked cards (notices, printer search) that opens THIS
    // app's page in the device settings: once Android stops asking, that page is the only way back.
    openDeviceSettings: 'Open settings',
    // hub#1732 — the notices, and the permission that lets them exist at all.
    //
    // The sheet that goes in FRONT of Android's dialog. Android's own says «Allow ERPlora to send
    // you notifications?» and nothing about what for; asked cold it reads as opportunistic and
    // gets refused, and two refusals close the dialog for the life of the install. So this says
    // what the notices are for — and never «permission», «POST_NOTIFICATIONS» or «Android». In
    // words that fit EVERY business: the sheet appears on a salon's front desk as much as on a
    // restaurant's till, and «orders in the kitchen» got it refused there (hub#1927).
    notices: {
      primerHeader: 'Let us keep you posted',
      primerMessage:
        'When something needs your attention, we can warn you, even if nobody is looking at this screen. Your device will ask you next.',
      primerLater: 'Not now',
      primerAllow: 'Turn on notices',
      // The row on System › your printer, which is where somebody who never got warned would
      // look. Only ever shown when the notices really are off ON THIS DEVICE.
      blockedTitle: 'Notices are off',
      blockedDetail:
        "This device won't warn you when something needs your attention. Turn the notices on and it says so out loud, even with nobody looking at the screen.",
      blockedAction: 'Turn on notices',
      // After asking again and still getting nothing: the system stops showing its dialog once
      // it has been refused, and from then on the only way through is the device's own settings.
      blockedInSettings:
        "Your device didn't ask again. Open its settings, find ERPlora and turn its notifications on.",
      turnedOn: 'Done — this device will warn you when something needs your attention.',
    },
  },
  planLimits: {
    currentPlan: 'Current plan',
    unknownPlan: 'Unknown',
    healthy: 'Within limits',
    nearLimit: 'Near a limit',
    memory: 'Memory (RAM)',
    cpu: 'CPU',
    database: 'Database',
    devices: 'Devices',
    users: 'People',
    na: 'n/a',
    naHint: 'Not available on this device',
    capped: 'Plan limit',
    unlimited: 'Unlimited',
    usedOfLimit: '{used} of {limit}',
    usedNoLimit: '{used} used',
    coresOf: '{used} of {limit} vCPU',
    cores: '{used} cores',
    dbNoQuota: 'No plan quota',
    // Plural via vue-i18n (`singular | plural`, picked by the `n` option): «1 active sessions» (hub#2202).
    activeSessions: '{n} active session | {n} active sessions',
    activeUsers: '{n} active person | {n} active people',
    liveNote: 'Live — refreshes every few seconds while this page is open.',
    loadErrorTitle: 'Resource metrics are unavailable',
    loadErrorBody: "The Hub couldn't report its resource usage right now. You can try again.",
    retry: 'Try again',
    upgradeTitle: 'Running out of room on your plan',
    upgradeMemory: 'This hub is close to its memory limit. More room would let it run smoothly.',
    upgradeDatabase: 'Your database is close to its plan limit.',
    upgradeDevices: "You're using every device your plan allows.",
    upgradeUsers: 'Every seat on your plan is taken, so you cannot add another person.',
    // Says WHERE, and stays a sentence: a link from here to the plans page is a link to somewhere
    // money changes hands, and that is what both stores reject (hub#479).
    upgradeWhere: 'Plans are managed from your ERPlora account at erplora.com.',
  },
  billing: {
    invoices: 'Invoices',
    subscriptions: 'Subscriptions',
    payments: 'Payments',
    colInvoice: 'Invoice',
    colDate: 'Date',
    colDueDate: 'Due date',
    colAmount: 'Amount',
    colStatus: 'Status',
    colSubscription: 'Subscription',
    colPrice: 'Price',
    colRenews: 'Renews',
    downloadInvoiceAria: 'Download {number}',
    issuedOn: 'Issued {date}',
    duesOn: 'Due {date}',
    download: 'Download',
    noInvoices: 'No invoices',
    noSubscriptions: 'No active subscriptions',
    month: 'month',
    ends: 'Ends',
    renews: 'Renews',
    // These three name erplora.com instead of opening it: `managePlan`, `openBillingPortal` and
    // their error strings went with the buttons (hub#479). No "opens in your browser" either —
    // nothing opens from here any more.
    paymentsPortalNotice: 'Payment methods are managed from your ERPlora account at erplora.com.',
    managePlanHint: 'Plan changes are managed from your ERPlora account at erplora.com.',
    cloudAuthTitle: 'View billing in your ERPlora account',
    cloudAuthBody: 'Your local session is still active. Invoices and subscriptions require your online account session at erplora.com.',
    loadErrorTitle: 'We could not load billing',
    loadErrorBody: 'Check your connection and try again. You can continue using the Hub.',
    retry: 'Try again',
    statusDraft: 'Draft',
    statusOpen: 'Open',
    statusPaid: 'Paid',
    statusVoid: 'Void',
    statusUncollectible: 'Uncollectible',
  },
  // hub#846 — the shell's ONE reaction when the RUNTIME says this session is no longer valid
  // (expired, or displaced by a sign-in on another device): explain it, instead of screens
  // quietly emptying into «no data» or a «Retry» that can never help.
  auth: {
    sessionEnded:
      'Your session has ended: it expired or was opened on another device. Please sign in again.',
  },
  login: {
    logoAlt: 'Business logo',
    toggleTheme: 'Toggle theme',
    subtitleSetup: 'Create your access PIN',
    subtitlePin: 'Enter your PIN',
    subtitleEmail: 'Sign in to your business',
    tabPin: 'PIN',
    tabEmail: 'Email',
    emailLabel: 'Email',
    emailPlaceholder: "you{'@'}company.com",
    passwordLabel: 'Password',
    trustDevice: 'Trust this device',
    trustInfoAria: 'More information about trusted devices',
    // hub#358: shown instead of the "trust this device" box when an administrator marked this
    // device as personal. It states the CONSEQUENCE (it stays signed in), which is what matters if
    // the device is ever lost, and says where the decision lives.
    personalDeviceNote:
      'This device is set up as personal: it stays signed in and never asks for a PIN. An administrator can change that in Settings › General.',
    popoverTitle: 'PIN access',
    popoverBody: 'Check this box to sign in with a <strong>PIN</strong> on this device next time, without typing your email and password. If you leave it unchecked, you will always have to sign in with your email.',
    signIn: 'Sign in',
    usePinInstead: 'Use PIN instead',
    chooseUser: 'Choose your user',
    signInWithEmail: 'Sign in with email',
    changeUser: 'Change user',
    pinIncorrect: 'Incorrect PIN',
    // hub#658 — one sentence for every way a badge can be refused, on purpose: the login door must
    // not become the way to find out which cards this business has issued.
    orSwipeBadge: '…or swipe your badge — no need to tap your name first.',
    badgeRejected: 'That badge does not open anything here. Use your PIN, or ask an administrator.',
    badgeTooManyAttempts: 'Too many failed attempts with this badge. Wait a few minutes, or use your PIN.',
    // hub#330. Shown INSTEAD of «Incorrect PIN» when the refusal was about the device, not the
    // digits. Saying "incorrect PIN" to somebody whose PIN is correct is the worst answer available:
    // they retype it, and nothing on the screen names the one gesture that fixes it.
    deviceNotEnrolled:
      'A PIN does not work on this device yet. Sign in once with your account here and it will from then on.',
    // The other refusal, and it needs its own words: this browser keeps nothing between page loads
    // (a private window, or site data turned off), so signing in with an account would not help —
    // the next visit would be a stranger again.
    deviceUnidentified:
      'This browser cannot remember which device it is, so a PIN cannot be used here. Sign in with your account, or allow this site to store data and try again.',
    // ADR-0154: shown when this device's session was taken over by a sign-in on another device
    // (single active device plan). Wired since hub#1801: the runtime names the reason in the `401`
    // of the probe door, `main.ts` carries it here in the query, and this screen paints it — until
    // then the displaced device landed on the login with no word about why, which reads as an
    // outage and ends in a support call.
    sessionTakenOver: 'Session opened on another device',
    // The BODY says the two things the heading cannot: what the rule is (the plan, not a fault of
    // theirs) and what to do about it. Both gestures are offered, in the order that is free first.
    sessionTakenOverBody:
      'Your plan covers one device at a time, so signing in on another one signed this device out. Sign in again to use it here, or add devices to your plan.',
    // hub#2152 — the pass from the ERPlora panel could not be redeemed; the login still works.
    courierFailed: "Couldn't sign you in from the ERPlora panel",
    courierFailedBody:
      'Sign in here to continue.',
    setupChoosePin: 'Choose a {n}-digit PIN',
    setupConfirmPin: 'Confirm your PIN',
    setupMismatch: 'The PINs do not match, please try again',
    setupSaveError: 'The PIN could not be saved. Please try again.',
    setupPinTooSimple: 'That PIN is too easy to guess: avoid repeated digits (1111) and straight runs (1234).',
    footerTrustedDevice: 'trusted device',
    footerSecureCloud: 'secure connection',
    errorSignIn: 'Could not sign in. Check your credentials or your connection.',
    errorMachineRegistration:
      'Your account is valid, but this device could not be registered. Check the connection and try again.',
    requiredFields: 'Enter a valid email address and your password.',
    // ADR-0157 §8: sign in with the same Google account you use in the Cloud portal.
    orSeparator: 'or',
    continueWithGoogle: 'Continue with Google',
    errorGoogle: 'Could not sign in with Google. Please try again.',
    // Login 2-pasos (2FA por OTP de email, ERPlora/saas#994): pantalla de introducción del código.
    twoFactorSubtitle: 'Verify it’s you',
    twoFactorHint: 'We sent a one-time code to your email. Enter it to continue.',
    twoFactorCodeLabel: 'Verification code',
    twoFactorCodePlaceholder: '6-digit code',
    twoFactorVerify: 'Verify',
    twoFactorBack: 'Back',
    twoFactorRequired: 'Enter the code we sent to your email.',
    twoFactorIncorrect: 'Incorrect or expired code. We sent a new code — try again.',
    twoFactorError: 'Could not verify the code. Please try again.',
  },
  // hub#363 — the manager's approval, asked for without closing the cashier's session. Every line
  // here is read out loud across a counter with a queue behind it, so it says what to DO. Guarded
  // by `i18n/elevation-copy.test.ts`, including the one thing it must never say: WHICH of unknown
  // name / wrong PIN / deactivated user it was. The runtime answers those three identically on
  // purpose, so that a dialog anybody can open is not the way to learn who works here.
  elevation: {
    what: 'To approve: {action}',
    whatFromModule: 'To approve: an action in {app}',
    whatUnknown: 'To approve: an action this app cannot name',
    title: 'Approval needed',
    lead: 'Ask a manager to enter their PIN to approve this.',
    // hub#658 — swiping the card IS the approval (Toast, Aloha, Square). Said up front, in both
    // steps, because a badge needs nobody tapped on the grid first: it resolves the whole person.
    orSwipeBadge: '…or swipe their badge — no need to tap anything first.',
    chooseApprover: 'Who is approving?',
    approverName: 'Their name',
    approverNamePlaceholder: 'Type their name',
    continue: 'Continue',
    cancel: 'Cancel',
    changeApprover: 'Someone else',
    // The confirmation the cashier gets: the action went through, and under whose name it is now
    // recorded. Saying it out loud is half of what keeps the trail honest.
    approvedBy: 'Approved by {name}',
    rejected: 'Those details do not approve this. Check the name and the PIN, and try again.',
    approverCannot: 'That person cannot approve this. Ask someone who could do it themselves.',
    notElevable:
      'This one is not approved with a PIN. Whoever runs your business has to sign in with their own account to do it.',
    notRequired: 'This no longer needs approval. Close this and try again.',
    tooManyAttempts: 'Too many failed attempts. Wait a few minutes and try again.',
    failed: 'The approval could not be sent. Check the connection and try again.',
  },
  // hub#456 — the shift changes in the middle of a ticket. Every line here is read by somebody with
  // a queue in front of them, and the first job of the copy is to say that pressing this does NOT
  // lose the sale: without that sentence a cashier finishes the ticket under the wrong name, which
  // is the behaviour this feature exists to end.
  userSwitch: {
    menu: 'Switch user',
    title: 'Switch user',
    lead: 'The sale stays open. From now on it is recorded under whoever signs in here.',
    chooseUser: 'Who is taking over?',
    userName: 'Their name',
    userNamePlaceholder: 'Type their name',
    continue: 'Continue',
    cancel: 'Cancel',
    someoneElse: 'Someone else',
    // The confirmation: the till belongs to somebody else now, and the next lines of this sale
    // carry their name.
    nowServing: 'Now serving as {name}',
    rejected: 'Those details did not work. Check the name and the PIN, and try again.',
    deviceNotEnrolled:
      'This device is not set up for PINs yet. Sign in once with an ERPlora account on it, and the PIN will work from then on.',
    deviceUnidentified: 'This device could not identify itself. Reload the page and try again.',
    tooManyAttempts: 'Too many failed attempts. Wait a few minutes and try again.',
  },
  activation: {
    title: 'Activation required',
    lead: 'This device has to check your apps with erplora.com before it can open your business. Connect to the internet and try again.',
    retry: 'Retry',
    retryError: 'Your apps could not be checked yet. Check your connection or sign in with your ERPlora account.',
    logout: 'Log out',
  },
  exportPage: {
    title: 'Export configuration',
    lead: 'Package how this business is set up — and optionally its data — as a template you can load into another business.',
    adminOnly: 'Only an administrator can export the business.',
    name: 'Name',
    language: 'Language',
    sections: 'Sections',
    purposeTitle: 'What is this file for?',
    purposeBackup: 'Backup of this business',
    purposeBackupDesc: 'Private copy to restore or move this business. Includes your people and their access.',
    purposeTemplate: 'Template to share',
    purposeTemplateDesc: 'To publish or hand to another business. Never includes people, PINs or tax certificates.',
    purposeLocked: 'This is a demo or a test installation, so it can only export templates: people, PINs and tax details never travel in its file.',
    sectionUsers: 'Users',
    sectionUsersDesc: 'Employees, roles and permissions',
    sectionSettings: 'Settings',
    sectionSettingsDesc: 'Business settings: currency, language, tax details',
    // hub#405 — a template carries the configuration of the sector, never the identity of the
    // business that made it: its tax id would make another hub invoice under this company's name.
    sectionSettingsDescTemplate: 'Business settings: country, currency, language and theme. Never the tax id or the legal name.',
    sectionFiscal: 'Fiscal',
    sectionFiscalDesc: 'VeriFactu configuration and the company certificate',
    fiscalWarning: 'Includes the certificate: the .p12 travels as-is and keeps its own password. Share the file only with people you trust.',
    sectionMedia: 'Images and media',
    sectionMediaDesc: 'Files from the media folder',
    modules: 'Apps',
    modulesLead: 'Choose which installed apps the template registers, and whether their data travels along.',
    loadingModules: 'Loading installed apps…',
    colModule: 'App',
    colVersion: 'Version',
    colInclude: 'App',
    colData: 'Data',
    includeOf: 'Include {app}',
    dataOf: 'Data of {app}',
    selectAll: 'Select all',
    deselectAll: 'Deselect all',
    export: 'Export',
    exporting: 'Exporting…',
    done: '{filename} downloaded.',
    errorTitle: 'Export failed',
    // hub#765: the runtime did not answer before the deadline. Without a timeout the spinner spun
    // forever; now it aborts and says so honestly, so the user can retry instead of walking away.
    timeout: 'The server is taking too long to build the backup. Try again in a moment.',
  },
  // hub#1905 — asked at the end of a template import: the apps it brought need the owner's
  // permission, which a template can never give (hub#473). Same question the store asks for one app.
  importPermissions: {
    title: 'Permissions for your apps',
    intro: 'The template installed these apps, and they need your permission to work — a template cannot give it for you. You can change it any time in Settings → Permissions.',
    grant: 'Grant permissions',
    granting: 'Granting…',
    later: 'Not now',
    grantError: 'Could not grant the permissions of {apps}. Try again, or turn them on in Settings → Permissions.',
  },
  importPage: {
    title: 'Import configuration',
    lead: 'Load a template: it installs the missing apps, applies their data and copies the images.',
    adminOnly: 'Only an administrator can import.',
    pickTitle: 'Choose what to load',
    pickDesc: 'Pick a template published for your business, or upload a .blueprint.zip you exported or backed up.',
    pickFile: 'Choose .blueprint.zip file',
    fromCloud: 'From erplora.com',
    fromLocal: 'Upload from file',
    fromLocalDesc: 'A .blueprint.zip exported from another business, or a backup.',
    useTemplate: 'Use template',
    searchTemplates: 'Search templates',
    colTemplate: 'Template',
    colDescription: 'Description',
    colLanguage: 'Language',
    colVersion: 'Version',
    colDownloads: 'Downloads',
    colSize: 'Size',
    loadingCatalog: 'Loading templates…',
    catalogEmpty: 'No templates published for your business yet.',
    catalogForbidden: 'Only an administrator can browse and import templates.',
    catalogUnavailable: 'Templates could not be loaded right now. You can still import a file.',
    // hub#1120 — the way back from a catalogue that could not be read (a 429 from the SaaS lasts
    // minutes; this screen used to last longer, because it only ever asked once).
    catalogRetry: 'Try again',
    inspecting: 'Reading the file…',
    inspectErrorTitle: 'Could not read the file',
    manifestName: 'Name',
    manifestLanguage: 'Language',
    manifestCountry: 'Country',
    manifestModules: 'Apps',
    manifestCreated: 'Created',
    sections: 'Detected sections',
    sectionUsers: 'Users',
    sectionSettings: 'Settings',
    sectionFiscal: 'Fiscal',
    sectionFiscalDesc: 'VeriFactu configuration and the company certificate (.p12)',
    sectionMedia: 'Images and media',
    // hub#354 — the job titles the template switches on (Waiter, Kitchen…). A vertical brings its
    // own role set; the people who fill it are never in the file.
    sectionRoles: 'Roles',
    // hub#473 — the permissions each app had been given over this hub's own hardware and keys
    // (printer, signing certificate, internet, notifications). A backup brings them back so the
    // apps work again after a restore; a downloaded template never carries any.
    sectionCapabilities: 'App permissions',
    // hub#986 — the automations the owner wrote («when a big sale closes, note it on the
    // customer»). A backup brings the documents back; what each one is allowed to do is granted
    // again only on the terminal that granted it.
    sectionFlows: 'Automations',
    sectionModule: 'App {id}',
    modulesTitle: 'Apps',
    withData: 'includes data',
    import: 'Import',
    importing: 'Importing… installing apps and applying data.',
    importErrorTitle: 'Import failed',
    back: 'Choose another file',
    reportTitle: 'Import report',
    reportModules: 'Apps',
    // hub#763 — this report was RECOVERED, not just run. The Dashboard points an admin at Datos
    // after a partial import; this banner tells them WHICH import they are looking at (its name and
    // when it ran) so the report is not a mystery that appears out of nowhere.
    reportRecovered: 'This is the report of your last import of {name} ({when}). It did not all go in.',
    // The way back to the catalogue after reading a recovered report, so the admin can retry.
    reportDismiss: 'See the templates',
    // hub#845 — retry ONLY what did not make it in: the server re-downloads the SAME catalogue
    // version and re-runs just the failed parts; what already applied is never duplicated.
    retry: "Retry what's missing",
    retryNotRetryable:
      'This import came from an uploaded file, so it cannot be retried automatically. Upload the file again and select only what failed.',
    retryVersionUnavailable:
      'The template version this import used is no longer in the catalogue, so the retry did not run — retrying with a different version could load different data.',
    retryBatchNotFound:
      'The report of this import is no longer on record (it may have been undone), so there is nothing to retry.',
    statusApplied: 'Applied',
    statusSkipped: 'Skipped',
    statusIgnored: 'Discarded',
    statusPartial: 'Applied in part',
    statusFailed: 'Failed',
    // hub#409 / ADR-0060 — the module was not installed because the plan needs a dependency that
    // is not subscribed to. It is a purchase decision, not a breakage: it says what to subscribe
    // to (with the price the engine sent), never a mute red cross.
    statusBlocked: 'Subscription required',
    reasonBlocked:
      'Not installed: it needs apps you have not subscribed to yet: {missing}. Subscribe to them and load it again — nothing else was touched.',
    mediaFailed: '{n} not copied',
    // hub#751/#752/#1904 — the bundle names an older version than the one that went in: a
    // template always installs the newest compatible one, a backup only once its own is gone. It
    // installed fine; it is said out loud because the import preview listed the recorded version.
    reasonVersionSubstituted: 'The template came with {requested}; the newest compatible version, {installed}, went in.',
    // hub#331 — why the import kept a bundle's accounts out. Users, roles and PINs are the
    // identity of ONE hub: only that hub restoring its own backup gets them back.
    reasonIdentityNotPortable:
      'Users, roles and PINs belong to the business that created them. Accounts discarded: {n}. Nobody was given access to yours.',
    // hub#405 — the settings that came in and the ones that did not. The tax id is the one that
    // matters: with someone else's, this hub would invoice under their name.
    reasonSettingsNotPortable:
      'Country, currency and language were applied. Settings discarded: {n} — tax id, legal name and other details belong to the business that created the file; yours stay as they are.',
    // hub#354 — the template asked for roles this hub does not have in its catalogue: they belong
    // to a module that is not installed, or they are the administrative roles, which no file may
    // switch on. Nothing was created and nobody gained access.
    reasonRolesNotActivatable:
      'Roles not switched on: {n}. A template can only switch on roles the apps installed here provide, and never the administrative ones.',
    // ADR-0273 D8 / hub#560 — the file brought a section over this hub's own system tables (its
    // fiscal profile, its certificate store). No bundle writes those: they are this installation.
    reasonSystemTableNotPortable:
      "Rows discarded: {n}. The file tried to write this business's own records — its tax profile and certificate. Those belong to this installation and no file can change them.",
    // hub#753 — invoice series and the ledger of numbers already issued belong to ONE installation
    // (RD 1007/2023: no gaps, no duplicates). Yours are untouched; set them up here if you have not.
    reasonNumberingNotPortable:
      'Invoice numbering discarded: {n}. Series and the numbers already issued belong to the business that created the file. Your own numbering is untouched — set up your series in Settings if you have not yet.',
    // hub#380 — the app declares `installation_bound_data`: its records are chained to the till
    // that issued them (a VeriFactu chain, a TicketBai one), so they only ever come back to it.
    reasonInstallationBoundData:
      'Records discarded: {n}. This app keeps an official record chained to the till that issued it, so it only travels back to that same till. Yours starts its own — nothing here has been changed.',
    // hub#1947 — the template was published against an older version of the app, which kept data
    // the version installed here no longer has. Naming the APP and not the table is deliberate:
    // `appointments_schedule` is our word, and what she needs to know is that nothing is broken.
    reasonTableGoneInInstalledVersion:
      'Rows discarded: {n}. The template was built for an earlier version of this app, and the one installed here no longer keeps that data. Everything else went in — there is nothing for you to fix.',
    // hub#473 — the file came from ANOTHER hub and brought the permissions its owner had given to
    // its apps. Those are decisions about THIS terminal's printer, certificate and internet access,
    // so a downloaded file never makes them: you grant them here, once, and only if you want to.
    reasonCapabilityGrantsNotPortable:
      "App permissions discarded: {n}. Access to your printer, your signing certificate and the internet is granted on this terminal only. Nothing was allowed \u2014 grant what you need in Settings \u203a Permissions.",
    // hub#473 — this hub's OWN backup asked to restore permissions it can no longer grant: the app
    // was updated and stopped asking for them, or it is not installed here.
    reasonCapabilitiesNotGrantable:
      'Permissions not restored: {n}. Those apps no longer ask for them, or are not installed here. Everything else was given back.',
    // hub#986 — the file came from ANOTHER hub. Its automations are the owner's work and do come
    // back, but what each one may DO — which actions it runs, which addresses it writes to — is
    // granted on this terminal only, so they arrive switched off.
    reasonFlowGrantsNotPortable:
      'Automations restored, but switched off. What each one is allowed to do is granted on this terminal only — review them in Automations and turn on the ones you want.',
    // hub#986 — this hub's OWN backup asked to give an automation back a permission that no longer
    // exists here: the app did not come back, or its new version renamed the action.
    reasonFlowsPausedWithoutGrants:
      'Some automations came back switched off: a permission they had is no longer available here. Open Automations to see what each one is missing.',
    // hub#986 — the import saves through the same door as the editor, so a document this hub would
    // refuse on screen does not get in from a file either.
    reasonFlowsNotRestorable:
      'Automations discarded: {n}. Their instructions name something that is not here, so they could not be saved. The rest came back.',
    done: 'Go to home',
  },
  moduleView: {
    loading: 'Loading module…',
    loadError: 'Could not load the module.',
    loadErrorHint: 'Check that the module is still installed and active, then try again.',
    // hub#1743 — the sentence for when NOBODY answered. It must not mention the module: with the
    // wifi down the module is the one thing that is fine, and the line above sent people looking
    // for an app that nobody had uninstalled. It also promises the recovery, because the screen
    // really does come back on its own the moment the network does.
    offlineTitle: 'No internet connection',
    offlineHint:
      'This screen needs the connection to load. Check the network — it comes back on its own as soon as there is internet again.',
    retry: 'Try again',
    blockedTitle: 'Subscription required',
    blockedHint: 'This module is disabled because its subscription is no longer active for this hub. Your local data is safe and comes back as soon as the subscription does — manage it from your ERPlora account at erplora.com.',
    protectedTitle: 'Open the cash drawer first',
    protectedHint: 'This screen is locked while the cash drawer is closed. Open a register session to start selling — the screen reloads on its own the moment the drawer opens.',
    emptyTitle: 'Nothing to show here yet',
    emptyHint: 'This module is installed but has no screens to open right now. Check it is active in Apps, or open another one from the menu.',
    // hub#1175 — the router says why it sent you back: a module id nobody's entitlement ever
    // named (a stale bookmark, a typo, a module this hub never installed) has no screen to open.
    notAvailableToast: 'This app is not available for this hub.',
  },
  moduleSettings: {
    tab: 'Settings',
    loading: 'Loading settings…',
    loadError: 'Could not load settings.',
    save: 'Save',
    saved: 'Settings saved.',
    saveError: 'Could not save settings.',
    adminOnly: 'Only an administrator can change these settings.',
    textPlaceholder: 'Type here…',
    invalidFields: 'Check the fields marked below and save again.',
    fieldInvalid: 'This value is not accepted.',
    preview: 'Test',
    previewError: 'Could not run the test.',
  },
  modulePlan: {
    tab: 'Plan',
    statusTitle: 'Your plan',
    loadingStatus: 'Checking your subscription…',
    free: 'Free',
    perMonth: '/mo',
    perYear: '/yr',
    trialDays: '{n}-day trial',
    quota: 'Includes {quota}',
    overage: '{price} per extra unit',
    noTiers: 'This module has no paid plans.',
    trialEnds: 'Trial until {date}',
    renewsOn: 'Renews on {date}',
    cancelsOn: 'Cancels on {date}',
    // Where, not a way there — `buy` / `upgrade` / `cancel` and their error strings went with the
    // buttons that carried them (hub#479).
    managedInAccount: 'Plans for this module are managed from your ERPlora account at erplora.com.',
    checkPurchase: 'I already subscribed — check',
    // Badge on the card of the plan you are on (hub#1652). Same words as `statusTitle` on purpose:
    // it is the same fact, said on the block and again on the card it points at.
    yourPlan: 'Your plan',
    managePlan: 'Manage plan',
    managePlanError: 'Could not open plan management. Try again.',
    upgradeHubPlan: 'Upgrade your plan for more',
    purchaseDetected: 'Confirmed. Your plan has been updated.',
    // What the hub has already SPENT of what its plan includes (whatsapp_inbox#131). The tier
    // cards say what a plan includes; without these the one number that warns a channel is about
    // to go quiet had no screen at all. The metric itself is named by the module
    // (`lib/module-quota.ts`), so these strings never spell out «conversations».
    usageTitle: 'This month',
    usageOfLimit: '{used} of {limit} {metric}',
    usageNoLimit: '{used} {metric}',
    usageNearLimit: 'You are close to what your plan includes.',
    usageOverLimit: 'You have used everything your plan includes this month.',
    usageUnavailable: "Couldn't read what you have used. Try again in a moment.",
    status: {
      active: 'Active',
      trialing: 'Trialing',
      expired: 'Expired',
      none: 'No plan',
      canceled: 'Canceled',
      past_due: 'Past due',
    },
    hint: {
      active: 'Your subscription is active.',
      trialing: 'You are in your trial period.',
      expired: 'Your subscription has expired. Subscribe again to keep using it.',
      none: 'You don\'t have a plan for this module yet.',
      // Coming in through the free tier IS being on a plan (ADR-0032): no purchase, no card, and
      // the module runs with that tier's quota. It is how the majority of our customers come in.
      free: 'You are on {plan}, the plan everyone comes in on.',
      // Expiring does not leave you outside when the module ships a free tier: it drops you back
      // onto it. Saying "subscribe again to keep using it" there is simply not true.
      expiredOnFree: 'Your subscription has expired. You are still on {plan}.',
      includedInPlan: 'Included in your {plan} plan.',
      includedInHubPlan: 'Included in your plan.',
      canceled: 'Your subscription is canceled.',
      past_due: 'There is a pending payment on your subscription.',
    },
  },

  // Hardware (printers, cash drawer). The two sentences below are the whole point of hub#338:
  // a scan can end with no printers for two OPPOSITE reasons, and each one asks the user for a
  // different thing. Showing the wrong one sends them to fix something that was never broken.
  hardware: {
    printersBlocked:
      'ERPlora could not search this network: the system has not given the app permission to reach local devices. Grant local network access to ERPlora in your device settings and search again.',
    printersNone:
      'No printer found on this network. Check that the printer is switched on and connected to the same network as this device, then search again.',
    // ADR-0196 §3: a browser on its own has no way to reach a printer. Naming the app is the
    // whole point — this is the one sentence that turns "it does not work" into a next step.
    unavailable:
      'This device cannot reach printers from the browser. Install the ERPlora app on the device that is connected to the printer and open your business from there.',
    // hub#1773 — the sentence that goes in front of Android's local-network dialog, and the row
    // that says so afterwards. Android's own wording («find, connect to and determine the
    // relative position of nearby devices») reads like tracking and gets refused; ours says what
    // it is for. Never mentions the permission by name: what the owner recognises is the printer.
    localNetwork: {
      primerHeader: 'Let us look for your printer',
      primerMessage:
        'To find your printer we have to look at the devices on your network. Your device will ask you next.',
      primerLater: 'Not now',
      primerAllow: 'Look for my printer',
      // The row on System › your printer, which is where somebody whose printer is never found
      // would look. Only ever shown when the search really is blocked ON THIS DEVICE.
      blockedTitle: 'Printer search is blocked',
      blockedDetail:
        'This device is not allowed to reach the printers on your network, so a search comes back empty however many printers are switched on.',
      blockedAction: 'Allow the search',
      // After asking again and still getting nothing: the system stops showing its dialog once it
      // has been refused, and from then on the only way through is the device's own settings.
      blockedInSettings:
        "Your device didn't ask again. Open its settings, find ERPlora and turn local network access on.",
      turnedOn: 'Done — this device can look for printers on your network now.',
    },
  },
  // What the CORE says when it refuses ONE field (hub#1190, ADR-0398 §6).
  //
  // The runtime answers `{code:"invalid_field", field, reason, message}` and the `message` is the
  // English source written for a log. These are the sentences a person reads instead. Keyed by
  // DATA — the pair first, the reason alone as the fallback — because the pair is what the screen
  // has, and parsing the sentence is what ADR-0055 forbids.
  //
  // A reason with no entry here is NOT invented: the screen keeps the runtime's own sentence,
  // which names the role, the length or the accepted values (same rule as `platformFailureMessage`,
  // hub#1102).
  invalidField: {
    byField: {
      name: {
        required: 'Type the name.',
        too_long: 'That name is too long: use 150 characters or fewer.',
        duplicate:
          'This hub already knows somebody by that name. Edit that user — reinstate them if they were deactivated — instead of creating a second identity.',
      },
      role: {
        required: 'Pick a role.',
        too_long: 'That role name is too long: use 50 characters or fewer.',
      },
      pin: { format: 'The PIN is {length} digits, numbers only.' },
      badge: {
        length: 'The badge must be between 4 and 64 characters.',
        format: 'The badge only accepts letters, digits, “-” and “_”.',
      },
      email: { format: 'That email address is not valid.' },
      role_key: {
        required: 'Pick a role.',
        immutable:
          'This role comes with the hub: it is always on and cannot be switched off.',
        unknown:
          'No installed app declares this role. Install the app that brings it, or pick another role.',
        inactive:
          'This role is switched off in this hub. Switch it on in Settings → Roles before assigning it.',
      },
      language: { unknown: 'That language is not available in this hub.' },
      theme_mode: { unknown: 'That appearance is not one this hub offers.' },
      theme_palette: { unknown: 'That colour scheme is not one this hub offers.' },
    },
    // Fallback by reason alone: covers a field that gains a refusal before this table does, which
    // is how the last sixteen fixes of this family started.
    byReason: {
      required: 'This field is required.',
      too_long: 'This value is too long.',
      length: 'This value does not have the length this hub expects.',
      format: 'This value does not have the shape this hub expects.',
      unknown: 'This hub does not accept that value.',
      immutable: 'This value cannot be changed.',
      inactive: 'This value is switched off in this hub.',
      duplicate: 'This hub already has that value.',
    },
  },
  // hub#1620 — the same codes when the runtime ALSO sent the facts the line names (`core_version_too_old`
  // → `required`, `core`). Only `moduleFailureMessage` reads these, and only when every fact arrived.
  runtimeErrorFacts: {
    core_version_too_old:
      'This app needs a newer hub (ERPlora {required}). Yours runs {core}: update the hub and try again.',
  },
  // What the runtime answers a screen when a cloud-facing door fails: a short stable code, not a
  // sentence (hub#1689 made it a code precisely so it COULD be translated). Every back-office
  // screen turns it into one of these lines through `lib/runtime-error-sentence.ts`; a code with
  // no line here is never painted, the caller falls back to `default`.
  runtimeErrors: {
    cloud_unreachable: CLOUD_UNREACHABLE,
    // Installing or updating an app fails with its own code for the same fact: the hub never
    // reached erplora.com. One fact, one sentence.
    install_cloud_unavailable: CLOUD_UNREACHABLE,
    // hub#1720 — the three ways installing fails that are NOT «the hub could not reach
    // erplora.com», and used to be reported as if they were. Telling them apart is the whole
    // point: only one of them is fixed by waiting, so only one of them says to try again.
    install_cloud_denied:
      'erplora.com did not accept the credentials of this hub, so it cannot install apps. Trying again will not fix it; contact support.',
    install_not_in_catalog: 'That app is not available in your catalogue.',
    install_cloud_rejected:
      'erplora.com could not attend to this installation right now. Try again in a few minutes.',
    // hub#1620 — the app needs a newer hub than this one. The hub refuses on purpose (the app would
    // not run whole); the owner can act on it by updating the hub. The line that names both versions
    // lives in `runtimeErrorFacts`: this catalogue is read with the bare code, so it needs no data.
    core_version_too_old: 'This app needs a newer hub: update the hub and try again.',
    cloud_rejected: 'erplora.com could not attend to this right now. Try again in a few minutes.',
    cloud_unreadable: 'erplora.com answered something this hub could not read. Try again in a few minutes.',
    hub_not_enrolled: 'This hub is not connected to erplora.com yet.',
    // hub#1763 — `POST /api/modules/:id/update` when the new version failed AND the previous one
    // could not be restored: the app is gone from this hub. The gravest answer of that door, and the
    // one thing the toast must never say there is «it keeps running the version it had».
    module: {
      update_lost:
        'The update failed and the previous version could not be restored, so this app is no longer installed. Install it again from Apps; if that fails too, contact support.',
    },
    default: 'Something went wrong. Try again in a minute.',
  },
  // hub#1258 used to carry a `platformFailure` catalogue here for what the core says when it
  // refuses at the PLATFORM level (`db`/`io`/`wasm`/`native`/`schema`/`manifest`,
  // `module_not_installed`/`module_inactive`/`missing_dependency`/`read_unavailable`) — a
  // byte-identical copy of `platformFailureMessage` in `packages/module-sdk/src/index.ts`
  // (hub#1102). hub#1315 removed the copy: `lib/platform-failure.ts` now renders the SDK's own
  // sentence directly (`locale` in, sentence out), so there is exactly one place these ten
  // sentences are written and no i18n keys to keep in sync here.
} as const;
