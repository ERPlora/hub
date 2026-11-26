// The sites screens-text-fits.spec.ts already knows cut a text, each with the issue that fixes it. A site is a box
// that cuts on the screens listed, at whatever size. The list only shrinks: a text cut anywhere else fails the spec,
// and so does a site that no longer cuts on any of its screens, until its entry goes.
export interface KnownSite {
  box: string;
  screens: readonly string[];
  issue: string;
}

/** The class of fault these all belong to; each site moves to its own issue when it is taken up. */
const CLASS = 'ERPlora/hub#2642';

export const KNOWN_SITES: readonly KnownSite[] = [
  {
    // The title of the topbar on the phone ends in «…» when it is longer than the room left by its buttons.
    box: 'ion-title.ios.title-default >> div.toolbar-title',
    screens: [
      '/api-docs',
      '/customer/fields',
      '/customer/groups',
      '/customer/preview/customer-search',
      '/customer/tags',
      '/online_booking/preview',
      '/verifactu/config',
      '/verifactu/contingency',
      '/verifactu/events',
      '/verifactu/records',
      '/verifactu/recovery',
      '/verifactu/settings',
    ],
    issue: CLASS,
  },
  // Home on the phone: the name of a product in a bar chart.
  { box: 'span.widget-bar-label', screens: ['/'], issue: CLASS },
  // Settings of Appointments on the phone: a field's label wider than the screen.
  { box: 'ion-content.ios.content-ltr >> div.inner-scroll.scroll-y', screens: ['/appointment/settings'], issue: CLASS },
  // The till: a category's name in the strip, and a product's name in its tile.
  { box: 'span.pos-cat__name', screens: ['/sale/pos'], issue: 'ERPlora/hub#2409' },
  { box: 'span.pos-tile__name', screens: ['/sale/pos'], issue: CLASS },
  // System on the phone: the names of the usage figures, a word or two a line.
  { box: 'span.system-usage-name', screens: ['/system'], issue: CLASS },
];
