// Types of base/schemas/catalog_images.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.

/** An image of the library: what a product, a service or a set menu keeps is its `reference`. */
export interface CatalogImage {
  /** `catalog:<folder>/<name>`. */
  reference: string;
  folder: string;
  name: string;
  /** In the business's language (in English when it is not Spanish); in the person's for `.get`. */
  title: string;
  /** `/p/catalog/<folder>/<name>.webp`, cached for a year. */
  url: string;
}

export interface CatalogImageSearchIn {
  /** Spanish or English; empty: the whole library (or folder) by title. */
  query?: string;
  /** beauty_body, beauty_hair, fitness, hospitality, retail or wellness_spa. */
  folder?: string | null;
  /** 1 to 100; 60 by default. */
  limit?: number;
  offset?: number;
}

export interface CatalogImagePage {
  rows: CatalogImage[];
  total: number;
  limit: number;
  offset: number;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    // The shared image library: 503 `base.image_library_unavailable` when it cannot be read.
    'base.catalog_image.search': { input: CatalogImageSearchIn; output: CatalogImagePage };
    'base.catalog_image.get': { input: { reference: string }; output: CatalogImage };
  }
}
