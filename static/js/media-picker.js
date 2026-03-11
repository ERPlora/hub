/**
 * Media Picker — Alpine.js component for WordPress-style image selection.
 *
 * Usage: x-data="mediaPicker('field_name', 'current_url', 'folder')"
 */
document.addEventListener('alpine:init', () => {
    Alpine.data('mediaPicker', (fieldName, currentUrl, folder) => ({
        fieldName,
        selectedUrl: currentUrl || '',
        pendingUrl: '',
        folder: folder || '',
        isOpen: false,
        tab: 'upload',
        dragover: false,
        uploading: false,

        // Library state
        libraryHtml: '',
        librarySearch: '',
        libraryFolder: folder || '',
        libraryFolders: [],

        // Shared state
        sharedHtml: '',
        sharedSearch: '',
        sharedFolder: '',
        sharedFolders: [],

        open() {
            this.isOpen = true;
            this.pendingUrl = this.selectedUrl;
            if (this.tab === 'library') this.loadLibrary();
        },

        close() {
            this.isOpen = false;
        },

        confirm() {
            if (this.pendingUrl) {
                this.selectedUrl = this.pendingUrl;
                // Clear the file input so only URL is submitted
                if (this.$refs.fileInput) this.$refs.fileInput.value = '';
            }
            this.close();
        },

        clear() {
            this.selectedUrl = '';
            this.pendingUrl = '';
            if (this.$refs.fileInput) this.$refs.fileInput.value = '';
        },

        selectPending(url) {
            this.pendingUrl = url;
        },

        // Direct file input (fallback — bypasses modal)
        handleDirectUpload(event) {
            const file = event.target.files[0];
            if (!file) return;
            // Show preview immediately
            this.selectedUrl = URL.createObjectURL(file);
            // The form will submit the file via the regular input
        },

        // Upload via modal dropzone or browse
        async handleUpload(event) {
            const files = event.target.files;
            if (!files.length) return;
            await this._upload(files);
        },

        async handleDrop(event) {
            this.dragover = false;
            const files = event.dataTransfer.files;
            if (!files.length) return;
            await this._upload(files);
        },

        async _upload(files) {
            this.uploading = true;
            const formData = new FormData();
            for (const file of files) {
                formData.append('file', file);
            }
            formData.append('folder', this.folder);

            try {
                const resp = await fetch('/htmx/media/upload/', {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value
                            || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '',
                    },
                });
                const data = await resp.json();
                if (data.url) {
                    this.pendingUrl = data.url;
                    this.selectedUrl = data.url;
                    // Clear file input
                    if (this.$refs.fileInput) this.$refs.fileInput.value = '';
                    this.close();
                } else if (data.files) {
                    // Multiple files — select the first
                    this.pendingUrl = data.files[0].url;
                    this.selectedUrl = data.files[0].url;
                    if (this.$refs.fileInput) this.$refs.fileInput.value = '';
                    this.close();
                }
            } catch (err) {
                console.error('Upload failed:', err);
            } finally {
                this.uploading = false;
            }
        },

        async loadLibrary() {
            const params = new URLSearchParams();
            if (this.librarySearch) params.set('q', this.librarySearch);
            if (this.libraryFolder) params.set('folder', this.libraryFolder);

            try {
                const resp = await fetch(`/htmx/media/list/?${params}`);
                this.libraryHtml = await resp.text();

                // Extract folders from response if first load
                if (!this.libraryFolders.length) {
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(this.libraryHtml, 'text/html');
                    // Folders are injected via a hidden element
                    const foldersEl = doc.querySelector('[data-folders]');
                    if (foldersEl) {
                        try {
                            this.libraryFolders = JSON.parse(foldersEl.dataset.folders);
                        } catch {}
                    }
                }
            } catch {}
        },

        async loadShared() {
            // Load folders on first access
            if (!this.sharedFolders.length) {
                try {
                    const resp = await fetch('/htmx/media/shared/folders/');
                    const data = await resp.json();
                    this.sharedFolders = data.folders || [];
                } catch {}
            }

            const params = new URLSearchParams();
            if (this.sharedSearch) params.set('q', this.sharedSearch);
            if (this.sharedFolder) params.set('folder', this.sharedFolder);

            try {
                const resp = await fetch(`/htmx/media/shared/?${params}`);
                this.sharedHtml = await resp.text();
            } catch {}
        },
    }));
});
