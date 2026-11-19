// Types of base/schemas/files.py for the SDK (`useLive`, `useCommand`, `client.api.call`), written by
// hand: keep them in step with it and with `frontend/generated/operations.json`.

/** How the screen shows a file (`base.schemas.FilePreview`); `''`: it does not, it is downloaded. */
export type FilePreview = 'image' | 'pdf' | 'text' | 'table' | 'json' | 'audio' | 'video' | '';

/** `base.FileFolderOut`: a folder of the business's files and the folders in it. */
export interface FileFolder {
  /** «Facturas/2026». */
  path: string;
  name: string;
  children: FileFolder[];
}

/** `base.FileItemOut`: a file of the open folder. */
export interface FileItem {
  path: string;
  name: string;
  size: number;
  /** ISO time it was last written; `null` when the store keeps none. */
  modified: string | null;
  /** The type `base.file.read` serves it with. */
  content_type: string;
  preview: FilePreview;
}

/** `base.FileListOut`. */
export interface FilesListing {
  folder: string;
  crumbs: { path: string; name: string }[];
  folders: FileFolder[];
  files: FileItem[];
  /** What the hub's files take, against the plan's space (`limit_bytes: null`: no limit). */
  space: { used_bytes: number; limit_bytes: number | null };
  /** Upload, new folder and rename; delete (moving takes both). */
  can: { upload: boolean; delete: boolean };
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.file.list': { input: { folder?: string }; output: FilesListing };
    'base.file.read': {
      input: { path: string; inline?: boolean };
      output: { path: string; name: string; size: number; content_type: string; preview: FilePreview };
    };
    'base.file.upload': {
      input: { folder?: string; name: string; content_base64: string };
      output: { path: string; name: string; size: number };
    };
    'base.file.create_folder': { input: { parent?: string; name: string }; output: { path: string; name: string } };
    'base.file.rename': { input: { path: string; name: string }; output: { path: string; name: string } };
    'base.file.move': { input: { path: string; to?: string }; output: { path: string; name: string } };
    'base.file.delete': { input: { path: string }; output: { path: string; folder: boolean } };
  }
}
