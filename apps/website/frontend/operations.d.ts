// Types of the website app's operations for the SDK (`useLive`, `useCommand`), from apps/website/schemas.py.
// Written by hand, as `frontend/sdk-types.d.ts` is for the PoC, until V3 generates them from `/api/openapi.json`.
// Keep it in step with schemas.py and with `frontend/generated/operations.json`. One input per operation (ninja's
// parity): no path parameters.

export type WebsiteTemplate = 'classic' | 'modern' | 'minimal' | 'bold';
export type CatalogSource = 'inventory' | 'service';
export type Day = 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun';
export type PriceKind = 'fixed' | 'from' | 'hourly' | 'free' | 'none';
export type StarKind = 'on' | 'half' | 'off';
export type ReviewsState = 'empty' | 'unavailable' | 'waiting' | 'failed' | 'ready';

export interface NoIn {
  [key: string]: never;
}

/** An uploaded image: its id; the server writes its URL on every save. */
export interface ImageRef {
  id: string;
  url: string;
}

export type PaletteId = 'ocean' | 'forest' | 'terracotta' | 'slate' | 'rose' | 'sand' | 'midnight' | 'olive';
export type ThemeMode = 'light' | 'dark' | 'auto';

/** The owner's two colours (#rrggbb) over the chosen palette's; the page, the bands and the text are derived from them. */
export interface CustomColours {
  primary: string;
  accent: string;
}

/** A curated palette, the owner's two colours over it (null = the palette's own), and light, dark or auto. */
export interface Theme {
  palette: PaletteId;
  custom: CustomColours | null;
  mode: ThemeMode;
}

export interface TopbarSection {
  name: string;
  logo: ImageRef | null;
}

export interface HeroSection {
  title: string;
  tagline: string;
  cover: ImageRef | null;
}

export interface AboutSection {
  hidden: boolean;
  title: string;
  text: string;
  image: ImageRef | null;
}

export interface CatalogSection {
  hidden: boolean;
  title: string;
  source: CatalogSource | null;
  category_ids: string[];
  show_prices: boolean;
}

/** Up to 12 uploaded photos, in the order the page shows them. */
export interface GallerySection {
  hidden: boolean;
  title: string;
  images: ImageRef[];
}

/** The business on Google Maps: the link of its page there, a share link or its Place ID; empty = no reviews. */
export interface ReviewsSection {
  hidden: boolean;
  title: string;
  place_ref: string;
}

export interface Socials {
  instagram: string;
  facebook: string;
  tiktok: string;
  x: string;
}

export interface Interval {
  opens: string;
  closes: string;
}

export interface DayHours {
  day: Day;
  intervals: Interval[];
}

export interface ContactSection {
  hidden: boolean;
  title: string;
  phone: string;
  whatsapp: string;
  email: string;
  socials: Socials;
  hours: DayHours[];
}

export interface LocationSection {
  hidden: boolean;
  title: string;
  address_lines: string[];
  map_url: string;
}

export interface FooterSection {
  text: string;
}

export interface Content {
  topbar: TopbarSection;
  hero: HeroSection;
  about: AboutSection;
  catalog: CatalogSection;
  gallery: GallerySection;
  reviews: ReviewsSection;
  contact: ContactSection;
  location: LocationSection;
  footer: FooterSection;
}

export interface SaveIn {
  template: WebsiteTemplate;
  theme: Theme;
  content: Content;
}

/** Whether Google's rating and reviews of the draft's place are there (the editor's note). */
export interface ReviewsStatusOut {
  state: ReviewsState;
  rating: number | null;
  count: number;
  fetched_at: string | null;
}

export interface SiteOut extends SaveIn {
  published_version: number;
  published_at: string | null;
  is_live: boolean;
  has_changes: boolean;
  updated_at: string | null;
  public_url: string;
  reviews: ReviewsStatusOut;
}

export interface PreviewOut {
  html: string;
}

export interface PublicationOut {
  published_version: number;
  published_at: string | null;
  is_live: boolean;
}

export interface ImageUploadIn {
  filename: string;
  content_type: 'image/jpeg' | 'image/png' | 'image/webp';
  data_base64: string;
}

export interface ImageOut {
  id: string;
  url: string;
  content_type: string;
  width: number;
  height: number;
  size: number;
}

export interface QrIn {
  format?: 'png' | 'svg';
}

export interface QrOut {
  format: 'png' | 'svg';
  url: string;
  content_type: string;
  filename: string;
  content_base64: string;
}

export interface CategoriesIn {
  source: CatalogSource;
}

export interface CategoriesOut {
  categories: { id: string; name: string }[];
}

export interface CatalogItemOut {
  name: string;
  price: number | null;
  price_kind: PriceKind;
  minutes: number | null;
  price_label: string;
}

export interface CatalogOut {
  source: CatalogSource | null;
  show_prices: boolean;
  groups: { name: string; items: CatalogItemOut[] }[];
}

/** One review's card, its labels in the visitor's language. */
export interface ReviewOut {
  author: string;
  author_uri: string;
  initial: string;
  stars: StarKind[];
  stars_label: string;
  text: string;
  /** The whole review when `text` was cut; empty otherwise. */
  full_text: string;
  when: string;
  uri: string;
}

/** Google's rating and reviews of the business as the public page shows them; `available: false` = nothing to show. */
export interface ReviewsOut {
  available: boolean;
  rating_label: string;
  stars: StarKind[];
  stars_label: string;
  count_label: string;
  maps_uri: string;
  write_uri: string;
  reviews: ReviewOut[];
}

export interface PublicSiteOut {
  version: number;
  published_at: string | null;
  template: WebsiteTemplate;
  theme: Theme;
  content: Content;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'website.site.get': { input: NoIn; output: SiteOut };
    'website.site.save': { input: SaveIn; output: SiteOut };
    'website.site.publish': { input: NoIn; output: PublicationOut };
    'website.site.unpublish': { input: NoIn; output: PublicationOut };
    'website.site.preview': { input: NoIn; output: PreviewOut };
    'website.image.upload': { input: ImageUploadIn; output: ImageOut };
    'website.qr.get': { input: QrIn; output: QrOut };
    'website.catalog.categories': { input: CategoriesIn; output: CategoriesOut };
    'website.public.site': { input: NoIn; output: PublicSiteOut };
    'website.public.catalog': { input: NoIn; output: CatalogOut };
    'website.public.reviews': { input: NoIn; output: ReviewsOut };
  }
}
