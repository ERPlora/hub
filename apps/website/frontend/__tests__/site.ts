// A site as `website.site.get` answers it for a hub that saved a name and a title and never published: what the
// editor's tests start from.
import type { SiteOut } from '../operations';

export const SITE: SiteOut = {
  template: 'classic',
  theme: { palette: 'ocean', custom: null, mode: 'auto' },
  content: {
    topbar: { name: 'Pepe', logo: null },
    hero: { title: 'Fresh food', tagline: '', cover: null },
    about: { hidden: false, title: '', text: '', image: null },
    catalog: { hidden: false, title: '', source: null, category_ids: [], show_prices: true },
    contact: {
      hidden: false,
      title: '',
      phone: '',
      whatsapp: '',
      email: '',
      socials: { instagram: '', facebook: '', tiktok: '', x: '' },
      hours: [],
    },
    location: { hidden: false, title: '', address_lines: [], map_url: '' },
    footer: { text: '' },
  },
  published_version: 0,
  published_at: null,
  is_live: false,
  has_changes: false,
  updated_at: null,
  public_url: 'https://a.erplora.com/',
};
